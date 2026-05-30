#!/usr/bin/env python3
"""Smoke-test Dropbox feedback logging (no index/API required)."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "serving" / "api"))

from quote_lib.util.env import load_env

load_env(ROOT / ".env")


def main() -> None:
    token = os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set DROPBOX_ACCESS_TOKEN in .env or env.\n"
            "Dropbox app console → Generate access token (no app key/secret needed for this)."
        )

    try:
        import dropbox
    except ImportError:
        raise SystemExit("pip install dropbox  (or: pip install -r serving/api/requirements.txt)")

    path = os.environ.get("DROPBOX_FEEDBACK_PATH", "/quote_memory/feedback.jsonl").strip()
    dbx = dropbox.Dropbox(token)

    account = dbx.users_get_current_account()
    print(f"Dropbox account: {account.name.display_name} ({account.email})")
    print(f"Target path: {path}")

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "feedback",
        "query": "smoke test query",
        "chunk_id": "smoke_test_chunk",
        "vote": "up",
        "rank": 1,
        "show_title": "Smoke Test",
        "episode_label": "S00E00",
        "note": "delete me — quote_memory smoke test",
    }
    line = json.dumps(row, ensure_ascii=False) + "\n"

    try:
        _meta, response = dbx.files_download(path)
        existing = response.content
        print(f"Existing file: {len(existing)} bytes")
    except dropbox.exceptions.ApiError as exc:
        if exc.error.is_path() and exc.error.get_path().is_not_found():
            existing = b""
            print("Existing file: (none — will create)")
        else:
            raise

    dbx.files_upload(
        existing + line.encode("utf-8"),
        path,
        mode=dropbox.files.WriteMode.overwrite,
    )
    print("Upload OK")

    # Verify round-trip
    time.sleep(0.5)
    _meta, response = dbx.files_download(path)
    tail = response.content.decode("utf-8").strip().splitlines()[-1]
    parsed = json.loads(tail)
    if parsed.get("chunk_id") != "smoke_test_chunk":
        raise SystemExit(f"Verify failed — last line: {tail[:200]}")
    print("Verify OK — last line matches smoke test")
    print(f"\nOpen Dropbox and check: {path}")


if __name__ == "__main__":
    main()
