from pytube import YouTube as PyYT
from pytube import Playlist

from engine.service.logger import logger

from engine.errors.errors_handler import ItagDoesNotExist, EmptyPlaylist


class YouTube(PyYT):
    """
    Объект PyYT с дополнительными методами для гибкого получения
    кода кач-ва видео Itag.
    """

    def get_video_stream_format_codes(self,
                                      type='only_video',
                                      sorted_by_itag=True,
                                      sorted_by_resolution=True):
        """Получение списка Itag кодов, с возможностью сортировки."""

        video_fmt_streams = self.fmt_streams

        def _get_only_video_type(items: list) -> list:
            return list(
                filter(lambda v: v.type == 'video', items)
            )

        def _get_only_audio_type(items: list) -> list:
            return list(
                filter(lambda v: v.type == 'audio', items)
            )

        def _sorted_by_itag(items: list) -> list:
            return list(
                sorted(items, key=lambda obj: obj.itag)
            )

        def _sorted_by_resolution(items: list) -> list:
            return list(
                sorted(
                    items,
                    key=lambda obj: int(obj.resolution[:-1]),
                    reverse=True
                )
            )

        if type == 'only_video':
            video_fmt_streams = _get_only_video_type(video_fmt_streams)

            if sorted_by_itag:
                video_fmt_streams = _sorted_by_itag(video_fmt_streams)

            if sorted_by_resolution:
                video_fmt_streams = _sorted_by_resolution(video_fmt_streams)

        elif type == 'only_audio':
            video_fmt_streams = _get_only_audio_type(video_fmt_streams)

        return video_fmt_streams

    def get_best_quality_itag(self) -> int:
        """Itag лучшего кач-ва из возможных."""
        return self.get_video_stream_format_codes()[0].itag

    def get_resolution_itag(self, resolution: int) -> int:
        """
        Возвращает Itag, соответствующий разрешению.
        Если существует.
        Примеры: '2160', '1440', '1080', '720'.
        """

        itags = list(
            filter(
                lambda stream: stream.resolution == f'{resolution}p',
                self.get_video_stream_format_codes()
            )
        )
        if itags:
            return itags[0].itag
        else:
            raise ItagDoesNotExist(
                f'У видео нет значения Itag для {resolution}'
            )

    def __str__(self):
        return self.title


class DownloadYTVideo:
    """Загружает видео с PyYT."""

    def __init__(self, video: YouTube) -> None:
        self.video = video

    def download(self, resolution: int, save_to: str) -> None:
        """Загрузка одиночного видео."""
        itag = get_resolution_itag(resolution=resolution,
                                   video=self.video)
        stream = self.video.streams.get_by_itag(itag)
        stream.download(save_to)

    def download_audio(self, save_to: str) -> None:
        """Загрузка одиночного видео."""
        itag = self.video.get_video_stream_format_codes(type='only_audio')
        best_quality_itag = get_best_quality_audio_itag(itag)
        stream = self.video.streams.get_by_itag(best_quality_itag)
        self.video.default_filename = stream.default_filename
        stream.download(save_to)


class DownloadYTPlaylist:

    def __init__(self, playlist_url: str) -> None:
        self._yt_list = Playlist(url=playlist_url)
        self.playlist = self._create_yt_playlist(self._yt_list)
        self.playlist_title = self._yt_list.title

    @staticmethod
    def _create_yt_playlist(yt_list: Playlist) -> list:
        video_list = [YouTube(url=v) for v in yt_list]
        if video_list:
            return video_list
        else:
            raise EmptyPlaylist('Плейлист пуст.')

    def download(self, resolution: int, save_to: str) -> None:
        for v in self.playlist:
            video = DownloadYTVideo(v)
            video.download(resolution=resolution, save_to=save_to)


def get_resolution_itag(resolution: int, video: YouTube) -> int:
    try:
        itag = video.get_resolution_itag(resolution)
    except ItagDoesNotExist:
        itag = video.get_best_quality_itag()
        logger.warning(f'Разрешение {resolution} недоступно.')
        logger.info(f'Установлено лучшее качество.')
    return itag


def get_best_quality_audio_itag(itags: list) -> int:
    """Возвращает лучшего качествао Itag audio."""
    itag = list(sorted(itags, key=lambda stream: stream.bitrate, reverse=True))
    return itag[0].itag
