import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from engine.application.download_duplicates import format_duplicate_download
from engine.domain.modes import AUDIO_MODE, VIDEO_MODE
from engine.service.config import (
    MAX_DOWNLOAD_WORKER_LIMIT,
    MAX_PROCESS_WORKER_LIMIT,
    MIN_WORKER_LIMIT,
    PROJECT_ROOT,
    ensure_env_file,
    load_config,
    save_parallel_limits,
)
from engine.gui.workers import DownloadWorker


VIDEO_QUALITIES = [144, 240, 360, 480, 720, 1080, 1440]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_env_file()
        self.config = load_config()
        self.active_thread: QThread | None = None
        self.active_worker: DownloadWorker | None = None
        self.active_tab: DownloadTab | None = None

        self.setWindowTitle("YouTube Downloader")
        self.resize(860, 620)

        tabs = QTabWidget()
        tabs.addTab(DownloadTab(mode=VIDEO_MODE, config=self.config, parent_window=self), "Видео")
        tabs.addTab(DownloadTab(mode=AUDIO_MODE, config=self.config, parent_window=self), "Аудио")
        tabs.addTab(
            DownloadTab(
                mode=VIDEO_MODE,
                config=self.config,
                parent_window=self,
                is_playlist=True,
            ),
            "Плейлист",
        )
        tabs.addTab(SettingsTab(config=self.config, parent_window=self), "Настройки")
        self.setCentralWidget(tabs)
        self._apply_style()

    def start_download(self, tab: "DownloadTab") -> None:
        if self.active_thread is not None:
            QMessageBox.warning(self, "Загрузка уже идёт", "Дождитесь завершения текущей загрузки.")
            return

        url = tab.url_value()
        bulk_urls = tab.bulk_urls_value()
        if not url and not bulk_urls:
            QMessageBox.warning(self, "Нет ссылки", "Вставьте ссылку на YouTube.")
            return

        if not tab.output_dir_text():
            QMessageBox.warning(self, "Нет каталога", "Укажите папку для сохранения.")
            return

        output_dir = tab.output_dir_value()
        tab.prepare_for_download()
        worker = DownloadWorker(
            mode=tab.mode,
            url="" if bulk_urls else url,
            output_dir=output_dir,
            video_quality=tab.video_quality_value(),
            is_playlist=tab.is_playlist,
            bulk_urls=bulk_urls,
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log_message.connect(tab.append_log)
        worker.status_message.connect(tab.set_status)
        worker.progress_changed.connect(tab.set_progress)
        worker.progress_busy.connect(tab.set_progress_busy)
        worker.overwrite_requested.connect(self._confirm_overwrite)
        worker.finished.connect(self._download_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.active_thread = thread
        self.active_worker = worker
        self.active_tab = tab
        thread.start()

    def request_cancel(self, tab: "DownloadTab") -> None:
        if self.active_worker is None or self.active_tab is not tab:
            return

        answer = _question_with_russian_buttons(
            self,
            "Отменить загрузку?",
            "Вы уверены? Текущие исходные файлы будут удалены.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        tab.mark_cancel_requested()
        self.active_worker.cancel()

    @Slot(object)
    def _confirm_overwrite(self, request) -> None:
        answer = _question_with_russian_buttons(
            self,
            "Файл уже существует",
            f"{format_duplicate_download(request.existing_record, request.planned_record)}\n\n"
            "Перезаписать?",
        )
        request.resolve(answer == QMessageBox.StandardButton.Yes)

    @Slot(int)
    def _download_finished(self, result: int) -> None:
        if self.active_tab is not None:
            self.active_tab.finish_download(
                success=result == 0,
                cancelled=result == DownloadWorker.CANCELLED,
            )

    @Slot()
    def _thread_finished(self) -> None:
        self.active_thread = None
        self.active_worker = None
        self.active_tab = None

    def closeEvent(self, event) -> None:
        if self.active_thread is not None:
            QMessageBox.warning(self, "Загрузка идёт", "Дождитесь завершения загрузки перед закрытием.")
            event.ignore()
            return

        event.accept()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #ffffff;
                color: #111111;
                font-size: 14px;
            }
            QLineEdit, QComboBox, QPlainTextEdit {
                border: 1px solid #111111;
                border-radius: 4px;
                padding: 6px;
                background: #ffffff;
                color: #111111;
            }
            QPushButton {
                border: 1px solid #111111;
                border-radius: 4px;
                padding: 7px 12px;
                background: #111111;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #777777;
                border-color: #777777;
            }
            QComboBox:focus {
                background: #f2f2f2;
            }
            QComboBox QAbstractItemView {
                selection-background-color: #d9d9d9;
                selection-color: #111111;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #d9d9d9;
                color: #111111;
            }
            QProgressBar {
                border: 1px solid #111111;
                border-radius: 4px;
                min-height: 18px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #111111;
            }
            QTabWidget::pane {
                border: 1px solid #111111;
                padding: 8px;
            }
            QTabBar::tab {
                border: 1px solid #111111;
                padding: 7px 16px;
                background: #ffffff;
            }
            QTabBar::tab:selected {
                background: #111111;
                color: #ffffff;
            }
            """
        )


class DownloadTab(QWidget):
    def __init__(
        self,
        *,
        mode: str,
        config,
        parent_window: MainWindow,
        is_playlist: bool = False,
    ) -> None:
        super().__init__()
        self._mode = mode
        self.is_playlist = is_playlist
        self.parent_window = parent_window
        self.started_at: float | None = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)

        self.url_input = QLineEdit()
        placeholder = "Вставьте ссылку на плейлист" if is_playlist else "Вставьте ссылку на YouTube"
        self.url_input.setPlaceholderText(placeholder)

        self.media_type_select = QComboBox()
        if is_playlist:
            self.media_type_select.addItem("Видео", VIDEO_MODE)
            self.media_type_select.addItem("Аудио", AUDIO_MODE)

        self.bulk_urls_input = QPlainTextEdit()
        self.bulk_urls_input.setPlaceholderText("Ссылка на каждой строке")
        self.bulk_urls_input.setFixedHeight(92)

        self.quality_select = QComboBox()
        for quality in VIDEO_QUALITIES:
            label = "2K (1440p)" if quality == 1440 else f"{quality}p"
            self.quality_select.addItem(label, quality)
        default_quality = 1080
        default_index = VIDEO_QUALITIES.index(default_quality)
        self.quality_select.setCurrentIndex(default_index)

        default_dir = (
            config.download_dir
            if mode == VIDEO_MODE or is_playlist
            else config.audio_download_dir
        )
        self.output_dir_input = QLineEdit(str(default_dir))
        self.browse_button = QPushButton("Обзор")
        self.browse_button.clicked.connect(self.choose_output_dir)

        self.download_button = QPushButton("Скачать")
        self.download_button.clicked.connect(lambda: self.parent_window.start_download(self))
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.parent_window.request_cancel(self))

        self.status_label = QLabel("Ожидание")
        self.show_output_button = QPushButton("Показать в проводнике")
        self.show_output_button.clicked.connect(self.open_output_dir)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.elapsed_label = QLabel("Время выполнения: -")

        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel("Ссылка"), 0, 0)
        form.addWidget(self.url_input, 0, 1, 1, 2)

        row = 1
        if self._supports_bulk():
            form.addWidget(QLabel("Список ссылок"), row, 0)
            form.addWidget(self.bulk_urls_input, row, 1, 1, 2)
            row += 1
        else:
            self.bulk_urls_input.hide()

        if self.is_playlist:
            form.addWidget(QLabel("Тип"), row, 0)
            form.addWidget(self.media_type_select, row, 1, 1, 2)
            self.quality_select.hide()
            row += 1
        elif self.mode == VIDEO_MODE:
            form.addWidget(QLabel("Качество"), row, 0)
            form.addWidget(self.quality_select, row, 1, 1, 2)
            row += 1
        else:
            self.quality_select.hide()
            self.media_type_select.hide()

        form.addWidget(QLabel("Папка"), row, 0)
        form.addWidget(self.output_dir_input, row, 1)
        form.addWidget(self.browse_button, row, 2)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addWidget(QLabel("Статус:"))
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.show_output_button)
        status_row.addStretch(1)
        status_row.addWidget(self.progress, stretch=2)

        root.addLayout(form)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)

        root.addLayout(buttons)
        root.addLayout(status_row)
        root.addWidget(QLabel("Логи"))
        root.addWidget(self.log_output, stretch=1)
        root.addWidget(self.elapsed_label)

    def choose_output_dir(self) -> None:
        initial = self.output_dir_value()
        selected = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку",
            str(initial if initial else PROJECT_ROOT),
        )
        if selected:
            self.output_dir_input.setText(selected)

    def url_value(self) -> str:
        return self.url_input.text().strip()

    def bulk_urls_value(self) -> list[str]:
        if not self._supports_bulk():
            return []

        return [
            line.strip()
            for line in self.bulk_urls_input.toPlainText().splitlines()
            if line.strip()
        ]

    @property
    def mode(self) -> str:
        if self.is_playlist:
            return str(self.media_type_select.currentData())

        return self._mode

    def output_dir_value(self) -> Path:
        return Path(self.output_dir_text())

    def output_dir_text(self) -> str:
        return self.output_dir_input.text().strip()

    def video_quality_value(self) -> int | None:
        if self.is_playlist or self.mode != VIDEO_MODE:
            return None

        return int(self.quality_select.currentData())

    def prepare_for_download(self) -> None:
        self.started_at = time.perf_counter()
        self.log_output.clear()
        self.set_elapsed_time(0)
        self.elapsed_timer.start()
        self.set_status("Старт")
        self.set_progress_busy(True)
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def mark_cancel_requested(self) -> None:
        self.set_status("Отмена")
        self.cancel_button.setEnabled(False)
        self.append_log("Пользователь подтвердил отмену.")

    def finish_download(self, *, success: bool, cancelled: bool = False) -> None:
        self.finish_elapsed_time()
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if cancelled:
            self.set_status("Отменено")
            self.set_progress_busy(False)
            return

        if success:
            self.set_status("Готово")
            self.set_progress_busy(False)
            self.set_progress(100)

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_progress(self, value: int) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(value)

    def set_progress_busy(self, busy: bool) -> None:
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def finish_elapsed_time(self) -> None:
        self.elapsed_timer.stop()
        if self.started_at is None:
            return

        elapsed_seconds = time.perf_counter() - self.started_at
        self.set_elapsed_time(elapsed_seconds)
        self.started_at = None

    def update_elapsed_time(self) -> None:
        if self.started_at is None:
            return

        self.set_elapsed_time(time.perf_counter() - self.started_at)

    def set_elapsed_time(self, seconds: float) -> None:
        self.elapsed_label.setText(f"Время выполнения: {_format_elapsed_time(seconds)}")

    def open_output_dir(self) -> None:
        output_dir = self.output_dir_value()
        if not output_dir.exists():
            QMessageBox.warning(self, "Папка не найдена", f"Папка не существует: {output_dir}")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir.resolve())))

    def _supports_bulk(self) -> bool:
        return not self.is_playlist and self._mode == AUDIO_MODE


class SettingsTab(QWidget):
    def __init__(self, *, config, parent_window: MainWindow) -> None:
        super().__init__()
        self.parent_window = parent_window

        self.group_title = QLabel("Параллельная обработка")
        self.group_title.setStyleSheet("font-weight: 700;")

        self.download_worker_limit_select = QComboBox()
        self.process_worker_limit_select = QComboBox()
        for value in range(MIN_WORKER_LIMIT, MAX_DOWNLOAD_WORKER_LIMIT + 1):
            self.download_worker_limit_select.addItem(str(value), value)
        for value in range(MIN_WORKER_LIMIT, MAX_PROCESS_WORKER_LIMIT + 1):
            self.process_worker_limit_select.addItem(str(value), value)

        self.download_worker_limit_select.setCurrentIndex(
            self._select_index(config.download_worker_limit, self.download_worker_limit_select),
        )
        self.process_worker_limit_select.setCurrentIndex(
            self._select_index(config.process_worker_limit, self.process_worker_limit_select),
        )
        self.download_worker_limit_select.currentIndexChanged.connect(self.save_settings)
        self.process_worker_limit_select.currentIndexChanged.connect(self.save_settings)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.addWidget(self.group_title, 0, 0, 1, 2)
        form.addWidget(QLabel("Параллельных скачиваний"), 1, 0)
        form.addWidget(self.download_worker_limit_select, 1, 1)
        form.addWidget(QLabel("Параллельных конвертаций"), 2, 0)
        form.addWidget(self.process_worker_limit_select, 2, 1)

        root.addLayout(form)
        root.addStretch(1)

    def download_worker_limit_value(self) -> int:
        return int(self.download_worker_limit_select.currentData())

    def process_worker_limit_value(self) -> int:
        return int(self.process_worker_limit_select.currentData())

    def save_settings(self, *_args) -> None:
        save_parallel_limits(
            self.download_worker_limit_value(),
            self.process_worker_limit_value(),
        )
        self.parent_window.config = load_config()

    def _select_index(self, value: int, select: QComboBox) -> int:
        return max(
            0,
            min(
                select.count() - 1,
                int(value) - MIN_WORKER_LIMIT,
            ),
        )


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


def _question_with_russian_buttons(
    parent,
    title: str,
    text: str,
) -> QMessageBox.StandardButton:
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(title)
    dialog.setText(text)
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    dialog.setDefaultButton(QMessageBox.StandardButton.No)

    yes_button = dialog.button(QMessageBox.StandardButton.Yes)
    no_button = dialog.button(QMessageBox.StandardButton.No)
    if yes_button is not None:
        yes_button.setText("Да")
    if no_button is not None:
        no_button.setText("Нет")

    return QMessageBox.StandardButton(dialog.exec())


def _format_elapsed_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"
