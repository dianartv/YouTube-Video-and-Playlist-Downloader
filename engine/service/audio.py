import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg


class AudioConversionError(RuntimeError):
    pass


def parse_bitrate_kbps(value: str | None) -> int | None:
    if not value:
        return None

    match = re.search(r"\d+", value)
    if match is None:
        return None

    return int(match.group())


def choose_mp3_bitrate(
    source_bitrate_kbps: int | None,
    max_bitrate_kbps: int = 320,
) -> int:
    if max_bitrate_kbps <= 0:
        raise ValueError("max_bitrate_kbps must be greater than zero")

    if source_bitrate_kbps is None or source_bitrate_kbps <= 0:
        return max_bitrate_kbps

    return min(source_bitrate_kbps, max_bitrate_kbps)


def resolve_ffmpeg_executable(ffmpeg_path: str = "ffmpeg") -> str:
    configured_path = Path(ffmpeg_path)
    if configured_path.exists():
        return str(configured_path)

    executable = shutil.which(ffmpeg_path)
    if executable is not None:
        return executable

    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_to_mp3(
    input_path: str | Path,
    output_path: str | Path,
    source_bitrate_kbps: int | None,
    max_bitrate_kbps: int = 320,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bitrate = choose_mp3_bitrate(
        source_bitrate_kbps=source_bitrate_kbps,
        max_bitrate_kbps=max_bitrate_kbps,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        resolve_ffmpeg_executable(ffmpeg_path),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate}k",
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AudioConversionError(result.stderr.strip() or "FFmpeg failed")

    return output_path
