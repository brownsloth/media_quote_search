"""Build Netflix session cookie from environment variables."""

from __future__ import annotations

import os


def _strip_cookie_prefix(name: str, value: str) -> str:
    value = value.strip().strip('"').strip("'")
    prefix = f"{name}="
    if value.lower().startswith(prefix.lower()):
        return value[len(prefix) :]
    return value


def build_netflix_cookie() -> str:
    """
    Resolve Netflix Cookie header from env.

    Precedence:
      1. NETFLIX_COOKIE — full header value
      2. NETFLIX_ID + SECURE_NETFLIX_ID — assembled automatically

    Use the **exact** Value from Chrome DevTools (usually URL-encoded, e.g. ct%3D…).
    Do not URL-decode — Netflix expects the encoded form.
    """
    explicit = os.environ.get("NETFLIX_COOKIE", "").strip()
    if explicit:
        return explicit

    netflix_id = os.environ.get("NETFLIX_ID", "").strip()
    secure_id = os.environ.get("SECURE_NETFLIX_ID", "").strip()
    if not netflix_id or not secure_id:
        return ""

    netflix_id = _strip_cookie_prefix("NetflixId", netflix_id)
    secure_id = _strip_cookie_prefix("SecureNetflixId", secure_id)
    return f"NetflixId={netflix_id}; SecureNetflixId={secure_id}"


def require_netflix_cookie() -> str:
    cookie = build_netflix_cookie()
    if cookie:
        return cookie
    raise SystemExit(
        "Set Netflix session env vars:\n\n"
        "  export NETFLIX_ID='...'\n"
        "  export SECURE_NETFLIX_ID='...'\n\n"
        "Or the combined form:\n"
        "  export NETFLIX_COOKIE='NetflixId=...; SecureNetflixId=...'\n\n"
        "Copy values from Chrome DevTools → Application → Cookies → netflix.com"
    )
