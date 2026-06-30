import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


PLATFORMS = {
    "yt": "https://studio.youtube.com",
    "ig": "https://www.instagram.com/accounts/login/",
}


def capture(platform: str, output_dir: str) -> None:
    url = PLATFORMS[platform]
    out_path = Path(output_dir) / f"{platform}_cookies.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        input(
            f"[{platform}] Log in fully, complete any 2FA/checks, "
            "confirm the page is usable, then press Enter here..."
        )
        ctx.storage_state(path=str(out_path))
        browser.close()

    print(f"Saved {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Playwright auth cookies.")
    parser.add_argument("platform", choices=sorted(PLATFORMS))
    parser.add_argument("--output-dir", default=".", help="Directory for *_cookies.json")
    args = parser.parse_args()
    capture(args.platform, args.output_dir)


if __name__ == "__main__":
    main()

