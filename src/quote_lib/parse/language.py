from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect_langs

from quote_lib.parse.srt import ParsedEpisode

DetectorFactory.seed = 0

# Subtitle lines are short; langdetect can be noisy on single cues.
MIN_SAMPLE_CHARS = 400


def detect_episode_language(episode: ParsedEpisode) -> str | None:
    """
    Detect primary dialogue language for an episode.

    Returns ISO 639-1 code (e.g. 'en', 'es') or None if unknown.
    """
    parts: list[str] = []
    total = 0
    for cue in episode.cues:
        if cue.is_watermark or not cue.text_raw.strip():
            continue
        parts.append(cue.text_raw)
        total += len(cue.text_raw)
        if total >= MIN_SAMPLE_CHARS:
            break

    sample = " ".join(parts).strip()
    if len(sample) < 80:
        return None

    try:
        langs = detect_langs(sample)
    except LangDetectException:
        return None

    if not langs:
        return None

    top = langs[0]
    if top.prob < 0.85:
        return None
    return top.lang


def needs_translation(episode: ParsedEpisode, target_lang: str = "en") -> bool:
    lang = detect_episode_language(episode)
    episode.detected_language = lang
    return lang is not None and lang != target_lang
