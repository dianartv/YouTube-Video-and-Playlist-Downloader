import sqlite3
from pathlib import Path

from engine.domain.download_history import DownloadRecord
from engine.service.config import PROJECT_ROOT


DEFAULT_HISTORY_PATH = PROJECT_ROOT / "content" / ".downloads.sqlite3"


class SQLiteDownloadHistory:
    def __init__(self, database_path: str | Path = DEFAULT_HISTORY_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @classmethod
    def default(cls) -> "SQLiteDownloadHistory":
        return cls(DEFAULT_HISTORY_PATH)

    def find(self, video_id: str, media_type: str) -> DownloadRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT
                    video_id,
                    media_type,
                    title,
                    output_path,
                    source_url,
                    video_resolution,
                    video_itag,
                    audio_bitrate,
                    audio_itag,
                    output_bitrate,
                    container,
                    file_size_bytes,
                    downloaded_at
                FROM downloads
                WHERE video_id = ? AND media_type = ?
                """,
                (video_id, media_type),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return _row_to_record(row)

    def upsert(self, record: DownloadRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO downloads (
                    video_id,
                    media_type,
                    title,
                    output_path,
                    source_url,
                    video_resolution,
                    video_itag,
                    audio_bitrate,
                    audio_itag,
                    output_bitrate,
                    container,
                    file_size_bytes,
                    downloaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, media_type) DO UPDATE SET
                    title = excluded.title,
                    output_path = excluded.output_path,
                    source_url = excluded.source_url,
                    video_resolution = excluded.video_resolution,
                    video_itag = excluded.video_itag,
                    audio_bitrate = excluded.audio_bitrate,
                    audio_itag = excluded.audio_itag,
                    output_bitrate = excluded.output_bitrate,
                    container = excluded.container,
                    file_size_bytes = excluded.file_size_bytes,
                    downloaded_at = excluded.downloaded_at
                """,
                (
                    record.video_id,
                    record.media_type,
                    record.title,
                    str(record.output_path),
                    record.source_url,
                    record.video_resolution,
                    record.video_itag,
                    record.audio_bitrate,
                    record.audio_itag,
                    record.output_bitrate,
                    record.container,
                    record.file_size_bytes,
                    record.downloaded_at,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    video_resolution INTEGER,
                    video_itag INTEGER,
                    audio_bitrate INTEGER,
                    audio_itag INTEGER,
                    output_bitrate INTEGER,
                    container TEXT,
                    file_size_bytes INTEGER,
                    downloaded_at TEXT NOT NULL,
                    UNIQUE(video_id, media_type)
                )
                """
            )
            connection.commit()
        finally:
            connection.close()


def _row_to_record(row: sqlite3.Row) -> DownloadRecord:
    return DownloadRecord(
        video_id=row["video_id"],
        media_type=row["media_type"],
        title=row["title"],
        output_path=Path(row["output_path"]),
        source_url=row["source_url"],
        video_resolution=row["video_resolution"],
        video_itag=row["video_itag"],
        audio_bitrate=row["audio_bitrate"],
        audio_itag=row["audio_itag"],
        output_bitrate=row["output_bitrate"],
        container=row["container"],
        file_size_bytes=row["file_size_bytes"],
        downloaded_at=row["downloaded_at"],
    )
