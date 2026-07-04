import threading
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from pytubefix.exceptions import LiveStreamEnded, LiveStreamError, VideoUnavailable

from engine.application.download_audio import download_audio
from engine.application.download_audio_bulk import download_audio_bulk
from engine.application.download_playlist import download_playlist
from engine.application.download_video import download_video
from engine.domain.download_history import DownloadRecord
from engine.domain.modes import AUDIO_MODE, VIDEO_MODE
from engine.service.cancellation import CancellationToken, OperationCancelled
from engine.service.config import AppConfig, ensure_env_file, load_config
from engine.service.download_history import SQLiteDownloadHistory
from engine.service.logger import configure_file_logger, logger
from engine.youtube_tools.youtube_tools import Playlist, YouTube


@dataclass
class OverwriteRequest:
    existing_record: DownloadRecord
    planned_record: DownloadRecord
    accepted: bool = False
    event: threading.Event = field(default_factory=threading.Event)

    def resolve(self, accepted: bool) -> None:
        self.accepted = accepted
        self.event.set()


class DownloadWorker(QObject):
    log_message = Signal(str)
    status_message = Signal(str)
    progress_changed = Signal(int)
    progress_busy = Signal(bool)
    overwrite_requested = Signal(object)
    finished = Signal(int)
    CANCELLED = 2

    def __init__(
        self,
        *,
        mode: str,
        url: str,
        output_dir: Path,
        video_quality: int | None = None,
        is_playlist: bool = False,
        bulk_urls: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.url = url
        self.output_dir = output_dir
        self.video_quality = video_quality
        self.is_playlist = is_playlist
        self.bulk_urls = [url.strip() for url in bulk_urls or [] if url.strip()]
        self.cancel_token = CancellationToken()

    def cancel(self) -> None:
        self.cancel_token.cancel()
        self.log_message.emit("Запрошена отмена. Останавливаю текущую операцию.")
        self.status_message.emit("Отмена")

    @Slot()
    def run(self) -> None:
        configure_file_logger()
        ensure_env_file()

        try:
            result = self._run_download()
        except LiveStreamError:
            logger.warning(f"Трансляция {self.url} ещё идёт.")
            self._print("Активные live-трансляции не скачиваются. Дождитесь завершения и публикации архива.")
            result = 1
        except LiveStreamEnded:
            logger.warning(f"Архив трансляции {self.url} ещё недоступен.")
            self._print(
                "Трансляция завершилась, но YouTube ещё не отдаёт архив как обычное видео. "
                "Повторите позже."
            )
            result = 1
        except VideoUnavailable:
            logger.warning(f"Видео {self.url} - недоступно.")
            self._print("Видео недоступно.")
            result = 1
        except OperationCancelled:
            self._print("Операция отменена. Удаляю временные файлы текущей загрузки.")
            self.cancel_token.cleanup_paths()
            result = self.CANCELLED
        except Exception as exc:
            logger.exception(f"Не удалось выполнить загрузку из GUI: {exc}")
            self._print(f"Ошибка: {exc}")
            result = 1
        finally:
            if self.cancel_token.is_cancelled():
                self.cancel_token.cleanup_paths()

        if result == self.CANCELLED:
            self.status_message.emit("Отменено")
            self.progress_busy.emit(False)
        elif result == 0:
            self.status_message.emit("Готово")
            self.progress_busy.emit(False)
            self.progress_changed.emit(100)
        else:
            self.status_message.emit("Ошибка")
            self.progress_busy.emit(False)

        self.finished.emit(result)

    def _run_download(self) -> int:
        config = self._build_config(load_config())
        download_history = SQLiteDownloadHistory.default()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.status_message.emit("Получение данных YouTube")
        self.progress_busy.emit(True)
        if self.is_playlist:
            return self._run_playlist_download(config, download_history)
        if self.bulk_urls:
            return self._run_bulk_download(config, download_history)

        video = YouTube(url=self.url)
        self.cancel_token.raise_if_cancelled()
        self._print(f"Видео: {video.title}")

        if self.mode == VIDEO_MODE:
            return download_video(
                video=video,
                config=config,
                print_func=self._print,
                cancel_token=self.cancel_token,
                download_history=download_history,
                confirm_overwrite_func=self._confirm_overwrite,
                progress_callback=self._set_progress,
            )

        if self.mode == AUDIO_MODE:
            return download_audio(
                video=video,
                config=config,
                print_func=self._print,
                cancel_token=self.cancel_token,
                download_history=download_history,
                confirm_overwrite_func=self._confirm_overwrite,
                progress_callback=self._set_progress,
            )

        raise ValueError("mode must be video or audio")

    def _run_bulk_download(self, config: AppConfig, download_history: SQLiteDownloadHistory) -> int:
        if self.mode != AUDIO_MODE:
            raise ValueError("bulk mode supports audio only")

        self.status_message.emit("Скачивание пачки")
        return download_audio_bulk(
            urls=self.bulk_urls,
            config=config,
            print_func=self._print,
            download_history=download_history,
            confirm_overwrite_func=self._confirm_overwrite,
            cancel_token=self.cancel_token,
        )

    def _run_playlist_download(self, config: AppConfig, download_history: SQLiteDownloadHistory) -> int:
        self.status_message.emit("Получение данных плейлиста")
        playlist = Playlist(self.url)
        self.cancel_token.raise_if_cancelled()
        return download_playlist(
            playlist=playlist,
            media_mode=self.mode,
            config=config,
            print_func=self._print,
            download_history=download_history,
            confirm_overwrite_func=self._confirm_overwrite,
            cancel_token=self.cancel_token,
        )

    def _confirm_overwrite(
        self,
        existing_record: DownloadRecord,
        planned_record: DownloadRecord,
    ) -> bool:
        request = OverwriteRequest(
            existing_record=existing_record,
            planned_record=planned_record,
        )
        self.overwrite_requested.emit(request)
        request.event.wait()
        self.cancel_token.raise_if_cancelled()
        return request.accepted

    def _build_config(self, config: AppConfig) -> AppConfig:
        if self.mode == VIDEO_MODE:
            return replace(
                config,
                download_dir=self.output_dir,
                default_video_quality=self.video_quality or config.default_video_quality,
            )

        return replace(
            config,
            audio_download_dir=self.output_dir,
        )

    def _print(self, message: str) -> None:
        self.log_message.emit(message)
        self._update_status_from_log(message)

    def _set_progress(self, percent: int) -> None:
        self.progress_busy.emit(False)
        self.progress_changed.emit(max(0, min(100, int(percent))))

    def _update_status_from_log(self, message: str) -> None:
        if message.startswith("[") and "] " in message:
            message = message.split("] ", 1)[1]

        if message.startswith("Скачиваю"):
            self.status_message.emit("Скачивание")
            self.progress_busy.emit(True)
            return

        if message.startswith("FFmpeg: старт"):
            self.status_message.emit("Конвертация")
            self.progress_busy.emit(False)
            self.progress_changed.emit(0)
            return

        if message.startswith("Конвертирую") or message.startswith("Собираю"):
            self.status_message.emit("Конвертация")
            self.progress_busy.emit(True)
            return

        if message.startswith("FFmpeg: ") and message.endswith("%"):
            value = message.removeprefix("FFmpeg: ").removesuffix("%")
            if value.isdigit():
                self.status_message.emit("Конвертация")
                self.progress_busy.emit(False)
                self.progress_changed.emit(int(value))
            return

        if message.startswith("Готово."):
            self.status_message.emit("Готово")
            self.progress_busy.emit(False)
            self.progress_changed.emit(100)
