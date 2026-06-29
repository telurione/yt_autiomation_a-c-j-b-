import logging
import os
import random
import re
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from pipeline.errors import CookieAuthError


log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]


def human_gap(lo: float = 3, hi: float = 10) -> None:
    delay = random.uniform(lo, hi)
    log.info("Human-like pause: %.1fs", delay)
    time.sleep(delay)


def human_type(locator: Locator, text: str) -> None:
    for ch in text or "":
        locator.type(ch)
        time.sleep(random.uniform(0.04, 0.16))


def make_context(browser, storage_state: str):
    return browser.new_context(
        storage_state=storage_state,
        viewport={"width": 1366, "height": 768},
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/New_York",
    )


def ensure_cookie_file(path: str, platform: str) -> None:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise CookieAuthError(f"Missing or empty {platform} cookie file: {path}")


def screenshot(page: Page, label: str) -> str:
    Path("screenshots").mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "-", label).strip("-")
    path = f"screenshots/{safe_label}-{int(time.time())}.png"
    page.screenshot(path=path, full_page=True)
    return path


def click_first(page: Page, selectors: list[str], timeout: int = 5000) -> str:
    last_error = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(timeout=timeout)
            return selector
        except Exception as exc:
            last_error = exc
    raise PlaywrightTimeoutError(f"No selector matched: {selectors}. Last error: {last_error}")


def fill_contenteditable(locator: Locator, text: str) -> None:
    locator.click()
    locator.page.keyboard.press("Control+A")
    locator.page.keyboard.press("Delete")
    human_type(locator, text)

