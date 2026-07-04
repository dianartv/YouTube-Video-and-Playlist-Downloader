from pytubefix import YouTube as PyYT
from pytubefix import Playlist

from engine.errors.errors_handler import ItagDoesNotExist
from engine.service.audio import parse_bitrate_kbps


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

    def download(self, stream, save_to: str, filename: str | None = None) -> str:
        """Загрузка выбранного audio-only stream."""
        kwargs = {"output_path": save_to}
        if filename is not None:
            kwargs["filename"] = filename

        return stream.download(**kwargs)


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


def get_video_resolutions_no_higher_than(video: YouTube, max_resolution: int) -> list[int]:
    resolutions = []
    for stream in get_video_streams_no_higher_than(video, max_resolution):
        resolution = _stream_resolution_value(stream)
        if resolution is not None and resolution not in resolutions:
            resolutions.append(resolution)

    return resolutions


def get_best_video_stream_no_higher_than(video: YouTube, max_resolution: int):
    streams = get_video_streams_no_higher_than(video, max_resolution)
    if not streams:
        raise ItagDoesNotExist(
            f'У видео нет видеопотоков не выше {max_resolution}p.'
        )

    return streams[0]


def get_best_video_stream_for_resolution(video_streams: list, resolution: int):
    matching_streams = [
        stream
        for stream in video_streams
        if _stream_resolution_value(stream) == resolution
    ]
    if not matching_streams:
        raise ItagDoesNotExist(
            f'У видео нет видеопотока для {resolution}p.'
        )

    return matching_streams[0]


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
