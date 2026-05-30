"""
Netflix Shakti / Falcor pathEvaluator client.

Modern body: application/x-www-form-urlencoded
  path=["videos","70171942","title"]&path=...&authURL=...

Netflix often returns HTTP 421 on scripted POST (TLS/bot detection) even when
GET /browse works. Use scripts/data/browser_fetch_archer_episodes.js in Chrome.
"""

from __future__ import annotations

import http.client
import http.cookiejar
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from typing import Any


class ShaktiError(RuntimeError):
    pass


class ShaktiHTTPError(ShaktiError):
    def __init__(self, url: str, status: int, reason: str, body: bytes = b"") -> None:
        self.url = url
        self.status = status
        self.reason = reason
        self.body = body
        snippet = body[:800].decode("utf-8", errors="replace")
        super().__init__(f"HTTP {status} {reason} for {url}\n{snippet}")


BROWSER_FETCH_HELP = """
Netflix blocked the scripted Shakti POST (HTTP 421). Use the browser instead:

  1. Log into netflix.com in Chrome
  2. Open DevTools → Console (on any netflix.com page)
  3. Paste contents of: scripts/data/browser_fetch_archer_episodes.js
  4. Press Enter — downloads archer_episodes.json
  5. Import: python scripts/data/import_netflix_mapping.py ~/Downloads/archer_episodes.json

Tip: copy ALL cookies from DevTools → Network → any netflix request → Cookie header
into NETFLIX_COOKIE (not just NetflixId + SecureNetflixId).
"""


