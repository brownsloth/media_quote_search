from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from quote_lib.parse.clean import clean_cue_text
from quote_lib.search.guardrail_config import DEFAULT_GUARDRAIL_CONFIG, GuardrailConfig
from quote_lib.search.embedder import Embedder
from quote_lib.search.lexical import apply_lexical_guardrail, lexical_mode
from quote_lib.search.reranker import CrossEncoderReranker


@dataclass
class SearchResult:
    rank: int
    score: float
    ce_score: float
    ann_score: float
    fuzzy_score: float
    chunk_id: str
    season: int | None
    episode: int | None
    text_line: str
    text_embed: str
    start_ms: int
    end_ms: int = 0
    show_id: str | None = None
    show_title: str | None = None
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    guardrail_note: str | None = None


@dataclass
class ChunkIndex:
    chunks: list[dict]
    embeddings: np.ndarray
    model_name: str
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    _embedder: Embedder | None = field(default=None, repr=False)
    _reranker: CrossEncoderReranker | None = field(default=None, repr=False)

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(model_name=self.model_name)
        return self._embedder

    @property
    def reranker(self) -> CrossEncoderReranker:
        if self._reranker is None:
            self._reranker = CrossEncoderReranker(model_name=self.reranker_model)
        return self._reranker

    @classmethod
    def build(
        cls,
        chunks: list[dict],
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        batch_size: int = 64,
        show_progress: bool = True,
    ) -> "ChunkIndex":
        embedder = Embedder(model_name=model_name)
        texts = [c["text_embed"] for c in chunks]
        embeddings = embedder.encode(texts, batch_size=batch_size, show_progress=show_progress)
        return cls(chunks=chunks, embeddings=embeddings, model_name=model_name)

    def save(self, directory: Path, *, verbose: bool = True) -> None:
        if verbose:
            print(f"Saving index to {directory} ...", flush=True)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "embeddings.npy", self.embeddings)
        meta = {
            "model_name": self.model_name,
            "reranker_model": self.reranker_model,
            "chunk_count": len(self.chunks),
            "embedding_dim": int(self.embeddings.shape[1]),
        }
        (directory / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        with (directory / "chunks.jsonl").open("w", encoding="utf-8") as f:
            for chunk in self.chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        if verbose:
            print(f"  saved {len(self.chunks)} chunks + embeddings.npy", flush=True)

    @classmethod
    def load(cls, directory: Path) -> "ChunkIndex":
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        embeddings = np.load(directory / "embeddings.npy")
        chunks: list[dict] = []
        with (directory / "chunks.jsonl").open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))
        return cls(
            chunks=chunks,
            embeddings=embeddings,
            model_name=meta["model_name"],
            reranker_model=meta.get("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        ann_top: int = 200,
        use_reranker: bool = True,
        max_per_episode: int | None = 2,
        guardrail_config: GuardrailConfig | None = None,
    ) -> list[SearchResult]:
        """
        Staged retrieval:
          1. Bi-encoder ANN → recall gate (ann_top candidates)
          2. Cross-encoder → primary ranking
          3. Fuzzy guardrails on text_line → query-dependent boosts/penalties
        """
        q_clean = clean_cue_text(query, for_embed=True)
        q_vec = self.embedder.encode([q_clean])[0]

        ann_scores = self.embeddings @ q_vec
        ann_top = min(ann_top, len(self.chunks))
        candidate_idx = np.argpartition(-ann_scores, ann_top - 1)[:ann_top]
        candidate_idx = candidate_idx[np.argsort(-ann_scores[candidate_idx])]

        candidates = [(int(i), float(ann_scores[int(i)]), self.chunks[int(i)]) for i in candidate_idx]

        if use_reranker:
            pairs = [(query, chunk["text_embed"]) for _, _, chunk in candidates]
            ce_scores = self.reranker.score_pairs(pairs)
        else:
            ce_scores = [ann for _, ann, _ in candidates]

        mode = lexical_mode(query)
        cfg = guardrail_config or DEFAULT_GUARDRAIL_CONFIG
        scored: list[tuple[float, int, float, float, float, str | None, dict]] = []

        for (idx, ann, chunk), ce in zip(candidates, ce_scores):
            adjusted, fuzzy, note = apply_lexical_guardrail(
                ce,
                query=query,
                text_line=chunk["text_line"],
                mode=mode,
                config=cfg,
            )
            scored.append((adjusted, idx, ce, ann, fuzzy, note, chunk))

        scored.sort(key=lambda row: row[0], reverse=True)

        results: list[SearchResult] = []
        episode_counts: dict[str, int] = {}

        for adjusted, _idx, ce, ann, fuzzy, note, chunk in scored:
            if max_per_episode is not None:
                ep_key = f"{chunk.get('show_id')}:{chunk.get('season')}:{chunk.get('episode')}"
                if episode_counts.get(ep_key, 0) >= max_per_episode:
                    continue
                episode_counts[ep_key] = episode_counts.get(ep_key, 0) + 1

            results.append(
                SearchResult(
                    rank=0,
                    score=adjusted,
                    ce_score=ce,
                    ann_score=ann,
                    fuzzy_score=fuzzy,
                    chunk_id=chunk["chunk_id"],
                    show_id=chunk.get("show_id"),
                    show_title=chunk.get("show_title"),
                    season=chunk.get("season"),
                    episode=chunk.get("episode"),
                    text_line=chunk["text_line"],
                    text_embed=chunk["text_embed"],
                    start_ms=chunk["start_ms"],
                    end_ms=chunk.get("end_ms", chunk["start_ms"]),
                    context_before=chunk.get("context_before") or [],
                    context_after=chunk.get("context_after") or [],
                    guardrail_note=note,
                )
            )
            if len(results) >= top_k:
                break

        for i, result in enumerate(results, start=1):
            result.rank = i
        return results
