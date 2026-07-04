import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from engine.service.cancellation import CancellationToken, OperationCancelled


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
    cancel_token: CancellationToken | None = None,
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

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
    if cancel_token is not None:
        return _run_cancellable_ffmpeg(command, output_path, cancel_token)

    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise AudioConversionError(stderr or "FFmpeg failed")

    return output_path


def _run_cancellable_ffmpeg(
    command: list[str],
    output_path: Path,
    cancel_token: CancellationToken,
) -> Path:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cancel_token.register_process(process)
    try:
        while True:
            if cancel_token.is_cancelled():
                _terminate_process(process)
                raise OperationCancelled("Конвертация MP3 отменена.")

            try:
                stdout, stderr = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
    finally:
        cancel_token.unregister_process(process)

    if cancel_token.is_cancelled():
        raise OperationCancelled("Конвертация MP3 отменена.")

    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise AudioConversionError(message or "FFmpeg failed")

    return output_path


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
