import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engine.application.download_audio import download_audio
from engine.application.download_playlist import download_playlist
from engine.application.download_video import download_video
from engine.domain.download_history import DownloadRecord
from engine.domain.naming import make_playlist_directory_name
from engine.service.cancellation import CancellationToken, OperationCancelled
from engine.service.config import AppConfig


class FakeAudioStream:
    def __init__(self, itag, abr, subtype="webm", mime_type=None):
        self.itag = itag
        self.abr = abr
        self.subtype = subtype
        self.mime_type = mime_type
        self.saved_to = None

    def download(self, output_path=None, filename=None, interrupt_checker=None):
        if interrupt_checker is not None and interrupt_checker():
            return None

        self.saved_to = Path(output_path) / filename
        return str(self.saved_to)


class FakeVideoStream:
    def __init__(self, itag, resolution, subtype="mp4", fps=30):
        self.itag = itag
        self.resolution = resolution
        self.subtype = subtype
        self.fps = fps
        self.saved_to = None

    def download(self, output_path=None, filename=None, interrupt_checker=None):
        if interrupt_checker is not None and interrupt_checker():
            return None

        self.saved_to = Path(output_path) / filename
        return str(self.saved_to)


class InMemoryDownloadHistory:
    def __init__(self, records=None):
        self.records = records or {}

    def find(self, video_id: str, media_type: str):
        return self.records.get((video_id, media_type))

    def upsert(self, record: DownloadRecord) -> None:
        self.records[(record.video_id, record.media_type)] = record


