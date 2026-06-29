import os
import subprocess


WATERMARK_PATH = "assets/watermark.png"


def _has_audio(input_path: str) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        input_path,
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return result.returncode == 0 and "audio" in result.stdout


def apply_preset(input_path: str) -> str:
    if not os.path.exists(WATERMARK_PATH):
        raise FileNotFoundError(
            "Missing assets/watermark.png. Add your square logo there before running."
        )

    output_path = input_path.replace(".mp4", "_processed.mp4")
    video_chain = (
        "[0:v]eq=saturation=1.05:contrast=1.03,"
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30[v0];"
        "[1:v]scale=96:96:force_original_aspect_ratio=decrease,"
        "pad=96:96:(ow-iw)/2:(oh-ih)/2:color=black@0.0,format=rgba[wm];"
        "[v0][wm]overlay=x=W-w-36:y=H-h-36[vout];"
        "[vout]setpts=PTS/1.1[vfinal]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-i",
        WATERMARK_PATH,
        "-filter_complex",
        video_chain,
        "-map",
        "[vfinal]",
    ]

    if _has_audio(input_path):
        cmd.extend(
            [
                "-map",
                "0:a:0",
                "-filter:a",
                "atempo=1.1",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        )
    else:
        cmd.append("-an")

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            output_path,
        ]
    )
    subprocess.run(cmd, check=True)
    os.remove(input_path)
    return output_path
