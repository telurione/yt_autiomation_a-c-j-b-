import io
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive"]


def _credentials_path() -> str:
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ".secrets/sa.json")


def _service():
    creds = Credentials.from_service_account_file(_credentials_path(), scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def upload(path: str) -> str:
    svc = _service()
    meta = {"name": os.path.basename(path), "parents": [os.environ["DRIVE_FOLDER_ID"]]}
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    file = svc.files().create(body=meta, media_body=media, fields="id").execute()
    return file["id"]


def download(file_id: str) -> str:
    svc = _service()
    os.makedirs("/tmp/videos", exist_ok=True)
    request = svc.files().get_media(fileId=file_id)
    local_path = f"/tmp/videos/{file_id}.mp4"
    with io.FileIO(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return local_path


def delete(file_id: str) -> None:
    _service().files().delete(fileId=file_id).execute()

