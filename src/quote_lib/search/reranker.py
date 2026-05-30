from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CrossEncoderReranker:
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __post_init__(self) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(self.model_name)

    def score_pairs(self, pairs: list[tuple[str, str]], *, batch_size: int = 32) -> list[float]:
        if not pairs:
            return []
        raw = self.model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
        return [float(x) for x in raw]
