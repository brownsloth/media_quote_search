"""Load index and run quote search for the API."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from quote_lib.links.netflix import _load_mapping
from quote_lib.search.format import result_to_dict
from quote_lib.search.guardrail_config import GuardrailConfig
from quote_lib.search.index import ChunkIndex
from quote_lib.search.lexical import lexical_mode


class QuoteSearchService:
    def __init__(self, index_dir: Path | str | None = None) -> None:
        if index_dir is None:
            index_dir = os.environ.get("SERVE_INDEX_DIR")
        if index_dir is None:
            index_dir = Path(os.environ.get("SERVE_ARTIFACTS_DIR", "serving/artifacts")) / "index"
        index_dir = Path(index_dir)
        guardrail_path = index_dir.parent / "guardrail_config.json"
        if not guardrail_path.exists():
            guardrail_path = Path(
                os.environ.get(
                    "SERVE_GUARDRAIL_CONFIG",
                    "data/processed/stats/guardrail_config.json",
                )
            )

        self.index_dir = index_dir
        self.guardrail_config: GuardrailConfig | None = None
        if guardrail_path.exists():
            self.guardrail_config = GuardrailConfig.from_dict(
                json.loads(guardrail_path.read_text(encoding="utf-8"))
            )

        self.index = ChunkIndex.load(index_dir)
        self.meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))

    def health(self) -> dict:
        netflix = _load_mapping()
        episodes = netflix.get("episodes") or {}
        return {
            "index_dir": str(self.index_dir),
            "chunk_count": self.meta.get("chunk_count"),
            "embedding_model": self.meta.get("model_name"),
            "reranker_model": self.meta.get("reranker_model"),
            "netflix_show_id": netflix.get("show_id"),
            "netflix_episode_count": len(episodes),
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        ann_top: int = 200,
        use_reranker: bool = True,
    ) -> dict:
        t0 = time.perf_counter()
        results = self.index.search(
            query,
            top_k=top_k,
            ann_top=ann_top,
            use_reranker=use_reranker,
            guardrail_config=self.guardrail_config,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "query": query,
            "lexical_mode": lexical_mode(query),
            "latency_ms": latency_ms,
            "results": [result_to_dict(r) for r in results],
        }
