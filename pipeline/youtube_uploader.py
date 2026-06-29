import logging
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from pipeline.browser_utils import (
    BROWSER_ARGS,
    click_first,
    ensure_cookie_file,
    fill_contenteditable,
    human_gap,
    human_type,
    make_context,
    screenshot,
)
from pipeline.errors import CookieAuthError


log = logging.getLogger(__name__)
COOKIE_PATH = ".secrets/yt_cookies.json"

UPLOAD_INPUT = "input[type='file']"

CREATE_SELECTORS = [
    "ytcp-button#create-icon",
    "#create-icon",
    "ytcp-icon-button#create-icon",
    "button:has-text('Create')",
    "ytcp-button:has-text('Create')",
    "button[aria-label='Create']",
    "[aria-label='Create']",
    "tp-yt-paper-icon-button[aria-label='Create']",
    "yt-icon-button[aria-label='Create']",
]

UPLOAD_VIDEO_SELECTORS = [
    "text=Upload videos",
    "button:has-text('Upload videos')",
    "ytcp-button:has-text('Upload videos')",
    "tp-yt-paper-item:has-text('Upload videos')",
    "yt-formatted-string:has-text('Upload videos')",
    "div[role='menuitem']:has-text('Upload videos')",
]

DASHBOARD_UPLOAD_SELECTORS = [
    "button:has-text('Upload videos')",
    "ytcp-button:has-text('Upload videos')",
    "a:has-text('Upload videos')",
]


def _assert_logged_in(page) -> None:
    if re.search(r"/signin|accounts\.google\.com", page.url):
        raise CookieAuthError("YouTube cookies are expired; capture fresh yt_cookies.json.")
    sign_in = page.locator("text=/sign in/i").first
    if sign_in.count() and sign_in.is_visible(timeout=1000):
        raise CookieAuthError("YouTube cookies are expired; sign-in prompt is visible.")


def _page_state(page) -> str:
    try:
        title = page.title()
    except Exception:
        title = "<unavailable>"
    return f"url={page.url!r}, title={title!r}"


def _wait_for_idle(page, timeout: int = 30000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        log.info("Timed out waiting for network idle; continuing. %s", _page_state(page))


def _dismiss_interruptions(page) -> None:
    selectors = [
        "button:has-text('Not now')",
        "button:has-text('Not Now')",
        "button:has-text('Skip')",
        "button:has-text('Got it')",
        "button:has-text('Dismiss')",
        "button:has-text('Accept all')",
        "ytcp-button:has-text('Not now')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=1000):
                locator.click(timeout=2000)
                human_gap(1, 3)
        except Exception:
            continue


def _try_set_upload_file(page, video_path: str, timeout: int = 5000) -> bool:
    try:
        input_box = page.locator(UPLOAD_INPUT).first
        input_box.wait_for(state="attached", timeout=timeout)
        input_box.set_input_files(video_path)
        return True
    except Exception:
        return False


def _try_dashboard_upload_button(page, video_path: str) -> bool:
    try:
        click_first(page, DASHBOARD_UPLOAD_SELECTORS, timeout=8000)
        human_gap(2, 5)
        return _try_set_upload_file(page, video_path, timeout=15000)
    except Exception:
        return False


def _open_upload_dialog(page, video_path: str) -> None:
    page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=60000)
    _wait_for_idle(page)
    human_gap(4, 9)
    _assert_logged_in(page)
    _dismiss_interruptions(page)

    if _try_set_upload_file(page, video_path):
        return

    if _try_dashboard_upload_button(page, video_path):
        return

    log.info("Upload input not present on Studio home; trying direct YouTube upload route.")
    page.goto("https://www.youtube.com/upload", wait_until="domcontentloaded", timeout=60000)
    _wait_for_idle(page)
    human_gap(4, 9)
    _assert_logged_in(page)
    _dismiss_interruptions(page)

    if _try_set_upload_file(page, video_path, timeout=10000):
        return

    log.info("Direct upload route did not expose file input; clicking Create menu.")
    page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=60000)
    _wait_for_idle(page)
    human_gap(4, 9)
    _assert_logged_in(page)
    _dismiss_interruptions(page)

    click_first(page, CREATE_SELECTORS, timeout=45000)
    human_gap()
    click_first(page, UPLOAD_VIDEO_SELECTORS, timeout=30000)
    human_gap()

    input_box = page.locator(UPLOAD_INPUT).first
    input_box.wait_for(state="attached", timeout=60000)
    input_box.set_input_files(video_path)


def publish(video_path: str, title: str, desc: str, hashtags: str) -> None:
    ensure_cookie_file(COOKIE_PATH, "YouTube")
    full_desc = f"{desc or ''}\n\n{hashtags or ''}".strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = make_context(browser, COOKIE_PATH)
        page = ctx.new_page()

        try:
            _open_upload_dialog(page, video_path)
            human_gap(15, 25)

            title_box = page.locator("#title-textarea #textbox").first
            title_box.wait_for(state="visible", timeout=60000)
            fill_contenteditable(title_box, title or "Untitled repost")
            human_gap()

            desc_box = page.locator("#description-textarea #textbox").first
            desc_box.wait_for(state="visible", timeout=30000)
            desc_box.click()
            human_type(desc_box, full_desc)
            human_gap()

            try:
                click_first(page, ["text=No, it's not made for kids", "tp-yt-paper-radio-button:has-text(\"No, it's not made for kids\")"])
            except PlaywrightTimeoutError:
                log.info("Made-for-kids selector not visible; continuing.")
            human_gap()

            for _ in range(3):
                click_first(page, ["#next-button", "ytcp-button:has-text('Next')"], timeout=30000)
                human_gap(4, 8)

            click_first(page, ["text=Public", "tp-yt-paper-radio-button:has-text('Public')"], timeout=30000)
            human_gap()
            click_first(page, ["#done-button", "ytcp-button:has-text('Done')"], timeout=30000)
            human_gap(5, 10)

            ctx.storage_state(path=COOKIE_PATH)
        except Exception:
            shot = screenshot(page, "youtube-upload-failure")
            log.exception("YouTube upload failed. %s Screenshot saved to %s", _page_state(page), shot)
            raise
        finally:
            browser.close()
