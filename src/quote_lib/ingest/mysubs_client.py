"""Scrape English SRTs from my-subs.co (same flow as 29thMay/parse_archer_subtitles.py)."""

from __future__ import annotations

import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://my-subs.co"
LANGUAGE = "English"
EPISODE_HREF_RE = re.compile(r"versions-\d+-(\d+)-(\d+)-[\w-]+-subtitles")


@dataclass
class EpisodeLink:
    season: int
    episode: int
    url: str


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")


def parse_show_page(html: str, *, base_url: str = BASE_URL) -> list[EpisodeLink]:
    soup = BeautifulSoup(html, "html.parser")
    episodes: list[EpisodeLink] = []
    seen: set[tuple[int, int]] = set()

    for a in soup.select("a.list-group-item[href*='-subtitles']"):
        href = a.get("href", "")
        m = EPISODE_HREF_RE.search(href)
        if not m:
            continue
        episode = int(m.group(1))
        season = int(m.group(2))
        key = (season, episode)
        if key in seen:
            continue
        seen.add(key)
        episodes.append(EpisodeLink(season=season, episode=episode, url=urljoin(base_url, href)))

    return sorted(episodes, key=lambda x: (x.season, x.episode))


def pick_download_link(episode_html: str, *, language: str = LANGUAGE, base_url: str = BASE_URL) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(episode_html, "html.parser")
    candidates: list[tuple[str, str, int]] = []

    for box in soup.find_all("div", style=lambda x: x and "background-color: #f5f5f5" in x):
        text = box.get_text(" ", strip=True)
        if f"Language : {language}" not in text and f"Language :  {language}" not in text:
            continue

        version_tag = box.select_one(".version i, .version-hearing i")
        version = version_tag.get_text(strip=True) if version_tag else "unknown"

        dl_match = re.search(r"Downloads\s*:\s*(\d+)", text)
        downloads = int(dl_match.group(1)) if dl_match else 0

        download = box.select_one("a[href^='/downloads/']")
        if download:
            candidates.append((version, urljoin(base_url, download["href"]), downloads))

    if not candidates:
        return None, None

    # Prefer highest download count among English subs
    candidates.sort(key=lambda row: row[2], reverse=True)
    version, url, _ = candidates[0]
    return version, url


def download_subtitle_file(
    session: requests.Session,
    download_page_url: str,
    dest: Path,
    *,
    wait_sec: float = 10.0,
) -> None:
    r = session.get(download_page_url, timeout=30)
    r.raise_for_status()

    m = re.search(r'REAL_URL="([^"]+)"', r.text)
    if not m:
        raise RuntimeError(f"No REAL_URL found for {download_page_url}")

    real_url = urljoin(BASE_URL, m.group(1).replace("\\/", "/"))
    if wait_sec > 0:
        time.sleep(wait_sec)

    r2 = session.get(real_url, timeout=60, headers={"Referer": download_page_url})
    r2.raise_for_status()

    content_start = r2.content[:100].lower()
    if b"<!doctype html" in content_start or b"<html" in content_start:
        raise RuntimeError(f"Got HTML instead of subtitle: {real_url}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r2.content)


def finalize_download(tmp_path: Path, dest: Path) -> None:
    if zipfile.is_zipfile(tmp_path):
        with zipfile.ZipFile(tmp_path, "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".srt", ".sub", ".ass", ".vtt"))]
            if not names:
                raise RuntimeError(f"Zip has no subtitle: {zf.namelist()}")
            dest.write_bytes(zf.read(names[0]))
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.replace(dest)


def fetch_show_page(session: requests.Session, show_url: str) -> str:
    r = session.get(show_url, timeout=(10, 120))
    r.raise_for_status()
    return r.text


def download_episode(
    session: requests.Session,
    link: EpisodeLink,
    dest: Path,
    *,
    wait_sec: float = 10.0,
    pause_sec: float = 2.0,
) -> dict:
    if dest.exists() and dest.stat().st_size > 50:
        return {"status": "skipped", "path": str(dest)}

    ep_page = session.get(link.url, timeout=(10, 60))
    ep_page.raise_for_status()

    version, download_url = pick_download_link(ep_page.text)
    if not download_url:
        return {"status": "not_found", "url": link.url}

    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    download_subtitle_file(session, download_url, tmp_path, wait_sec=wait_sec)
    finalize_download(tmp_path, dest)

    if pause_sec > 0:
        time.sleep(pause_sec)

    return {"status": "ok", "path": str(dest), "version": version, "source_url": link.url}
