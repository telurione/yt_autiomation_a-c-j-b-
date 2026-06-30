import logging
import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from pipeline.browser_utils import (
    BROWSER_ARGS,
    click_first,
    click_visible_text,
    ensure_cookie_file,
    human_gap,
    human_type,
    make_context,
    screenshot,
)
from pipeline.errors import CookieAuthError


log = logging.getLogger(__name__)
COOKIE_PATH = ".secrets/ig_cookies.json"


def _page_state(page) -> str:
    try:
        title = page.title()
    except Exception:
        title = "<unavailable>"
    return f"url={page.url!r}, title={title!r}"


def _debug_screenshot(page, label: str) -> None:
    try:
        path = screenshot(page, label)
        log.info("Instagram debug screenshot saved to %s. %s", path, _page_state(page))
    except Exception as exc:
        log.info("Could not save Instagram debug screenshot %s: %s", label, exc)


def _assert_logged_in(page) -> None:
    if "/accounts/login" in page.url:
        raise CookieAuthError("Instagram cookies are expired; capture fresh ig_cookies.json.")
    login_fields = page.locator("input[name='username'], input[name='password']")
    if login_fields.count():
        raise CookieAuthError("Instagram cookies are expired; login form is visible.")


def _dismiss_interruptions(page) -> None:
    selectors = [
        "button:has-text('Not Now')",
        "button:has-text('Not now')",
        "div[role='button']:has-text('Not Now')",
        "div[role='button']:has-text('Not now')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=1000):
                locator.click(timeout=2000)
                human_gap(1, 3)
        except Exception:
            continue


def _click_next(page) -> None:
    click_first(
        page,
        [
            "div[role='button']:has-text('Next')",
            "button:has-text('Next')",
            "text=Next",
        ],
        timeout=30000,
    )


def _click_share(page) -> None:
    try:
        click_first(
            page,
            [
                "div[role='button']:has-text('Share')",
                "button:has-text('Share')",
                "span:has-text('Share')",
                "xpath=//*[normalize-space()='Share' and not(self::title)]",
            ],
            timeout=10000,
        )
    except PlaywrightTimeoutError:
        click_visible_text(page, "Share", timeout=30000)


def _has_visible(page, selectors: list[str], timeout: int = 500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=timeout):
                return True
        except Exception:
            continue
    return False


def _wait_for_share_complete(page, timeout: int = 150000) -> None:
    success_selectors = [
        "text=/Your reel has been shared/i",
        "text=/Your post has been shared/i",
        "text=/Reel shared/i",
        "text=/Post shared/i",
    ]
    error_selectors = [
        "text=/couldn't share/i",
        "text=/couldn't post/i",
        "text=/try again/i",
        "text=/something went wrong/i",
        "text=/error/i",
    ]
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        _assert_logged_in(page)

        if _has_visible(page, success_selectors):
            log.info("Instagram reported the upload as shared.")
            return

        if _has_visible(page, error_selectors):
            raise RuntimeError("Instagram showed an upload error after Share.")

        time.sleep(2)

    _debug_screenshot(page, "instagram-share-confirm-timeout")
    raise PlaywrightTimeoutError("Instagram did not confirm that the upload was shared.")


def publish(video_path: str, caption: str, hashtags: str) -> None:
    ensure_cookie_file(COOKIE_PATH, "Instagram")
    full_caption = f"{caption or ''}\n\n{hashtags or ''}".strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = make_context(browser, COOKIE_PATH)
        page = ctx.new_page()

        try:
            page.goto("https://www.instagram.com/", wait_until="networkidle", timeout=60000)
            human_gap(5, 11)
            _assert_logged_in(page)
            _dismiss_interruptions(page)
            _debug_screenshot(page, "instagram-home")

            click_first(
                page,
                [
                    "svg[aria-label='New post']",
                    "svg[aria-label='Create']",
                    "a[href='/create/select/']",
                    "div[role='button']:has-text('Create')",
                    "text=Create",
                ],
                timeout=30000,
            )
            human_gap(3, 8)

            upload_input = page.locator("input[type='file']").first
            upload_input.wait_for(state="attached", timeout=30000)
            upload_input.set_input_files(video_path)
            human_gap(12, 22)
            _debug_screenshot(page, "instagram-after-file-selected")

            try:
                click_first(
                    page,
                    [
                        "button:has-text('OK')",
                        "div[role='button']:has-text('OK')",
                        "button:has-text('Select crop')",
                    ],
                    timeout=4000,
                )
                human_gap(2, 5)
            except PlaywrightTimeoutError:
                pass

            _click_next(page)
            human_gap(4, 9)
            _debug_screenshot(page, "instagram-after-first-next")
            _click_next(page)
            human_gap(4, 9)
            _debug_screenshot(page, "instagram-caption-screen")

            caption_box = page.locator(
                "div[aria-label='Write a caption...'], textarea[aria-label='Write a caption...'], div[contenteditable='true']"
            ).first
            caption_box.wait_for(state="visible", timeout=30000)
            caption_box.click()
            human_type(caption_box, full_caption)
            human_gap(4, 10)
            _debug_screenshot(page, "instagram-before-share")

            _click_share(page)
            human_gap(5, 10)
            _debug_screenshot(page, "instagram-after-share-click")
            _wait_for_share_complete(page)

            if re.search(r"/accounts/login", page.url):
                raise CookieAuthError("Instagram cookies expired during upload.")

            ctx.storage_state(path=COOKIE_PATH)
        except Exception:
            shot = screenshot(page, "instagram-upload-failure")
            log.exception("Instagram upload failed. %s Screenshot saved to %s", _page_state(page), shot)
            raise
        finally:
            browser.close()
