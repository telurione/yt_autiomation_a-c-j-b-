import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from pipeline.errors import CookieAuthError


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


def _browser_download_instagram(url: str, out_path: str, storage_state_path: str) -> str:
    if not os.path.exists(storage_state_path):
        raise CookieAuthError(f"Missing Instagram cookie file: {storage_state_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(
            storage_state=storage_state_path,
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()
        try:
            log.info("Falling back to browser-backed Instagram download for %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_load_state("networkidle", timeout=90000)

            if "/accounts/login" in page.url:
                raise CookieAuthError("Instagram cookies are expired for downloader fallback.")

            video_src = None
            selectors = [
                "meta[property='og:video']",
                "meta[property='og:video:secure_url']",
                "video",
            ]
            deadline_ms = 90000
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    locator.wait_for(state="attached", timeout=deadline_ms)
                except Exception:
                    continue

                if selector.startswith("meta"):
                    candidate = locator.get_attribute("content")
                else:
                    candidate = locator.get_attribute("src")
                    if not candidate:
                        candidate = locator.evaluate(
                            "el => el.currentSrc || el.src || el.querySelector('source')?.src || null"
                        )
                if candidate:
                    video_src = candidate
                    break

            if not video_src:
                raise RuntimeError("Could not extract Instagram video URL from browser session.")

            response = context.request.get(video_src, headers={"Referer": "https://www.instagram.com/"}, timeout=90000)
            if not response.ok:
                raise RuntimeError(f"Instagram media request failed with HTTP {response.status}.")

            Path(out_path).write_bytes(response.body())
            return out_path
        finally:
            browser.close()


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

    try:
        subprocess.run(cmd, check=True)
        return out_path
    except subprocess.CalledProcessError:
        host = urlparse(url).netloc.lower()
        if storage_state_path and (host == "instagram.com" or host.endswith(".instagram.com")):
            log.warning("yt-dlp failed for Instagram URL; trying browser-backed fallback.")
            return _browser_download_instagram(url, out_path, storage_state_path)
        raise
