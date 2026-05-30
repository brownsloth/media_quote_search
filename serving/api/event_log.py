"""Append-only JSONL event log for queries and feedback."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from dropbox_log import append_line as dropbox_append_line

_lock = threading.Lock()


def _log_path() -> Path:
    raw = os.environ.get("EVENT_LOG_PATH", "/tmp/quote_memory_events.jsonl")
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_event(event_type: str, payload: dict) -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        **payload,
    }
    line = json.dumps(row, ensure_ascii=False) + "\n"
    path = _log_path()
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    print(f"event {event_type}: {line.strip()}", flush=True)
    dropbox_append_line(line, event_type=event_type)
