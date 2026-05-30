from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quote_lib.parse.srt import ParsedCue, ParsedEpisode, parse_srt_file

HTML_MARKERS = (b"<!doctype html", b"<html", b"<head>")


@dataclass
class FileAuditRow:
    path: str
    season: int | None
    episode: int | None
    release_group: str | None
    status: str
    file_size_bytes: int
    cue_count: int
    dialogue_cue_count: int
    duration_ms: int | None
    has_watermark: bool
    parse_error_count: int
    error_message: str


def detect_file_status(path: Path, parsed: ParsedEpisode | None = None) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "empty"

    head = path.read_bytes()[:256].lower()
    if any(marker in head for marker in HTML_MARKERS):
        return "html_wrapper"

    if parsed is None:
        parsed = parse_srt_file(path)

    if parsed.parse_errors and "encoding_error" in parsed.parse_errors:
        return "encoding_error"

    dialogue_cues = [c for c in parsed.cues if not c.is_watermark and c.text_clean]
    if not dialogue_cues:
        return "no_dialogue_cues"

    if len(dialogue_cues) < 50:
        return "low_cue_count"

    return "valid_srt"


def audit_srt_file(path: Path) -> FileAuditRow:
    parsed = parse_srt_file(path)
    dialogue_cues = [c for c in parsed.cues if not c.is_watermark and c.text_clean]
    status = detect_file_status(path, parsed)

    duration_ms = None
    if dialogue_cues:
        duration_ms = max(c.end_ms for c in dialogue_cues) - min(c.start_ms for c in dialogue_cues)

    error_message = ""
    if status == "html_wrapper":
        error_message = "File looks like an HTML download page, not SRT."
    elif parsed.parse_errors:
        error_message = "; ".join(parsed.parse_errors[:3])

    return FileAuditRow(
        path=str(path),
        season=parsed.season,
        episode=parsed.episode,
        release_group=parsed.release_group,
        status=status,
        file_size_bytes=path.stat().st_size,
        cue_count=len(parsed.cues),
        dialogue_cue_count=len(dialogue_cues),
        duration_ms=duration_ms,
        has_watermark=any(c.is_watermark for c in parsed.cues),
        parse_error_count=len(parsed.parse_errors),
        error_message=error_message,
    )


def audit_srt_directory(root: Path) -> list[FileAuditRow]:
    files = sorted(root.rglob("*.srt"))
    return [audit_srt_file(path) for path in files]
