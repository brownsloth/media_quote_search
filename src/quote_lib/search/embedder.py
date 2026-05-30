from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Embedder:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    def __post_init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        print(f"  loading embedder {self.model_name} ...", flush=True)
        self.model = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str], *, batch_size: int = 64, show_progress: bool = True) -> np.ndarray:
        use_bar = show_progress and len(texts) > 0
        if use_bar:
            print(f"  encoding {len(texts)} texts (batch_size={batch_size}) ...", flush=True)
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=use_bar,
        )
        return np.asarray(vectors, dtype=np.float32)