def _debug(msg: str) -> None:
    if os.environ.get("NETFLIX_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
        print(f"[shakti debug] {msg}", flush=True)


def browser_fetch_help() -> str:
    return BROWSER_FETCH_HELP.strip()


def _normalize_auth_url(auth_url: str) -> str:
    auth_url = auth_url.strip()
    if not auth_url:
        return auth_url
    if "\\u" in auth_url or '\\"' in auth_url:
        try:
            auth_url = json.loads(f'"{auth_url}"')
        except json.JSONDecodeError:
            pass
    return str(auth_url).replace("\\/", "/")


def _encode_form_body(paths: list[list[Any]], auth_url: str) -> bytes:
    """CastagnaIT-style raw form body (literal brackets, not urlencoded JSON)."""
    chunks = ["path=" + json.dumps(path, separators=(",", ":")) for path in paths]
    chunks.append("authURL=" + auth_url)
    return "&".join(chunks).encode("utf-8")


def _encode_form_body_encoded(paths: list[list[Any]], auth_url: str) -> bytes:
    pairs = [("path", json.dumps(path, separators=(",", ":"))) for path in paths]
    pairs.append(("authURL", auth_url))
    return urllib.parse.urlencode(pairs).encode("utf-8")


def _encode_json_body(paths: list[list[Any]], auth_url: str) -> bytes:
    return json.dumps({"authURL": auth_url, "paths": paths}, separators=(",", ":")).encode("utf-8")


def _shakti_query_params(*, materialize: bool, with_size: bool) -> dict[str, str]:
    return {
        "drmSystem": "widevine",
        "falcor_server": "0.1.0",
        "withSize": "true" if with_size else "false",
        "materialize": "true" if materialize else "false",
        "routeAPIRequestsThroughFTL": "false",
        "isVolatileBillboardsEnabled": "true",
        "isTop10Supported": "true",
        "original_path": "/shakti/mre/pathEvaluator",
    }


def _build_path_evaluator_url(build_id: str, *, materialize: bool, with_size: bool) -> str:
    params = _shakti_query_params(materialize=materialize, with_size=with_size)
    return (
        f"https://www.netflix.com/api/shakti/{build_id}/pathEvaluator?"
        + urllib.parse.urlencode(params)
    )


def _browser_headers(*, method: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.netflix.com",
        "Referer": "https://www.netflix.com/browse",
        "Connection": "close",
        "x-netflix.nq.stack": "prod",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if method == "POST":
        headers["X-Netflix.client.request.name"] = "pathEvaluator"
    return headers


def _http(
    url: str,
    *,
    cookie: str,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, str]:
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise ShaktiError(f"Invalid URL: {url}")

    headers = _browser_headers(method=method, content_type=content_type)
    headers["Cookie"] = cookie
    body = data or b""
    if body:
        headers["Content-Length"] = str(len(body))

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=60, context=ctx)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        _debug(f"{method} {url} -> {resp.status} ({len(raw)} bytes)")
        if resp.status >= 400:
            raise ShaktiHTTPError(url, resp.status, resp.reason, raw)
        return resp.status, text
    finally:
        conn.close()


def _http_cookie_jar(
    url: str,
    *,
    cookie: str,
    method: str = "POST",
    data: bytes | None = None,
    content_type: str | None = None,
    warmup_url: str = "https://www.netflix.com/browse",
) -> tuple[int, str]:
    """
    GET /browse into a cookie jar, then POST — picks up session cookies Netflix
    sets on page load that are missing from a manual NetflixId export.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = _browser_headers(method="GET")
    headers["Cookie"] = cookie
    req = urllib.request.Request(warmup_url, headers=headers, method="GET")
    with opener.open(req, timeout=60) as resp:
        resp.read()
    _debug(f"cookie jar after browse: {len(list(jar))} cookies")

    post_headers = _browser_headers(method=method, content_type=content_type)
    req = urllib.request.Request(url, data=data, headers=post_headers, method=method)
    with opener.open(req, timeout=60) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        _debug(f"jar POST -> {resp.status} ({len(raw)} bytes)")
        if resp.status >= 400:
            raise ShaktiHTTPError(url, resp.status, resp.reason, raw)
        return resp.status, text


def _http_curl_jar(
    url: str,
    *,
    cookie: str,
    data: bytes,
    content_type: str,
) -> tuple[int, str]:
    if not shutil.which("curl"):
        raise ShaktiError("curl not found")

    with tempfile.TemporaryDirectory() as tmp:
        jar = os.path.join(tmp, "cookies.jar")
        browse_cmd = [
            "curl",
            "-sS",
            "--http1.1",
            "--no-alpn",
            "-c",
            jar,
            "-b",
            cookie,
            "-H",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "https://www.netflix.com/browse",
        ]
        subprocess.run(browse_cmd, capture_output=True, timeout=90, check=False)

        post_cmd = [
            "curl",
            "-sS",
            "--http1.1",
            "--no-alpn",
            "-b",
            jar,
            "-X",
            "POST",
            url,
            "-H",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "-H",
            "Accept: application/json, text/javascript, */*; q=0.01",
            "-H",
            "Origin: https://www.netflix.com",
            "-H",
            "Referer: https://www.netflix.com/browse",
            "-H",
            f"Content-Type: {content_type}",
            "-H",
            "X-Netflix.client.request.name: pathEvaluator",
            "-H",
            "x-netflix.nq.stack: prod",
            "-H",
            "sec-fetch-site: same-origin",
            "-H",
            "sec-fetch-mode: cors",
            "-H",
            "sec-fetch-dest: empty",
            "--data-binary",
            "@-",
            "-w",
            "\n__HTTP_STATUS__%{http_code}",
        ]
        proc = subprocess.run(
            post_cmd, input=data, capture_output=True, timeout=90, check=False
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise ShaktiError(f"curl jar POST failed: {err}")

        out = proc.stdout.decode("utf-8", errors="replace")
        body, status_str = out.rsplit("\n__HTTP_STATUS__", 1)
        status = int(status_str.strip() or "0")
        _debug(f"curl jar POST -> {status} ({len(body)} bytes)")
        if status >= 400:
            raise ShaktiHTTPError(url, status, "curl jar error", body.encode("utf-8"))
        return status, body


def http_request(
    url: str,
    *,
    cookie: str,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
) -> str:
    _, text = _http(
        url, cookie=cookie, method=method, data=data, content_type=content_type
    )
    return text


def http_post_shakti(
    url: str,
    *,
    cookie: str,
    data: bytes,
    content_type: str,
) -> str:
    """POST with cookie-jar warmup, then curl-jar fallback."""
    try:
        _, text = _http_cookie_jar(
            url, cookie=cookie, method="POST", data=data, content_type=content_type
        )
        return text
    except ShaktiHTTPError as e:
        _debug(f"jar POST failed HTTP {e.status}, trying curl jar")
        if shutil.which("curl"):
            _, text = _http_curl_jar(
                url, cookie=cookie, data=data, content_type=content_type
            )
            return text
        raise


def detect_session(cookie: str) -> tuple[str, str]:
    html = http_request("https://www.netflix.com/browse", cookie=cookie)

    build_id = None
    for pattern in (
        r'"BUILD_IDENTIFIER"\s*:\s*"([a-z0-9]+)"',
        r"shakti/([a-z0-9]{6,12})/pathEvaluator",
    ):
        m = re.search(pattern, html)
        if m:
            build_id = m.group(1)
            break
    if not build_id:
        raise ShaktiError("Could not find BUILD_IDENTIFIER — set NETFLIX_BUILD_ID")

    auth_url = None
    for pattern in (
        r'"authURL"\s*:\s*"([^"]+)"',
        r'"authUrl"\s*:\s*"([^"]+)"',
    ):
        m = re.search(pattern, html)
        if m:
            auth_url = m.group(1)
            break
    if not auth_url:
        raise ShaktiError("Could not find authURL — are you logged in?")

    auth_url = _normalize_auth_url(auth_url)
    _debug(f"build_id={build_id} authURL len={len(auth_url)}")
    return build_id, auth_url


def _parse_shakti_response(raw: str, *, label: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise ShaktiError(f"Empty Shakti response ({label})")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ShaktiError(f"Non-JSON Shakti response ({label}): {raw[:500]}") from e
    if isinstance(data, dict) and data.get("status") == "error":
        raise ShaktiError(f"Shakti API error ({label}): {data.get('message', data)}")
    return data


def path_evaluator(
    *,
    cookie: str,
    build_id: str,
    auth_url: str,
    paths: list[list[Any]],
) -> dict:
    attempts: list[tuple[str, bytes, str, bool, bool]] = [
        (
            "form/raw",
            _encode_form_body(paths, auth_url),
            "application/x-www-form-urlencoded",
            True,
            True,
        ),
        (
            "form/encoded",
            _encode_form_body_encoded(paths, auth_url),
            "application/x-www-form-urlencoded",
            True,
            True,
        ),
        (
            "form/compact",
            _encode_form_body(paths, auth_url),
            "application/x-www-form-urlencoded",
            False,
            False,
        ),
        (
            "json/legacy",
            _encode_json_body(paths, auth_url),
            "application/json",
            True,
            True,
        ),
    ]

    errors: list[str] = []
    got_421 = False
    for label, body, content_type, materialize, with_size in attempts:
        url = _build_path_evaluator_url(build_id, materialize=materialize, with_size=with_size)
        _debug(f"try {label} POST {len(body)} bytes")
        try:
            raw = http_post_shakti(
                url, cookie=cookie, data=body, content_type=content_type
            )
            return _parse_shakti_response(raw, label=label)
        except ShaktiHTTPError as e:
            if e.status == 421:
                got_421 = True
            errors.append(f"{label}: HTTP {e.status}")
        except ShaktiError as e:
            errors.append(f"{label}: {e}")

    msg = "All Shakti request formats failed:\n" + "\n".join(errors)
    if got_421:
        msg += "\n\n" + browser_fetch_help()
    raise ShaktiError(msg)


def atom_value(node: Any) -> Any:
    if isinstance(node, dict):
        if node.get("$type") == "atom":
            return node.get("value")
        if "value" in node and len(node) <= 3:
            return node.get("value")
    return node


def deref(graph: dict, node: Any) -> Any:
    if isinstance(node, dict) and node.get("$type") == "ref":
        path = node.get("value") or []
        cur: Any = graph
        for part in path:
            if isinstance(cur, dict):
                cur = cur.get(str(part), cur.get(part))
            else:
                return None
        return cur
    return node


def list_values(node: Any, graph: dict | None = None) -> list[Any]:
    node = deref(graph, node) if graph is not None else node
    if isinstance(node, dict) and node.get("$type") == "list":
        return node.get("values") or []
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        numeric_keys = [k for k in node if str(k).isdigit()]
        if numeric_keys:
            return [node[k] for k in sorted(numeric_keys, key=int)]
    return []


def walk_show_episodes(json_graph: dict, show_id: int) -> dict[str, str]:
    videos = json_graph.get("videos") or {}
    show = videos.get(str(show_id)) or videos.get(show_id) or {}

    season_list = show.get("seasonList") or {}
    seasons_raw = season_list.get("seasons")
    season_entries = list_values(seasons_raw, json_graph)

    out: dict[str, str] = {}
    for season_idx, season_ref in enumerate(season_entries, start=1):
        season_obj = deref(json_graph, season_ref)
        if not isinstance(season_obj, dict):
            sid = atom_value(season_ref.get("id") if isinstance(season_ref, dict) else season_ref)
            if sid is not None:
                season_obj = videos.get(str(sid)) or {}
        season_id = atom_value(season_obj.get("id") if isinstance(season_obj, dict) else None)
        if season_id is None and isinstance(season_ref, dict):
            season_id = atom_value(season_ref.get("id"))
        if season_id is None:
            continue

        season_block = videos.get(str(season_id)) or season_obj or {}
        episodes_raw = season_block.get("episodes") or {}
        if (
            isinstance(episodes_raw, dict)
            and "values" not in episodes_raw
            and episodes_raw.get("$type") != "list"
        ):
            episodes_raw = episodes_raw.get("values") or episodes_raw
        episode_entries = list_values(episodes_raw, json_graph)

        for ep_idx, ep_ref in enumerate(episode_entries, start=1):
            ep_obj = deref(json_graph, ep_ref)
            if not isinstance(ep_obj, dict):
                ep_obj = ep_ref if isinstance(ep_ref, dict) else {}
            ep_id = atom_value(ep_obj.get("id"))
            if ep_id is None and isinstance(ep_ref, dict):
                ep_id = atom_value(ep_ref.get("id"))
            if ep_id is not None:
                out[f"S{season_idx:02d}E{ep_idx:02d}"] = str(ep_id)

    return out


def build_episode_fetch_paths(
    show_id: int | str, *, max_seasons: int = 20, max_episodes: int = 35
) -> list[list[Any]]:
    sid = str(show_id)
    season_range = {"from": 0, "to": max_seasons}
    episode_range = {"from": 0, "to": max_episodes}
    return [
        ["videos", sid, "title"],
        ["videos", sid, "seasonCount"],
        [
            "videos",
            sid,
            "seasonList",
            "seasons",
            season_range,
            ["id", "length", "shortName", "episodes", episode_range, ["id", "title", "shortName"]],
        ],
    ]
