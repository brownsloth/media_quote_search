"""OpenSubtitles REST API v1 client (login + search + download)."""

from __future__ import annotations

import gzip
import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "QuoteMemory v1.0"


class OpenSubtitlesError(RuntimeError):
    pass


class OpenSubtitlesClient:
    def __init__(
        self,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        min_interval_sec: float = 1.1,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENSUBTITLES_API_KEY", "")
        self.username = username or os.environ.get("OPENSUBTITLES_USERNAME", "")
        self.password = password or os.environ.get("OPENSUBTITLES_PASSWORD", "")
        if not self.api_key:
            raise OpenSubtitlesError("Set OPENSUBTITLES_API_KEY")
        self._token: str | None = None
        self._last_request = 0.0
        self._min_interval = min_interval_sec
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Api-Key": self.api_key,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._throttle()
        url = f"{API_BASE}{path}"
        resp = self._session.request(method, url, timeout=60, **kwargs)
        if resp.status_code == 429:
            time.sleep(5)
            return self._request(method, path, **kwargs)
        if not resp.ok:
            raise OpenSubtitlesError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            return {}
        return resp.json()

    def login(self) -> str:
        if not self.username or not self.password:
            raise OpenSubtitlesError("Set OPENSUBTITLES_USERNAME and OPENSUBTITLES_PASSWORD for downloads")
        data = self._request(
            "POST",
            "/login",
            json={"username": self.username, "password": self.password},
        )
        token = data.get("token")
        if not token:
            raise OpenSubtitlesError(f"Login failed: {data}")
        self._token = token
        self._session.headers["Authorization"] = f"Bearer {token}"
        return token

    def ensure_login(self) -> None:
        if not self._token:
            self.login()

    def search_episode(
        self,
        *,
        imdb_id: str,
        season: int,
        episode: int,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        params = {
            "imdb_id": imdb_id,
            "season_number": season,
            "episode_number": episode,
            "languages": language,
        }
        data = self._request("GET", "/subtitles", params=params)
        return data.get("data") or []

    def pick_best_subtitle(self, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not items:
            return None

        def score(item: dict[str, Any]) -> tuple[int, int, int]:
            attrs = item.get("attributes") or {}
            fmt = (attrs.get("format") or "").lower()
            hi = 1 if attrs.get("hearing_impaired") else 0
            dl = int(attrs.get("download_count") or 0)
            fmt_rank = 2 if fmt == "srt" else (1 if fmt == "sub" else 0)
            return (fmt_rank, -hi, dl)

        return max(items, key=score)

    def download_subtitle_file(self, file_id: int, dest: Path) -> Path:
        self.ensure_login()
        self._throttle()
        url = f"{API_BASE}/download"
        resp = self._session.post(url, json={"file_id": file_id}, timeout=120)
        if not resp.ok:
            raise OpenSubtitlesError(f"download {file_id} -> {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        link = (payload.get("link") or "").strip()
        if not link:
            raise OpenSubtitlesError(f"No download link for file_id={file_id}: {payload}")

        self._throttle()
        file_resp = self._session.get(link, timeout=120)
        file_resp.raise_for_status()
        raw = file_resp.content

        dest.parent.mkdir(parents=True, exist_ok=True)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        if raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith((".srt", ".sub"))]
                if not names:
                    raise OpenSubtitlesError(f"Zip has no srt/sub: {zf.namelist()}")
                dest.write_bytes(zf.read(names[0]))
        else:
            dest.write_bytes(raw)
        return dest

    def download_episode(
        self,
        *,
        imdb_id: str,
        season: int,
        episode: int,
        dest: Path,
        language: str = "en",
    ) -> dict[str, Any] | None:
        items = self.search_episode(imdb_id=imdb_id, season=season, episode=episode, language=language)
        pick = self.pick_best_subtitle(items)
        if not pick:
            return None
        attrs = pick.get("attributes") or {}
        files = attrs.get("files") or []
        if not files:
            return None
        file_id = int(files[0]["file_id"])
        self.download_subtitle_file(file_id, dest)
        return {
            "file_id": file_id,
            "release": attrs.get("release") or attrs.get("feature_details", {}).get("title"),
            "download_count": attrs.get("download_count"),
        }
