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
    _debug_screenshot(page, "instagram-after-dismiss-interruptions")


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


def _open_post_upload_dialog(page) -> None:
    _debug_screenshot(page, "instagram-before-create-click")
    click_first(
        page,
        [
            "svg[aria-label='New post']",
            "svg[aria-label='Create']",
            "a[href='/create/select/']",
            "div[role='button']:has-text('Create')",
            "span:has-text('Create')",
            "text=Create",
        ],
        timeout=30000,
    )
    human_gap(2, 5)
    _debug_screenshot(page, "instagram-after-create-click")

    post_menu_open = _has_visible(
        page,
        [
            "div[role='button']:has-text('Post')",
            "button:has-text('Post')",
            "span:has-text('Post')",
            "text=Post",
        ],
        timeout=1000,
    )

    if not post_menu_open and "/create/select/" in page.url and page.locator("input[type='file']").count():
        _debug_screenshot(page, "instagram-file-input-ready-after-create")
        return

    click_first(
        page,
        [
            "a[href='/create/select/']",
            "div[role='button']:has-text('Post')",
            "button:has-text('Post')",
            "span:has-text('Post')",
            "text=Post",
        ],
        timeout=15000,
    )
    human_gap(2, 5)
    _debug_screenshot(page, "instagram-after-post-click")

    page.locator("input[type='file']").first.wait_for(state="attached", timeout=30000)
    _debug_screenshot(page, "instagram-file-input-ready-after-post")


def _has_visible(page, selectors: list[str], timeout: int = 500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=timeout):
                return True
        except Exception:
            continue
    return False


def _is_publish_destination(url: str) -> bool:
    lowered = url.lower()
    return "/reel/" in lowered or "/p/" in lowered


def _composer_is_open(page) -> bool:
    if "/create/" in page.url:
        return True
    return _has_visible(
        page,
        [
            "input[type='file']",
            "div[role='dialog'] div[role='button']:has-text('Next')",
            "div[role='dialog'] button:has-text('Next')",
            "div[role='dialog'] div[role='button']:has-text('Share')",
            "div[role='dialog'] button:has-text('Share')",
            "div[role='dialog'] textarea[aria-label='Write a caption...']",
            "div[role='dialog'] div[aria-label='Write a caption...']",
        ],
        timeout=200,
    )


def _share_progress_visible(page) -> bool:
    return _has_visible(
        page,
        [
            "text=/Sharing/i",
            "text=/Processing/i",
            "text=/Publishing/i",
            "text=/Preparing/i",
            "[role='progressbar']",
        ],
        timeout=200,
    )


def _wait_for_share_complete(page, timeout: int = 150000) -> None:
    success_selectors = [
        "text=/Your reel has been shared/i",
        "text=/Your post has been shared/i",
        "text=/Your reel was shared/i",
        "text=/Your post was shared/i",
        "text=/Your reel has been posted/i",
        "text=/Your post has been posted/i",
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
    saw_share_progress = False
    composer_closed_polls = 0
    while time.time() < deadline:
        _assert_logged_in(page)

        if _has_visible(page, success_selectors):
            _debug_screenshot(page, "instagram-share-success-toast")
            log.info("Instagram reported the upload as shared.")
            return

        if _has_visible(page, error_selectors):
            raise RuntimeError("Instagram showed an upload error after Share.")

        if _is_publish_destination(page.url):
            _debug_screenshot(page, "instagram-share-success-url")
            log.info("Instagram navigated to the published post: %s", _page_state(page))
            return

        if _share_progress_visible(page):
            if not saw_share_progress:
                saw_share_progress = True
                _debug_screenshot(page, "instagram-share-progress")
                log.info("Instagram entered share progress state. %s", _page_state(page))
            composer_closed_polls = 0
            time.sleep(2)
            continue

        if not _composer_is_open(page):
            composer_closed_polls += 1
            if composer_closed_polls == 1:
                log.info("Instagram composer closed after Share. Waiting for a stable success state.")
            if composer_closed_polls >= 3 and saw_share_progress:
                _debug_screenshot(page, "instagram-share-success-no-toast")
                log.info(
                    "Instagram closed the composer after showing share progress without an explicit success toast."
                )
                return
            if composer_closed_polls >= 6:
                _debug_screenshot(page, "instagram-share-success-fallback")
                log.info(
                    "Instagram kept the composer closed after Share without showing explicit progress or success text; treating this as a likely successful publish."
                )
                return
        else:
            composer_closed_polls = 0

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
            _debug_screenshot(page, "instagram-after-home-load")
            _assert_logged_in(page)
            _debug_screenshot(page, "instagram-after-login-check")
            _dismiss_interruptions(page)
            _debug_screenshot(page, "instagram-home")

            _open_post_upload_dialog(page)

            upload_input = page.locator("input[type='file']").first
            _debug_screenshot(page, "instagram-before-file-input")
            upload_input.wait_for(state="attached", timeout=30000)
            _debug_screenshot(page, "instagram-file-input-attached")
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
                _debug_screenshot(page, "instagram-after-crop-confirm")
            except PlaywrightTimeoutError:
                _debug_screenshot(page, "instagram-crop-confirm-not-shown")

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
            _debug_screenshot(page, "instagram-caption-box-visible")
            caption_box.click()
            human_type(caption_box, full_caption)
            human_gap(4, 10)
            _debug_screenshot(page, "instagram-after-caption-entry")
            _debug_screenshot(page, "instagram-before-share")

            _click_share(page)
            human_gap(5, 10)
            _debug_screenshot(page, "instagram-after-share-click")
            _wait_for_share_complete(page)

            if re.search(r"/accounts/login", page.url):
                raise CookieAuthError("Instagram cookies expired during upload.")

            ctx.storage_state(path=COOKIE_PATH)
            _debug_screenshot(page, "instagram-after-cookie-save")
        except Exception:
            shot = screenshot(page, "instagram-upload-failure")
            log.exception("Instagram upload failed. %s Screenshot saved to %s", _page_state(page), shot)
            raise
        finally:
            browser.close()
