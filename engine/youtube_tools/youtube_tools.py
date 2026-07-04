from collections.abc import Callable

from pytubefix import YouTube as PyYT
from pytubefix import Playlist

from engine.errors.errors_handler import ItagDoesNotExist
from engine.service.audio import parse_bitrate_kbps


DownloadProgressFunc = Callable[[int], None]


class YouTube(PyYT):
    """
    Объект PyYT с дополнительными методами для гибкого получения
    кода кач-ва видео Itag.
    """

    def get_video_stream_format_codes(self,
                                      only_video=True,
                                      only_with_audio=False,
                                      sorted_by_itag=True,
                                      sorted_by_resolution=True):
        """Получение списка Itag кодов, с возможностью сортировки."""

        video_fmt_streams = self.fmt_streams

        def _get_only_video_type(items: list) -> list:
            return list(
                filter(lambda v: v.type == 'video', items)
            )

        def _get_only_streams_with_audio(items: list) -> list:
            return list(
                filter(lambda v: bool(getattr(v, 'includes_audio_track', False)), items)
            )

        def _sorted_by_itag(items: list) -> list:
            return list(
                sorted(items, key=lambda obj: obj.itag)
            )

        def _sorted_by_resolution(items: list) -> list:
            def _resolution_value(obj) -> int:
                if obj.resolution is None:
                    return 0
                return int(obj.resolution.removesuffix('p'))

            return list(
                sorted(
                    items,
                    key=_resolution_value,
                    reverse=True
                )
            )

        if only_video:
            video_fmt_streams = _get_only_video_type(video_fmt_streams)

        if only_with_audio:
            video_fmt_streams = _get_only_streams_with_audio(video_fmt_streams)

        if sorted_by_itag:
            video_fmt_streams = _sorted_by_itag(video_fmt_streams)

        if sorted_by_resolution:
            video_fmt_streams = _sorted_by_resolution(video_fmt_streams)

        return video_fmt_streams

    def __str__(self):
        return self.title


class DownloadYTAudio:
    """Загружает аудио-дорожку с PyYT."""

    def __init__(self, video: YouTube) -> None:
        self.video = video

    def download(
        self,
        stream,
        save_to: str,
        filename: str | None = None,
        interrupt_checker=None,
        progress_callback: DownloadProgressFunc | None = None,
    ) -> str | None:
        """Загрузка выбранного audio-only stream."""
        return download_stream(
            video=self.video,
            stream=stream,
            save_to=save_to,
            filename=filename,
            interrupt_checker=interrupt_checker,
            progress_callback=progress_callback,
        )


def download_stream(
    *,
    video: YouTube,
    stream,
    save_to: str,
    filename: str | None = None,
    interrupt_checker=None,
    progress_callback: DownloadProgressFunc | None = None,
) -> str | None:
    kwargs = {"output_path": save_to}
    if filename is not None:
        kwargs["filename"] = filename
    if interrupt_checker is not None:
        kwargs["interrupt_checker"] = interrupt_checker

    if progress_callback is None:
        return stream.download(**kwargs)

    previous_callback = getattr(video.stream_monostate, "on_progress", None)
    last_percent = -1

    def on_progress(current_stream, _chunk: bytes, bytes_remaining: int) -> None:
        nonlocal last_percent

        filesize = int(getattr(current_stream, "filesize", 0) or 0)
        if filesize <= 0:
            return

        downloaded = max(0, filesize - int(bytes_remaining))
        percent = min(100, max(0, int(downloaded / filesize * 100)))
        if percent == 100 or percent > last_percent:
            last_percent = percent
            progress_callback(percent)

    progress_callback(0)
    video.register_on_progress_callback(on_progress)
    try:
        result = stream.download(**kwargs)
    finally:
        video.register_on_progress_callback(previous_callback)

    if result is not None:
        progress_callback(100)

    return result


def get_video_streams_no_higher_than(video: YouTube, max_resolution: int) -> list:
    streams = [
        stream
        for stream in video.get_video_stream_format_codes(
            only_video=True,
            only_with_audio=False,
            sorted_by_itag=False,
            sorted_by_resolution=False,
        )
        if _stream_resolution_value(stream) is not None
        and _stream_resolution_value(stream) <= max_resolution
    ]

    return sorted(
        streams,
        key=lambda stream: (
            _stream_resolution_value(stream) or 0,
            int(getattr(stream, "subtype", "") == "mp4"),
            _stream_fps_value(stream),
            getattr(stream, "itag", 0),
        ),
        reverse=True,
    )


def get_best_video_stream_no_higher_than(video: YouTube, max_resolution: int):
    streams = get_video_streams_no_higher_than(video, max_resolution)
    if not streams:
        raise ItagDoesNotExist(
            f'У видео нет видеопотоков не выше {max_resolution}p.'
        )

    return streams[0]


def get_audio_streams(video: YouTube) -> list:
    streams = [
        stream
        for stream in video.fmt_streams
        if stream.type == 'audio'
    ]

    return sorted(
        streams,
        key=lambda stream: parse_bitrate_kbps(getattr(stream, 'abr', None)) or 0,
        reverse=True,
    )


def _stream_resolution_value(stream) -> int | None:
    resolution = getattr(stream, "resolution", None)
    if resolution is None:
        return None

    try:
        return int(str(resolution).removesuffix("p"))
    except ValueError:
        return None


def _stream_fps_value(stream) -> int:
    try:
        return int(getattr(stream, "fps", 0) or 0)
    except (TypeError, ValueError):
        return 0
