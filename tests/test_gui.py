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


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_has_video_audio_and_playlist_tabs(self):
        window = MainWindow()

        tabs = window.findChild(QTabWidget)

        self.assertEqual(tabs.count(), 3)
        self.assertEqual(tabs.tabText(0), "Видео")
        self.assertEqual(tabs.tabText(1), "Аудио")
        self.assertEqual(tabs.tabText(2), "Плейлист")

    def test_playlist_tab_can_select_video_or_audio_mode(self):
        window = MainWindow()
        tabs = window.findChild(QTabWidget)
        playlist_tab = tabs.widget(2)

        self.assertTrue(playlist_tab.is_playlist)
        self.assertEqual(playlist_tab.mode, VIDEO_MODE)

        playlist_tab.media_type_select.setCurrentIndex(1)

        self.assertEqual(playlist_tab.mode, AUDIO_MODE)
        self.assertIsNone(playlist_tab.video_quality_value())

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

        window._thread_finished()

        self.assertIsNone(window.active_thread)
        self.assertIsNone(window.active_worker)
        self.assertIsNone(window.active_tab)

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
        self.assertIs(download_playlist.call_args.kwargs["cancel_token"], worker.cancel_token)


if __name__ == "__main__":
    unittest.main()
