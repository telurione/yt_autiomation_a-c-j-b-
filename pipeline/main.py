import logging
import os
import random
import time

from pipeline import downloader, drive, github_secrets, instagram_uploader, processor, sheets
from pipeline import youtube_uploader
from pipeline.errors import CookieAuthError


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MAX_PER_RUN = 3


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _drive_staging_enabled() -> bool:
    return _truthy(os.environ.get("DRIVE_STAGING_ENABLED"), default=True)


def _is_drive_quota_error(exc: Exception) -> bool:
    message = str(exc)
    return (
        "storageQuotaExceeded" in message
        or "Service Accounts do not have storage quota" in message
    )


def human_gap(lo: int = 60, hi: int = 300) -> None:
    delay = random.randint(lo, hi)
    log.info("Inter-upload gap: %ss", delay)
    time.sleep(delay)


def publish_local_path(row: sheets.Row, local_path: str, mark_uploaded: bool = True) -> None:
    sheets.update_status(row, "uploading")
    youtube_uploader.publish(local_path, row.yt_title, row.yt_desc, row.hashtags)
    github_secrets.refresh_youtube_cookies()
    human_gap()
    instagram_uploader.publish(local_path, row.ig_caption, row.hashtags)
    github_secrets.refresh_instagram_cookies()
    if mark_uploaded:
        sheets.mark_uploaded(row)


def process_pending_rows() -> None:
    rows = sheets.get_pending_rows()[:MAX_PER_RUN]
    log.info("Found %s pending rows", len(rows))

    for i, row in enumerate(rows):
        try:
            sheets.update_status(row, "processing")
            raw_path = downloader.fetch(row.url)
            processed_path = processor.apply_preset(raw_path)

            if not _drive_staging_enabled():
                log.info("Drive staging disabled; uploading row directly.")
                publish_local_path(row, processed_path)
                if i < len(rows) - 1:
                    human_gap()
                continue

            try:
                file_id = drive.upload(processed_path)
                sheets.set_drive_id(row, file_id)
                sheets.update_status(row, "ready")
            except Exception as exc:
                if not _is_drive_quota_error(exc):
                    raise
                log.warning(
                    "Drive upload hit service-account storage quota; uploading row directly."
                )
                publish_local_path(row, processed_path)
                if i < len(rows) - 1:
                    human_gap()
        except CookieAuthError as exc:
            log.exception("Cookie authentication failed; stopping run.")
            sheets.mark_error(row, str(exc))
            raise SystemExit(2) from exc
        except Exception as exc:
            log.exception("Download/process failed for %s", row.url)
            sheets.mark_error(row, str(exc))


def upload_ready_rows() -> None:
    ready_rows = sheets.get_ready_rows()[:MAX_PER_RUN]
    log.info("Found %s ready rows", len(ready_rows))

    for i, row in enumerate(ready_rows):
        try:
            local_path = drive.download(row.drive_file_id)
            publish_local_path(row, local_path, mark_uploaded=False)
            drive.delete(row.drive_file_id)
            sheets.mark_uploaded(row)

            if i < len(ready_rows) - 1:
                human_gap()
        except CookieAuthError as exc:
            log.exception("Cookie authentication failed; stopping run.")
            sheets.mark_error(row, str(exc))
            raise SystemExit(2) from exc
        except Exception as exc:
            log.exception("Upload failed for row %s", row.url)
            sheets.mark_error(row, str(exc))


def main() -> None:
    process_pending_rows()
    upload_ready_rows()


if __name__ == "__main__":
    main()
