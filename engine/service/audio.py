import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import imageio_ffmpeg

from engine.service.cancellation import CancellationToken, OperationCancelled


class AudioConversionError(RuntimeError):
    pass


ProgressFunc = Callable[[str], None]


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
    duration_seconds: int | float | None = None,
    progress_callback: ProgressFunc | None = None,
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

    should_stream_progress = cancel_token is not None or progress_callback is not None
    command = [
        resolve_ffmpeg_executable(ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate}k",
    ]
    if should_stream_progress:
        command.extend(["-progress", "pipe:1", "-nostats"])
    command.append(str(output_path))

    if should_stream_progress:
        return _run_ffmpeg_with_progress(
            command=command,
            output_path=output_path,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )

    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise AudioConversionError(stderr or "FFmpeg failed")

    return output_path


def _run_ffmpeg_with_progress(
    *,
    command: list[str],
    output_path: Path,
    duration_seconds: int | float | None,
    progress_callback: ProgressFunc | None,
    cancel_token: CancellationToken | None,
) -> Path:
    _emit_progress(progress_callback, "FFmpeg: старт конвертации в MP3.")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if cancel_token is not None:
        cancel_token.register_process(process)

    output_lines: list[str] = []
    last_percent = -1
    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
                if cancel_token is not None and cancel_token.is_cancelled():
                    _terminate_process(process)
                    raise OperationCancelled("Конвертация MP3 отменена.")

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                key, separator, value = line.partition("=")
                if separator != "=":
                    output_lines.append(line)
                    continue

                if key == "out_time_ms":
                    percent = _progress_percent(value, duration_seconds)
                    if percent is not None and (percent == 100 or percent >= last_percent + 5):
                        _emit_progress(progress_callback, f"FFmpeg: {percent}%")
                        last_percent = percent
                elif key == "progress" and value == "end" and last_percent < 100:
                    _emit_progress(progress_callback, "FFmpeg: 100%")

        return_code = process.wait()
    finally:
        if cancel_token is not None:
            cancel_token.unregister_process(process)

    if cancel_token is not None and cancel_token.is_cancelled():
        raise OperationCancelled("Конвертация MP3 отменена.")

    if return_code != 0:
        message = "\n".join(output_lines[-20:]).strip()
        raise AudioConversionError(message or f"FFmpeg failed with exit code {return_code}")

    _emit_progress(progress_callback, f"FFmpeg: файл сохранён: {output_path}")
    return output_path


def _progress_percent(value: str, duration_seconds: int | float | None) -> int | None:
    if not duration_seconds:
        return None

    try:
        out_time_seconds = int(value) / 1_000_000
    except ValueError:
        return None

    return min(100, max(0, int(out_time_seconds / float(duration_seconds) * 100)))


def _emit_progress(progress_callback: ProgressFunc | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
