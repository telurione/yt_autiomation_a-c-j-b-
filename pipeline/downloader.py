import os
import subprocess
import uuid


def fetch(url: str) -> str:
    out_dir = "/tmp/videos"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{uuid.uuid4().hex}.mp4")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bv*[height<=1920]+ba/b[height<=1920]",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        "300M",
        "-o",
        out_path,
        url,
    ]
    subprocess.run(cmd, check=True)
    return out_path

