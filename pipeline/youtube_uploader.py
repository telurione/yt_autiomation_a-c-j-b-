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


def _assert_logged_in(page) -> None:
    if re.search(r"/signin|accounts\.google\.com", page.url):
        raise CookieAuthError("YouTube cookies are expired; capture fresh yt_cookies.json.")
    sign_in = page.locator("text=/sign in/i").first
    if sign_in.count() and sign_in.is_visible(timeout=1000):
        raise CookieAuthError("YouTube cookies are expired; sign-in prompt is visible.")


def publish(video_path: str, title: str, desc: str, hashtags: str) -> None:
    ensure_cookie_file(COOKIE_PATH, "YouTube")
    full_desc = f"{desc or ''}\n\n{hashtags or ''}".strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = make_context(browser, COOKIE_PATH)
        page = ctx.new_page()

        try:
            page.goto("https://studio.youtube.com", wait_until="networkidle", timeout=60000)
            human_gap(4, 9)
            _assert_logged_in(page)

            click_first(page, ["#create-icon", "ytcp-button#create-icon"])
            human_gap()
            click_first(page, ["text=Upload videos", "tp-yt-paper-item:has-text('Upload videos')"])
            human_gap()

            page.set_input_files("input[type=file]", video_path)
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
            log.exception("YouTube upload failed. Screenshot saved to %s", shot)
            raise
        finally:
            browser.close()

