import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget
from unittest.mock import Mock, patch

from engine.domain.download_history import DownloadRecord
from engine.domain.modes import AUDIO_MODE, VIDEO_MODE
from engine.gui.workers import DownloadWorker, OverwriteRequest
from engine.gui.app import MainWindow
from engine.service.config import AppConfig


class SignalStub:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class ThreadStub:
    def __init__(self, *args, **kwargs):
        self.started = SignalStub()
        self.finished = SignalStub()

    def start(self):
        pass

    def quit(self):
        pass

    def deleteLater(self):
        pass


class WorkerStub:
    def __init__(self):
        self.log_message = SignalStub()
        self.status_message = SignalStub()
        self.progress_changed = SignalStub()
        self.progress_busy = SignalStub()
        self.overwrite_requested = SignalStub()
        self.finished = SignalStub()

    def moveToThread(self, thread):
        pass

    def run(self):
        pass

    def deleteLater(self):
        pass


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_has_video_audio_playlist_and_settings_tabs(self):
        window = MainWindow()

        tabs = window.findChild(QTabWidget)

        self.assertEqual(tabs.count(), 4)
        self.assertEqual(tabs.tabText(0), "Видео")
        self.assertEqual(tabs.tabText(1), "Аудио")
        self.assertEqual(tabs.tabText(2), "Плейлист")
        self.assertEqual(tabs.tabText(3), "Настройки")

    def test_playlist_tab_can_select_video_or_audio_mode(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        playlist_tab = tabs.widget(2)

        self.assertTrue(playlist_tab.is_playlist)
        self.assertEqual(playlist_tab.mode, VIDEO_MODE)

        playlist_tab.media_type_select.setCurrentIndex(1)

        self.assertEqual(playlist_tab.mode, AUDIO_MODE)
        self.assertIsNone(playlist_tab.video_quality_value())

    def test_audio_bulk_field_is_passed_to_worker_and_single_url_is_ignored(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        audio_tab.url_input.setText("")
        audio_tab.bulk_urls_input.setPlainText("https://one\n\n https://two ")

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_tab.output_dir_input.setText(temp_dir)
            worker = WorkerStub()
            thread = ThreadStub()
            with (
                patch("engine.gui.app.DownloadWorker", return_value=worker) as worker_class,
                patch("engine.gui.app.QThread", return_value=thread),
            ):
                window.start_download(audio_tab)

        self.assertEqual(worker_class.call_args.kwargs["url"], "")
        self.assertEqual(
            worker_class.call_args.kwargs["bulk_urls"],
            ["https://one", "https://two"],
        )
        self.assertEqual(worker_class.call_args.kwargs["mode"], AUDIO_MODE)

    def test_settings_tab_saves_worker_limit(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        settings_tab = tabs.widget(3)
        settings_tab.worker_limit_select.setCurrentIndex(5)
        saved_config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            full_auto=True,
            worker_limit=6,
        )

        with (
            patch("engine.gui.app.save_worker_limit") as save_worker_limit,
            patch("engine.gui.app.load_config", return_value=saved_config),
        ):
            settings_tab.save_settings()

        save_worker_limit.assert_called_once_with(6)
        self.assertIs(window.config, saved_config)
        self.assertEqual(settings_tab.status_label.text(), "Сохранено")

    def test_download_finish_keeps_thread_until_thread_finished(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        thread = QThread(window)
        worker = object()
        audio_tab.prepare_for_download()
        window.active_thread = thread
        window.active_worker = worker
        window.active_tab = audio_tab

        window._download_finished(0)

        self.assertIs(window.active_thread, thread)
        self.assertIs(window.active_worker, worker)
        self.assertIs(window.active_tab, audio_tab)
        self.assertTrue(audio_tab.download_button.isEnabled())
        self.assertEqual(audio_tab.status_label.text(), "Готово")
        self.assertFalse(audio_tab.show_output_button.isHidden())

        window._thread_finished()

        self.assertIsNone(window.active_thread)
        self.assertIsNone(window.active_worker)
        self.assertIsNone(window.active_tab)

    def test_download_finish_shows_total_elapsed_time_under_logs(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        window.active_tab = audio_tab

        with patch("engine.gui.app.time.perf_counter", side_effect=[100.0, 165.0]):
            audio_tab.prepare_for_download()
            self.assertEqual(audio_tab.elapsed_label.text(), "Общее время выполнения: 00:00")

            window._download_finished(0)

        self.assertEqual(audio_tab.elapsed_label.text(), "Общее время выполнения: 01:05")
        self.assertIsNone(audio_tab.started_at)

    def test_request_cancel_requires_confirmation(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        worker = Mock()
        window.active_worker = worker
        window.active_tab = audio_tab

        with patch(
            "engine.gui.app.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            window.request_cancel(audio_tab)

        worker.cancel.assert_not_called()

    def test_request_cancel_calls_worker_cancel_after_confirmation(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        worker = Mock()
        window.active_worker = worker
        window.active_tab = audio_tab
        audio_tab.prepare_for_download()

        with patch(
            "engine.gui.app.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            window.request_cancel(audio_tab)

        worker.cancel.assert_called_once()
        self.assertFalse(audio_tab.cancel_button.isEnabled())
        self.assertIn("Пользователь подтвердил отмену.", audio_tab.log_output.toPlainText())

    def test_cancelled_finish_sets_cancelled_status(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)
        audio_tab.prepare_for_download()
        window.active_tab = audio_tab

        window._download_finished(DownloadWorker.CANCELLED)

        self.assertTrue(audio_tab.download_button.isEnabled())
        self.assertFalse(audio_tab.cancel_button.isEnabled())
        self.assertEqual(audio_tab.status_label.text(), "Отменено")
        self.assertTrue(audio_tab.show_output_button.isHidden())

    def test_show_output_button_opens_selected_directory(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        audio_tab = tabs.widget(1)

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_tab.output_dir_input.setText(temp_dir)

            with patch("engine.gui.app.QDesktopServices.openUrl") as open_url:
                audio_tab.open_output_dir()

            url = open_url.call_args.args[0]

        self.assertEqual(Path(url.toLocalFile()), Path(temp_dir).resolve())

    def test_confirm_overwrite_dialog_resolves_request(self):
        window = MainWindow()
        request = OverwriteRequest(
            existing_record=DownloadRecord(
                video_id="abc123",
                media_type="video",
                title="Title",
                output_path=Path("content/Title.mp4"),
                source_url="https://youtu.be/abc123",
                video_resolution=1080,
                video_itag=137,
                audio_bitrate=160,
                audio_itag=251,
                output_bitrate=160,
                container="mp4",
                downloaded_at="2026-07-04T12:00:00+00:00",
            ),
            planned_record=DownloadRecord(
                video_id="abc123",
                media_type="video",
                title="Title",
                output_path=Path("content/Title.mp4"),
                source_url="https://youtu.be/abc123",
                video_resolution=720,
                video_itag=136,
                audio_bitrate=128,
                audio_itag=140,
                output_bitrate=128,
                container="mp4",
            ),
        )

        with patch(
            "engine.gui.app.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question:
            window._confirm_overwrite(request)

        message = question.call_args.args[2]
        self.assertTrue(request.accepted)
        self.assertTrue(request.event.is_set())
        self.assertIn("Качество в истории: 1080p", message)
        self.assertIn("Текущее выбранное качество: 720p", message)

    def test_playlist_worker_routes_to_playlist_downloader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = AppConfig(
                download_dir=Path("content"),
                audio_download_dir=Path("content/audio"),
                default_video_quality=720,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
                full_auto=True,
                worker_limit=5,
            )
            worker = DownloadWorker(
                mode=AUDIO_MODE,
                url="https://www.youtube.com/playlist?list=123",
                output_dir=output_dir,
                is_playlist=True,
            )

            with (
                patch("engine.gui.workers.load_config", return_value=config),
                patch("engine.gui.workers.SQLiteDownloadHistory.default", return_value=object()),
                patch("engine.gui.workers.Playlist", return_value=object()) as playlist,
                patch("engine.gui.workers.download_playlist", return_value=0) as download_playlist,
            ):
                result = worker._run_download()

        self.assertEqual(result, 0)
        playlist.assert_called_once_with("https://www.youtube.com/playlist?list=123")
        download_playlist.assert_called_once()
        self.assertEqual(download_playlist.call_args.kwargs["media_mode"], AUDIO_MODE)
        self.assertEqual(download_playlist.call_args.kwargs["config"].audio_download_dir, output_dir)
        self.assertEqual(download_playlist.call_args.kwargs["config"].worker_limit, 5)
        self.assertIs(download_playlist.call_args.kwargs["cancel_token"], worker.cancel_token)

    def test_audio_bulk_worker_routes_to_bulk_downloader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = AppConfig(
                download_dir=Path("content"),
                audio_download_dir=Path("content/audio"),
                default_video_quality=720,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
                full_auto=True,
                worker_limit=4,
            )
            worker = DownloadWorker(
                mode=AUDIO_MODE,
                url="",
                output_dir=output_dir,
                bulk_urls=["one", "two"],
            )

            with (
                patch("engine.gui.workers.load_config", return_value=config),
                patch("engine.gui.workers.SQLiteDownloadHistory.default", return_value=object()),
                patch("engine.gui.workers.YouTube") as youtube,
                patch("engine.gui.workers.download_audio_bulk", return_value=0) as download_audio_bulk,
            ):
                result = worker._run_download()

        self.assertEqual(result, 0)
        youtube.assert_not_called()
        download_audio_bulk.assert_called_once()
        self.assertEqual(download_audio_bulk.call_args.kwargs["urls"], ["one", "two"])
        self.assertEqual(download_audio_bulk.call_args.kwargs["config"].audio_download_dir, output_dir)
        self.assertIs(download_audio_bulk.call_args.kwargs["cancel_token"], worker.cancel_token)


if __name__ == "__main__":
    unittest.main()
