from collections.abc import Callable


ProgressFunc = Callable[[int], None]
MessageProgressFunc = Callable[[str], None]


def ffmpeg_progress_adapter(progress_callback: ProgressFunc | None) -> MessageProgressFunc | None:
    if progress_callback is None:
        return None

    def handle(message: str) -> None:
        if message.startswith("FFmpeg: старт"):
            progress_callback(0)
            return

        if message.startswith("FFmpeg: ") and message.endswith("%"):
            value = message.removeprefix("FFmpeg: ").removesuffix("%")
            if value.isdigit():
                progress_callback(int(value))

    return handle
