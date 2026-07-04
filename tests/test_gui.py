import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget
from unittest.mock import Mock, patch

from engine.domain.download_history import DownloadRecord
from engine.gui.workers import DownloadWorker, OverwriteRequest
from engine.gui.app import MainWindow


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_has_video_and_audio_tabs(self):
        window = MainWindow()

        tabs = window.findChild(QTabWidget)

        self.assertEqual(tabs.count(), 2)
        self.assertEqual(tabs.tabText(0), "Видео")
        self.assertEqual(tabs.tabText(1), "Аудио")

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


if __name__ == "__main__":
    unittest.main()
