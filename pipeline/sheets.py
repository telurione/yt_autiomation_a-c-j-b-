import os
from dataclasses import dataclass
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ROW_KEYS = [
    "url",
    "platform_src",
    "status",
    "yt_title",
    "yt_desc",
    "ig_caption",
    "hashtags",
    "drive_file_id",
]


@dataclass
class Row:
    idx: int
    url: str
    platform_src: str
    status: str
    yt_title: str
    yt_desc: str
    ig_caption: str
    hashtags: str
    drive_file_id: str


def _credentials_path() -> str:
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ".secrets/sa.json")


def _client():
    creds = Credentials.from_service_account_file(_credentials_path(), scopes=SCOPES)
    return gspread.authorize(creds)


def _sheet():
    return _client().open_by_key(os.environ["SHEET_ID"]).sheet1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_from_record(idx: int, record: dict) -> Row:
    values = {key: str(record.get(key, "") or "").strip() for key in ROW_KEYS}
    return Row(idx=idx, **values)


def _rows_with_status(status: str) -> list[Row]:
    records = _sheet().get_all_records()
    wanted = status.strip().lower()
    rows = []
    for i, record in enumerate(records, start=2):
        row_status = str(record.get("status", "") or "").strip().lower()
        if row_status == wanted:
            rows.append(_row_from_record(i, record))
    return rows


def get_pending_rows() -> list[Row]:
    return _rows_with_status("pending")


def get_ready_rows() -> list[Row]:
    return _rows_with_status("ready")


def update_status(row: Row, status: str) -> None:
    _sheet().update_cell(row.idx, 3, status)
    row.status = status


def set_drive_id(row: Row, file_id: str) -> None:
    _sheet().update_cell(row.idx, 8, file_id)
    row.drive_file_id = file_id


def mark_uploaded(row: Row) -> None:
    sh = _sheet()
    sh.update_cell(row.idx, 3, "uploaded")
    sh.update_cell(row.idx, 10, _utc_now())
    row.status = "uploaded"


def mark_error(row: Row, msg: str) -> None:
    sh = _sheet()
    sh.update_cell(row.idx, 3, "error")
    sh.update_cell(row.idx, 11, str(msg)[:500])
    row.status = "error"

