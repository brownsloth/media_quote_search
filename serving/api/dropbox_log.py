"""Append feedback events to a Dropbox JSONL file."""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_client = None
_client_error: str | None = None


def _dropbox_path() -> str:
    return os.environ.get("DROPBOX_FEEDBACK_PATH", "/quote_memory/feedback.jsonl").strip()


def _log_queries_to_dropbox() -> bool:
    return os.environ.get("DROPBOX_LOG_QUERIES", "").strip().lower() in {"1", "true", "yes"}


def _enabled_for(event_type: str) -> bool:
    if not os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip():
        return False
    if event_type == "feedback":
        return True
    return event_type == "query" and _log_queries_to_dropbox()


def _get_client():
    global _client, _client_error
    if _client is not None:
        return _client
    if _client_error is not None:
        return None
    token = os.environ.get("DROPBOX_ACCESS_TOKEN", "").strip()
    if not token:
        _client_error = "missing token"
        return None
    try:
        import dropbox

        _client = dropbox.Dropbox(token)
        _client.users_get_current_account()
        return _client
    except Exception as exc:
        _client_error = str(exc)
        print(f"dropbox init failed: {exc}", flush=True)
        return None


def append_line(line: str, *, event_type: str) -> None:
    if not _enabled_for(event_type):
        return

    def _upload() -> None:
        dbx = _get_client()
        if dbx is None:
            return
        path = _dropbox_path()
        payload = line if line.endswith("\n") else line + "\n"
        try:
            import dropbox as dbx_mod

            with _lock:
                try:
                    _metadata, response = dbx.files_download(path)
                    existing = response.content
                except dbx_mod.exceptions.ApiError as exc:
                    if (
                        exc.error.is_path()
                        and exc.error.get_path().is_not_found()
                    ):
                        existing = b""
                    else:
                        raise
                dbx.files_upload(
                    existing + payload.encode("utf-8"),
                    path,
                    mode=dbx_mod.files.WriteMode.overwrite,
                )
            print(f"dropbox appended {event_type} -> {path}", flush=True)
        except Exception as exc:
            print(f"dropbox append failed ({event_type}): {exc}", flush=True)

    threading.Thread(target=_upload, daemon=True).start()
