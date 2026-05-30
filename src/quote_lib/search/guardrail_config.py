from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class GuardrailConfig:
    """
    Fuzzy guardrail knobs applied after cross-encoder ranking.

    Manual baseline (not grid-tuned):
    - strict mode (short / numeric queries): heavy miss penalty, moderate boosts
    - soft mode (medium queries): lighter nudges only
    - off mode (long queries): CE score unchanged

    Penalties are in CE-score units (~0–10 range); boosts are additive offsets.
    """

    strict_miss_penalty: float = 3.0
    strict_strong_boost: float = 0.75
    strict_partial_boost: float = 0.25
    strict_strong_fuzzy_threshold: float = 0.90
    soft_boost: float = 0.5
    soft_miss_penalty: float = 1.0
    soft_fuzzy_threshold: float = 0.85
    soft_weak_fuzzy: float = 0.40

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GuardrailConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


DEFAULT_GUARDRAIL_CONFIG = GuardrailConfig()
