from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np


def _resolve_device() -> str:
    forced = os.environ.get("EMBED_DEVICE", "").strip().lower()
    if forced:
        return forced
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


@dataclass
class Embedder:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str | None = None

    def __post_init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.device = self.device or _resolve_device()
        print(f"  loading embedder {self.model_name} on {self.device} ...", flush=True)
        self.model = SentenceTransformer(self.model_name, device=self.device)

    def encode(self, texts: list[str], *, batch_size: int | None = None, show_progress: bool = True) -> np.ndarray:
        if batch_size is None:
            batch_size = int(os.environ.get("EMBED_BATCH_SIZE", "512" if self.device == "cuda" else "64"))
        use_bar = show_progress and len(texts) > 0
        if use_bar:
            print(f"  encoding {len(texts)} texts (batch_size={batch_size}, device={self.device}) ...", flush=True)
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=use_bar,
            device=self.device,
        )
        return np.asarray(vectors, dtype=np.float32)