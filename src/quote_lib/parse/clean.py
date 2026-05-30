from __future__ import annotations

import re

HTML_TAG_RE = re.compile(r"<[^>]+>")
ASS_TAG_RE = re.compile(r"\{\\[^}]+\}")
BRACKET_STAGE_RE = re.compile(r"\[[^\]]*\]")
PAREN_STAGE_RE = re.compile(r"\([^)]*\)")
MUSIC_NOTE_RE = re.compile(r"♪+")
SPEAKER_PREFIX_RE = re.compile(
    r"^(?:[-–—]\s*)?(?P<name>[A-Z][A-Z0-9 .'-]{0,30})\s*:\s*(?P<text>.+)$"
)
LEADING_DASH_RE = re.compile(r"^[-–—]\s*")
WHITESPACE_RE = re.compile(r"\s+")

WATERMARK_PATTERNS = (
    "my-subs.com",
    "translated by the community",
    "www.my-subs",
)


def is_watermark_line(text: str) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in WATERMARK_PATTERNS)


def strip_html(text: str) -> str:
    return HTML_TAG_RE.sub("", text)


def extract_speaker(text: str) -> tuple[str | None, str]:
    """Best-effort speaker parse. Most Archer subs have no names."""
    match = SPEAKER_PREFIX_RE.match(text.strip())
    if not match:
        return None, text
    name = match.group("name").strip()
    body = match.group("text").strip()
    if len(name.split()) > 4:
        return None, text
    return name.title(), body


def clean_cue_text(text: str, *, for_embed: bool = True) -> str:
    """
    Normalize cue text for search/embeddings.

    Display text should use text_raw; this produces text_clean.
    """
    text = strip_html(text)
    text = ASS_TAG_RE.sub("", text)
    if for_embed:
        text = BRACKET_STAGE_RE.sub(" ", text)
        text = PAREN_STAGE_RE.sub(" ", text)
        text = MUSIC_NOTE_RE.sub(" ", text)
    text = LEADING_DASH_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    if for_embed:
        text = text.lower()
    return text


def whitespace_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower()) if text else []
