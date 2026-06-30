import logging
import os
import subprocess


log = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def refresh_enabled() -> bool:
    return _truthy(os.environ.get("COOKIE_REFRESH_ENABLED", "true"))


def update_secret_from_file(secret_name: str, file_path: str) -> bool:
    if not refresh_enabled():
        log.info("Cookie refresh is disabled; not updating %s", secret_name)
        return False

    token = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        log.warning(
            "Cannot refresh %s: GH_PAT or GITHUB_REPOSITORY is missing.",
            secret_name,
        )
        return False

    if not os.path.exists(file_path):
        log.warning("Cannot refresh %s: %s does not exist.", secret_name, file_path)
        return False

    env = os.environ.copy()
    env["GH_TOKEN"] = token
    cmd = ["gh", "secret", "set", secret_name, "--body-file", file_path, "--repo", repo]
    result = subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(
            "Failed to refresh %s via gh secret set: %s",
            secret_name,
            (result.stderr or result.stdout).strip(),
        )
        return False

    log.info("Refreshed GitHub secret %s", secret_name)
    return True


def refresh_cookie_secrets() -> None:
    refresh_youtube_cookies()
    refresh_instagram_cookies()


def refresh_youtube_cookies() -> bool:
    return update_secret_from_file("YT_COOKIES_JSON", ".secrets/yt_cookies.json")


def refresh_instagram_cookies() -> bool:
    return update_secret_from_file("IG_COOKIES_JSON", ".secrets/ig_cookies.json")
