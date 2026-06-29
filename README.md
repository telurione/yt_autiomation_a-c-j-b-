# Auto Repost Pipeline

Headless auto-repost pipeline for GitHub Actions, yt-dlp, ffmpeg, Playwright, Google Sheets, and Google Drive.

## Queue Sheet

Create a Google Sheet with these headers:

```text
url, platform_src, status, yt_title, yt_desc, ig_caption, hashtags, drive_file_id, created_at, uploaded_at, error
```

Rows move through:

```text
pending -> processing -> ready -> uploading -> uploaded
                        \-> error       \-> error
```

## Required GitHub Secrets

- `GOOGLE_SA_KEY`: full Google service account JSON
- `YT_COOKIES_JSON`: Playwright storage state for YouTube Studio
- `IG_COOKIES_JSON`: Playwright storage state for Instagram
- `SHEET_ID`: Google Sheet ID
- `DRIVE_FOLDER_ID`: Google Drive staging folder ID
- `GH_PAT`: GitHub PAT used by `gh secret set` to refresh cookie secrets

The PAT should be able to update Actions secrets for the repository. A fine-grained token needs repository access and secret administration capability; a classic PAT usually needs `repo` for private repos.

## Watermark

Add your square logo as `assets/watermark.png`. It is rendered as a tiny square in the bottom-right corner.

## Cookie Capture

Run this locally and paste the resulting JSON files into GitHub Secrets:

```python
from playwright.sync_api import sync_playwright

PLATFORMS = {
    "yt": "https://studio.youtube.com",
    "ig": "https://www.instagram.com/accounts/login/",
}

with sync_playwright() as p:
    for name, url in PLATFORMS.items():
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(url)
        input(f"[{name}] Log in manually, complete any 2FA, then press Enter...")
        ctx.storage_state(path=f"{name}_cookies.json")
        browser.close()
        print(f"Saved {name}_cookies.json")
```

## Runtime Behavior

- Runs twice daily on GitHub Actions with a randomized 0-25 minute workflow jitter.
- Processes up to 3 pending rows per run.
- Uploads ready rows to YouTube first, waits 3-15 minutes, then uploads to Instagram.
- Uses human-like typing, pauses, and Chromium automation-control hardening.
- Stops the workflow if YouTube or Instagram cookies are missing or expired.
- Refreshes `YT_COOKIES_JSON` and `IG_COOKIES_JSON` secrets after successful uploads when `GH_PAT` is present.

## Manual Run

```bash
pip install -r requirements.txt
playwright install chromium
python -m pipeline.main
```