class DownloadUseCaseTests(unittest.TestCase):
    def test_video_downloads_best_streams_and_merges_mp4(self):
        output = []
        video_stream = FakeVideoStream(137, "720p", "mp4")
        audio_stream = FakeAudioStream(251, "160kbps", "webm")
        config = SimpleNamespace(
            download_dir=Path("content"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
        )
        video = SimpleNamespace(title="Title", video_id="abc123", length=100)

        with (
            patch(
                "engine.application.download_video.get_video_streams_no_higher_than",
                return_value=[video_stream],
            ),
            patch(
                "engine.application.download_video.get_audio_streams",
                return_value=[audio_stream],
            ),
            patch(
                "engine.application.download_video.merge_video_and_audio_to_mp4",
                return_value=Path("content/Title.mp4"),
            ) as merge,
        ):
            result = download_video(
                video=video,
                config=config,
                print_func=output.append,
            )

        self.assertEqual(result, 0)
        self.assertEqual(video_stream.saved_to, Path("content/.tmp/abc123/video.mp4"))
        self.assertEqual(audio_stream.saved_to, Path("content/.tmp/abc123/audio.webm"))
        merge.assert_called_once()
        self.assertEqual(merge.call_args.kwargs["video_path"], video_stream.saved_to)
        self.assertEqual(merge.call_args.kwargs["audio_path"], audio_stream.saved_to)
        self.assertEqual(merge.call_args.kwargs["output_path"], Path("content/Title.mp4"))
        self.assertFalse(merge.call_args.kwargs["transcode_video"])
        self.assertTrue(any("720p mp4, 30fps (itag 137)" in line for line in output))

    def test_audio_download_uses_best_stream_and_converts_mp3(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm")
        config = SimpleNamespace(
            audio_download_dir=Path("content/audio"),
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
        )

        with (
            patch(
                "engine.application.download_audio.get_audio_streams",
                return_value=[stream, FakeAudioStream(140, "128kbps", "mp4")],
            ),
            patch("engine.application.download_audio.DownloadYTAudio") as downloader,
            patch("engine.application.download_audio.convert_to_mp3") as convert,
        ):
            downloader.return_value.download.return_value = "content/audio/audio.webm"
            convert.return_value = Path("content/audio/audio.mp3")
            result = download_audio(
                video=object(),
                config=config,
                print_func=output.append,
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            stream=stream,
            save_to=str(Path("content/audio")),
            filename="video.webm",
            interrupt_checker=None,
            progress_callback=None,
        )
        convert.assert_called_once()
        self.assertTrue(any("160kbps webm (itag 251, mp3 160kbps)" in line for line in output))

    def test_audio_uses_source_extension_from_mime_type(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm", "audio/webm")
        config = SimpleNamespace(
            audio_download_dir=Path("content/audio"),
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
        )

        with (
            patch("engine.application.download_audio.get_audio_streams", return_value=[stream]),
            patch("engine.application.download_audio.DownloadYTAudio") as downloader,
            patch("engine.application.download_audio.convert_to_mp3") as convert,
        ):
            downloader.return_value.download.return_value = "content/audio/Title.webm"
            convert.return_value = Path("content/audio/Title.mp3")
            result = download_audio(
                video=SimpleNamespace(title="Title"),
                config=config,
                print_func=output.append,
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            stream=stream,
            save_to=str(Path("content/audio")),
            filename="Title.webm",
            interrupt_checker=None,
            progress_callback=None,
        )
        self.assertTrue(any("160kbps webm" in line for line in output))

    def test_audio_duplicate_existing_file_requires_overwrite_confirmation(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_path = temp_path / "Title.mp3"
            existing_path.write_bytes(b"existing")
            history = InMemoryDownloadHistory(
                {
                    ("abc123", "audio"): DownloadRecord(
                        video_id="abc123",
                        media_type="audio",
                        title="Title",
                        output_path=existing_path,
                        source_url="https://youtu.be/abc123",
                        audio_bitrate=160,
                        audio_itag=251,
                        output_bitrate=160,
                        container="mp3",
                        downloaded_at="2026-07-04T12:00:00+00:00",
                    )
                }
            )
            config = SimpleNamespace(
                audio_download_dir=temp_path,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
            )
            confirm_calls = []

            with (
                patch("engine.application.download_audio.get_audio_streams", return_value=[stream]),
                patch("engine.application.download_audio.DownloadYTAudio") as downloader,
            ):
                result = download_audio(
                    video=SimpleNamespace(
                        title="Title",
                        video_id="abc123",
                        watch_url="https://youtu.be/abc123",
                    ),
                    config=config,
                    print_func=output.append,
                    download_history=history,
                    confirm_overwrite_func=lambda existing, planned: confirm_calls.append(
                        (existing, planned)
                    )
                    or False,
                )

        self.assertEqual(result, 0)
        downloader.assert_not_called()
        self.assertEqual(len(confirm_calls), 1)
        self.assertTrue(any("audio 160kbps" in line for line in output))

    def test_audio_stale_history_record_downloads_without_confirmation(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history = InMemoryDownloadHistory(
                {
                    ("abc123", "audio"): DownloadRecord(
                        video_id="abc123",
                        media_type="audio",
                        title="Title",
                        output_path=temp_path / "missing.mp3",
                        source_url="https://youtu.be/abc123",
                        output_bitrate=160,
                        container="mp3",
                        downloaded_at="2026-07-04T12:00:00+00:00",
                    )
                }
            )
            config = SimpleNamespace(
                audio_download_dir=temp_path,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
            )

            with (
                patch("engine.application.download_audio.get_audio_streams", return_value=[stream]),
                patch("engine.application.download_audio.DownloadYTAudio") as downloader,
                patch("engine.application.download_audio.convert_to_mp3") as convert,
            ):
                downloader.return_value.download.return_value = str(temp_path / "Title.webm")
                convert.return_value = temp_path / "Title.mp3"
                result = download_audio(
                    video=SimpleNamespace(
                        title="Title",
                        video_id="abc123",
                        watch_url="https://youtu.be/abc123",
                    ),
                    config=config,
                    print_func=output.append,
                    download_history=history,
                    confirm_overwrite_func=lambda *args: self.fail("confirm should not be called"),
                )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once()
        self.assertTrue(any("Скачиваю заново" in line for line in output))

    def test_successful_video_download_records_quality(self):
        video_stream = FakeVideoStream(137, "720p", "mp4")
        audio_stream = FakeAudioStream(251, "160kbps", "webm")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history = InMemoryDownloadHistory()
            config = SimpleNamespace(
                download_dir=temp_path,
                default_video_quality=720,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
            )

            with (
                patch(
                    "engine.application.download_video.get_video_streams_no_higher_than",
                    return_value=[video_stream],
                ),
                patch(
                    "engine.application.download_video.get_audio_streams",
                    return_value=[audio_stream],
                ),
                patch(
                    "engine.application.download_video.merge_video_and_audio_to_mp4",
                    return_value=temp_path / "Title.mp4",
                ),
            ):
                result = download_video(
                    video=SimpleNamespace(
                        title="Title",
                        video_id="abc123",
                        length=100,
                        watch_url="https://youtu.be/abc123",
                    ),
                    config=config,
                    print_func=lambda message: None,
                    download_history=history,
                    confirm_overwrite_func=lambda *args: self.fail("confirm should not be called"),
                )

        record = history.find("abc123", "video")
        self.assertEqual(result, 0)
        self.assertIsNotNone(record)
        self.assertEqual(record.video_resolution, 720)
        self.assertEqual(record.video_itag, 137)
        self.assertEqual(record.audio_bitrate, 160)
        self.assertEqual(record.audio_itag, 251)
        self.assertEqual(record.output_bitrate, 160)
        self.assertEqual(record.container, "mp4")


class PlaylistDownloadTests(unittest.TestCase):
    def test_playlist_download_stops_when_cancelled_before_processing(self):
        config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            worker_limit=4,
        )
        token = CancellationToken()
        token.cancel()

        with self.assertRaises(OperationCancelled):
            download_playlist(
                playlist=SimpleNamespace(
                    title="Videos",
                    video_urls=["https://youtu.be/one"],
                ),
                media_mode="video",
                config=config,
                print_func=lambda message: self.fail("print should not be called"),
                cancel_token=token,
            )

    def test_playlist_directory_name_removes_forbidden_path_characters(self):
        self.assertEqual(make_playlist_directory_name("My/Playlist?"), "MyPlaylist")
        self.assertEqual(make_playlist_directory_name("../"), "playlist")

    def test_audio_playlist_uses_auto_title_directory(self):
        output = []
        config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            worker_limit=6,
        )
        playlist = SimpleNamespace(
            title="My/Playlist?",
            video_urls=["https://youtu.be/one", "https://youtu.be/two"],
        )

        with (
            patch(
                "engine.application.download_playlist.YouTube",
                side_effect=[
                    SimpleNamespace(title="One"),
                    SimpleNamespace(title="Two"),
                ],
            ),
            patch("engine.application.download_playlist.download_audio", return_value=0) as download_audio_mock,
        ):
            result = download_playlist(
                playlist=playlist,
                media_mode="audio",
                config=config,
                print_func=output.append,
            )

        expected_dir = Path("content/audio") / "MyPlaylist"
        self.assertEqual(result, 0)
        self.assertEqual(download_audio_mock.call_count, 2)
        for call in download_audio_mock.call_args_list:
            self.assertEqual(call.kwargs["config"].audio_download_dir, expected_dir)
            self.assertEqual(call.kwargs["config"].worker_limit, 6)
        self.assertTrue(any(str(expected_dir) in line for line in output))

    def test_video_playlist_uses_auto_title_directory(self):
        output = []
        config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            worker_limit=5,
        )
        playlist = SimpleNamespace(
            title="Videos",
            video_urls=["https://youtu.be/one"],
        )

        with (
            patch(
                "engine.application.download_playlist.YouTube",
                return_value=SimpleNamespace(title="One"),
            ),
            patch("engine.application.download_playlist.download_video", return_value=0) as download_video_mock,
        ):
            result = download_playlist(
                playlist=playlist,
                media_mode="video",
                config=config,
                print_func=output.append,
            )

        expected_dir = Path("content") / "Videos"
        self.assertEqual(result, 0)
        download_video_mock.assert_called_once()
        self.assertEqual(download_video_mock.call_args.kwargs["config"].download_dir, expected_dir)
        self.assertEqual(download_video_mock.call_args.kwargs["config"].worker_limit, 5)
        self.assertTrue(any(str(expected_dir) in line for line in output))


if __name__ == "__main__":
    unittest.main()
