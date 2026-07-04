import subprocess
from collections.abc import Callable
from pathlib import Path

from engine.service.audio import choose_mp3_bitrate, resolve_ffmpeg_executable
from engine.service.cancellation import CancellationToken, OperationCancelled


class VideoMergeError(RuntimeError):
    pass


ProgressFunc = Callable[[str], None]


def merge_video_and_audio_to_mp4(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    source_audio_bitrate_kbps: int | None,
    max_audio_bitrate_kbps: int,
    ffmpeg_path: str = "ffmpeg",
    transcode_video: bool = False,
    duration_seconds: int | float | None = None,
    progress_callback: ProgressFunc | None = None,
    cancel_token: CancellationToken | None = None,
) -> Path:
    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_bitrate = choose_mp3_bitrate(
        source_bitrate_kbps=source_audio_bitrate_kbps,
        max_bitrate_kbps=max_audio_bitrate_kbps,
    )
    command = [
        resolve_ffmpeg_executable(ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264" if transcode_video else "copy",
    ]
    if transcode_video:
        command.extend(["-preset", "veryfast", "-crf", "18"])

    command.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate}k",
            "-shortest",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_path),
        ]
    )

    _emit_progress(progress_callback, "FFmpeg: старт склейки в MP4.")
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
                    raise OperationCancelled("Сборка MP4 отменена.")

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
        raise OperationCancelled("Сборка MP4 отменена.")

    if return_code != 0:
        message = "\n".join(output_lines[-20:]).strip()
        raise VideoMergeError(message or f"FFmpeg failed with exit code {return_code}")

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
