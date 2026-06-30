import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse


log = logging.getLogger(__name__)

COOKIE_SOURCES = {
    "instagram.com": ".secrets/ig_cookies.json",
    "youtube.com": ".secrets/yt_cookies.json",
    "youtu.be": ".secrets/yt_cookies.json",
}


def _cookie_source_for_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    for domain, cookie_path in COOKIE_SOURCES.items():
        if host == domain or host.endswith(f".{domain}"):
            return cookie_path
    return None


def _as_bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def _storage_state_to_netscape(storage_state_path: str) -> str | None:
    if not os.path.exists(storage_state_path):
        return None

    with open(storage_state_path, "r", encoding="utf-8") as fh:
        state = json.load(fh)

    cookies = state.get("cookies", [])
    if not cookies:
        return None

    out_dir = Path("/tmp/yt-dlp-cookies")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(storage_state_path).stem}.txt"

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated from Playwright storage_state for yt-dlp.",
    ]

    for cookie in cookies:
        domain = str(cookie.get("domain", "")).strip()
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", ""))
        if not domain or not name:
            continue

        include_subdomains = domain.startswith(".")
        path = str(cookie.get("path", "/") or "/")
        secure = bool(cookie.get("secure", False))
        http_only = bool(cookie.get("httpOnly", False))
        expires = cookie.get("expires", 0)
        try:
            expires_int = max(0, int(float(expires)))
        except (TypeError, ValueError):
            expires_int = 0

        cookie_domain = f"#HttpOnly_{domain}" if http_only else domain
        lines.append(
            "\t".join(
                [
                    cookie_domain,
                    _as_bool_text(include_subdomains),
                    path,
                    _as_bool_text(secure),
                    str(expires_int),
                    name,
                    value,
                ]
            )
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)


def fetch(url: str) -> str:
    out_dir = "/tmp/videos"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{uuid.uuid4().hex}.mp4")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bv*[height<=1920]+ba/b[height<=1920]",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        "300M",
        "--js-runtimes",
        "deno",
        "--remote-components",
        "ejs:npm",
        "-o",
        out_path,
    ]

    storage_state_path = _cookie_source_for_url(url)
    if storage_state_path:
        cookies_path = _storage_state_to_netscape(storage_state_path)
        if cookies_path:
            log.info("Using authenticated cookies for download from %s", urlparse(url).netloc)
            cmd.extend(["--cookies", cookies_path])

    cmd.append(url)
    subprocess.run(cmd, check=True)
    return out_path
