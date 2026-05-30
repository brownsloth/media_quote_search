from __future__ import annotations

import re

from quote_lib.parse.clean import clean_cue_text, whitespace_tokens
from quote_lib.search.guardrail_config import DEFAULT_GUARDRAIL_CONFIG, GuardrailConfig

STOPWORDS = frozenset(
    """
    a an the and or but if then else when at by for with about against between
    into through during before after above below to from up down in out on off
    over under again further once here there all each few more most other some
    such no nor not only own same so than too very can will just don should now
    is are was were be been being have has had do does did doing what which who
    wh this that these those am i you he she it we they me him her us them my
    your his its our their of as
    """.split()
)


def distinctive_tokens(query: str) -> list[str]:
    tokens = whitespace_tokens(clean_cue_text(query, for_embed=True))
    out: list[str] = []
    for tok in tokens:
        if tok in STOPWORDS:
            continue
        if len(tok) >= 3 or any(ch.isdigit() for ch in tok):
            out.append(tok)
    return out


def lexical_mode(query: str) -> str:
    tokens = distinctive_tokens(query)
    if not tokens:
        return "off"
    if any(any(ch.isdigit() for ch in t) for t in tokens):
        return "strict"
    if len(tokens) <= 4:
        return "strict"
    if len(tokens) <= 8:
        return "soft"
    return "off"


def line_fuzzy_score(query: str, text_line: str) -> float:
    from rapidfuzz import fuzz

    q = clean_cue_text(query, for_embed=True)
    line = clean_cue_text(text_line, for_embed=True)
    if not q or not line:
        return 0.0
    return fuzz.partial_ratio(q, line) / 100.0


def token_hits(tokens: list[str], text: str) -> int:
    cleaned = clean_cue_text(text, for_embed=True)
    return sum(1 for t in tokens if t in cleaned)


def apply_lexical_guardrail(
    ce_score: float,
    *,
    query: str,
    text_line: str,
    mode: str,
    config: GuardrailConfig | None = None,
) -> tuple[float, float, str | None]:
    cfg = config or DEFAULT_GUARDRAIL_CONFIG
    fuzzy = line_fuzzy_score(query, text_line)
    if mode == "off":
        return ce_score, fuzzy, None

    tokens = distinctive_tokens(query)
    hits = token_hits(tokens, text_line)
    note: str | None = None
    adjusted = ce_score

    if mode == "strict":
        if tokens and hits == 0:
            adjusted -= cfg.strict_miss_penalty
            note = "strict: no distinctive token in line"
        elif fuzzy >= cfg.strict_strong_fuzzy_threshold:
            adjusted += cfg.strict_strong_boost
            note = "strict: strong line match"
        elif hits >= max(1, len(tokens) // 2):
            adjusted += cfg.strict_partial_boost
            note = "strict: partial token hit"

    elif mode == "soft":
        if fuzzy >= cfg.soft_fuzzy_threshold:
            adjusted += cfg.soft_boost
            note = "soft: line fuzzy boost"
        elif tokens and hits == 0 and fuzzy < cfg.soft_weak_fuzzy:
            adjusted -= cfg.soft_miss_penalty
            note = "soft: weak line match"

    return adjusted, fuzzy, note
