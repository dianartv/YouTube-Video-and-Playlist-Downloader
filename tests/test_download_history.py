import tempfile
import unittest
from pathlib import Path

from engine.domain.download_history import DownloadRecord
from engine.service.download_history import SQLiteDownloadHistory


class SQLiteDownloadHistoryTests(unittest.TestCase):
    def test_upsert_and_find_download_record_with_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "downloads.sqlite3"
            output_path = Path(temp_dir) / "video.mp4"
            history = SQLiteDownloadHistory(database_path)

            history.upsert(
                DownloadRecord(
                    video_id="abc123",
                    media_type="video",
                    title="Title",
                    output_path=output_path,
                    source_url="https://youtu.be/abc123",
                    video_resolution=1080,
                    video_itag=137,
                    audio_bitrate=160,
                    audio_itag=251,
                    output_bitrate=160,
                    container="mp4",
                    file_size_bytes=123,
                    downloaded_at="2026-07-04T12:00:00+00:00",
                )
            )

            record = history.find("abc123", "video")

        self.assertIsNotNone(record)
        self.assertEqual(record.video_id, "abc123")
        self.assertEqual(record.media_type, "video")
        self.assertEqual(record.output_path, output_path)
        self.assertEqual(record.video_resolution, 1080)
        self.assertEqual(record.video_itag, 137)
        self.assertEqual(record.audio_bitrate, 160)
        self.assertEqual(record.audio_itag, 251)
        self.assertEqual(record.output_bitrate, 160)
        self.assertEqual(record.container, "mp4")
        self.assertEqual(record.file_size_bytes, 123)

    def test_upsert_replaces_record_for_same_video_and_media_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "downloads.sqlite3"
            history = SQLiteDownloadHistory(database_path)
            first_path = Path(temp_dir) / "first.mp3"
            second_path = Path(temp_dir) / "second.mp3"

            history.upsert(
                DownloadRecord(
                    video_id="abc123",
                    media_type="audio",
                    title="First",
                    output_path=first_path,
                    source_url="https://youtu.be/abc123",
                    output_bitrate=160,
                    container="mp3",
                    downloaded_at="2026-07-04T12:00:00+00:00",
                )
            )
            history.upsert(
                DownloadRecord(
                    video_id="abc123",
                    media_type="audio",
                    title="Second",
                    output_path=second_path,
                    source_url="https://youtu.be/abc123?t=1",
                    output_bitrate=320,
                    container="mp3",
                    downloaded_at="2026-07-04T12:10:00+00:00",
                )
            )

            record = history.find("abc123", "audio")

        self.assertEqual(record.title, "Second")
        self.assertEqual(record.output_path, second_path)
        self.assertEqual(record.output_bitrate, 320)


if __name__ == "__main__":
    unittest.main()
