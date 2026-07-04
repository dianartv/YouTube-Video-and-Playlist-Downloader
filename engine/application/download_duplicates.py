from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from engine.domain.download_history import DownloadHistory, DownloadRecord


PrintFunc = Callable[[str], None]
ConfirmOverwriteFunc = Callable[[DownloadRecord, DownloadRecord], bool]


def should_download_record(
    *,
    history: DownloadHistory | None,
    planned_record: DownloadRecord,
    confirm_overwrite_func: ConfirmOverwriteFunc | None,
    print_func: PrintFunc,
) -> bool:
    if history is None or not planned_record.video_id:
        return True

    existing_record = history.find(planned_record.video_id, planned_record.media_type)
    if existing_record is None:
        return True

    if not existing_record.output_path.exists():
        print_func(
            "Запись о прошлой загрузке найдена, но конечного файла уже нет. "
            "Скачиваю заново."
        )
        return True

    print_func(format_duplicate_download(existing_record, planned_record))
    if confirm_overwrite_func is None:
        print_func("Пропущено: подтверждение перезаписи недоступно.")
        return False

    if confirm_overwrite_func(existing_record, planned_record):
        return True

    print_func("Пропущено: пользователь отказался от перезаписи.")
    return False


def save_download_record(
    *,
    history: DownloadHistory | None,
    record: DownloadRecord,
    output_path: str | Path,
) -> None:
    if history is None or not record.video_id:
        return

    output_path = Path(output_path)
    history.upsert(
        replace(
            record,
            output_path=output_path,
            file_size_bytes=_file_size(output_path),
            downloaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    )


def format_duplicate_download(
    existing_record: DownloadRecord,
    planned_record: DownloadRecord,
) -> str:
    return "\n".join(
        [
            "Этот источник уже скачивался.",
            f"Название: {existing_record.title}",
            f"Тип: {_media_type_label(existing_record.media_type)}",
            f"Качество в истории: {describe_record_quality(existing_record)}",
            f"Текущее выбранное качество: {describe_record_quality(planned_record)}",
            f"Файл: {existing_record.output_path}",
        ]
    )


def describe_record_quality(record: DownloadRecord) -> str:
    parts = []
    if record.video_resolution is not None:
        parts.append(f"{record.video_resolution}p")
    if record.video_itag is not None:
        parts.append(f"video itag {record.video_itag}")
    if record.audio_bitrate is not None:
        parts.append(f"audio {record.audio_bitrate}kbps")
    if record.audio_itag is not None:
        parts.append(f"audio itag {record.audio_itag}")
    if record.output_bitrate is not None:
        parts.append(f"output {record.output_bitrate}kbps")
    if record.container:
        parts.append(record.container)

    return ", ".join(parts) if parts else "неизвестно"


def _media_type_label(media_type: str) -> str:
    if media_type == "video":
        return "видео"
    if media_type == "audio":
        return "аудио"
    return media_type


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
