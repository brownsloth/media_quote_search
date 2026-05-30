from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from quote_lib.parse.clean import clean_cue_text, extract_speaker, is_watermark_line

TIMESTAMP_LINE_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
)
EPISODE_FILE_RE = re.compile(
    r"(?:Archer|Friends|The\.Office|Game\.of\.Thrones|Breaking\.Bad|"
    r"Friends|Office|GoT|BB|[A-Za-z0-9._+-]+)"
    r"\.S(?P<season>\d+)E(?P<episode>\d+)\.(?P<release>[^/\\]+)\.srt$",
    re.IGNORECASE,
)
# Generic: anything.S01E02.Release.srt
GENERIC_EPISODE_FILE_RE = re.compile(
    r"\.S(?P<season>\d+)E(?P<episode>\d+)\.(?P<release>[^/\\]+)\.srt$",
    re.IGNORECASE,
)
# OpenSubtitles download layout: S01E01.srt
FLAT_EPISODE_FILE_RE = re.compile(
    r"^S(?P<season>\d+)E(?P<episode>\d+)\.srt$",
    re.IGNORECASE,
)


@dataclass
class ParsedCue:
    cue_index: int | None
    start_ms: int
    end_ms: int
    text_raw: str
    text_clean: str
    speaker: str | None = None
    is_watermark: bool = False
    text_original: str | None = None


@dataclass
class ParsedEpisode:
    source_path: Path
    season: int | None
    episode: int | None
    release_group: str | None
    cues: list[ParsedCue] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    detected_language: str | None = None
    was_translated: bool = False


def parse_episode_from_path(path: Path) -> tuple[int | None, int | None, str | None]:
    for pattern in (EPISODE_FILE_RE, GENERIC_EPISODE_FILE_RE, FLAT_EPISODE_FILE_RE):
        match = pattern.search(path.name)
        if match:
            return int(match.group("season")), int(match.group("episode")), match.group("release") if "release" in match.groupdict() else None
    return None, None, None


def timestamp_to_ms(value: str) -> int:
    value = value.strip().replace(",", ".")
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(".")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(millis.ljust(3, "0")[:3])
    )


def parse_srt_text(text: str) -> tuple[list[ParsedCue], list[str]]:
    errors: list[str] = []
    cues: list[ParsedCue] = []

    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return [], ["empty file"]

    blocks = re.split(r"\n\s*\n", normalized)
    for block_idx, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        cue_index: int | None = None
        ts_line_idx = 0

        if lines[0].isdigit() and len(lines) > 1 and "-->" in lines[1]:
            cue_index = int(lines[0])
            ts_line_idx = 1
        elif "-->" in lines[0]:
            ts_line_idx = 0
        else:
            errors.append(f"block {block_idx}: could not find timestamp")
            continue

        ts_match = TIMESTAMP_LINE_RE.match(lines[ts_line_idx])
        if not ts_match:
            errors.append(f"block {block_idx}: invalid timestamp line")
            continue

        body_lines = lines[ts_line_idx + 1 :]
        text_raw = " ".join(body_lines).strip()
        if not text_raw:
            continue

        watermark = is_watermark_line(text_raw)
        speaker, dialogue = extract_speaker(text_raw)
        text_clean = clean_cue_text(dialogue if speaker else text_raw, for_embed=True)

        if not watermark and not text_clean:
            continue

        cues.append(
            ParsedCue(
                cue_index=cue_index,
                start_ms=timestamp_to_ms(ts_match.group("start")),
                end_ms=timestamp_to_ms(ts_match.group("end")),
                text_raw=text_raw,
                text_clean=text_clean,
                speaker=speaker,
                is_watermark=watermark,
            )
        )

    return cues, errors


def parse_srt_file(path: Path) -> ParsedEpisode:
    season, episode, release = parse_episode_from_path(path)
    episode_obj = ParsedEpisode(
        source_path=path,
        season=season,
        episode=episode,
        release_group=release,
    )

    raw_bytes = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        episode_obj.parse_errors.append("encoding_error")
        return episode_obj

    cues, errors = parse_srt_text(text)
    episode_obj.cues = cues
    episode_obj.parse_errors.extend(errors)
    return episode_obj
