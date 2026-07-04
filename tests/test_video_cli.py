import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError

from engine.application.download_audio import download_audio
from engine.application.download_playlist import download_playlist
from engine.application.download_video import download_video
from engine.cli.prompts import prompt_audio_stream, prompt_video_resolution
from engine.domain.naming import make_playlist_directory_name
from engine.domain.selection import choose_audio_stream, choose_video_resolution
from engine.domain.download_history import DownloadRecord
from engine.service.config import AppConfig
from engine.service.cancellation import CancellationToken, OperationCancelled
from engine.cli.handlers import (
    download_media_interactive,
)


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


class ChooseVideoResolutionTests(unittest.TestCase):
    def test_blank_choice_uses_default_resolution(self):
        self.assertEqual(choose_video_resolution([1080, 720, 480], 720, ""), 720)

    def test_blank_choice_uses_best_available_when_default_is_unavailable(self):
        self.assertEqual(choose_video_resolution([1080, 480], 720, ""), 1080)

    def test_numeric_choice_can_select_by_list_index(self):
        self.assertEqual(choose_video_resolution([1080, 720, 480], 720, "2"), 720)

    def test_numeric_choice_can_select_by_resolution_value(self):
        self.assertEqual(choose_video_resolution([1080, 720, 480], 720, "1080"), 1080)

    def test_resolution_choice_accepts_p_suffix(self):
        self.assertEqual(choose_video_resolution([1080, 720, 480], 720, "480p"), 480)

    def test_unknown_resolution_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_video_resolution([1080, 720, 480], 720, "360")


class PromptVideoResolutionTests(unittest.TestCase):
    def test_prompt_shows_video_only_resolutions_separately(self):
        output = []

        resolution = prompt_video_resolution(
            available_resolutions=[360],
            default_resolution=720,
            video_only_resolutions=[1080, 720, 480],
            input_func=lambda prompt: "",
            print_func=output.append,
        )

        self.assertEqual(resolution, 360)
        self.assertIn("1. 360p", output)
        self.assertIn(
            "Без аудио, не скачивается в этом режиме: 1080p, 720p, 480p",
            output,
        )


class ChooseAudioStreamTests(unittest.TestCase):
    def test_blank_choice_uses_best_audio_stream(self):
        streams = [FakeAudioStream(251, "160kbps"), FakeAudioStream(140, "128kbps")]

        self.assertEqual(choose_audio_stream(streams, "").itag, 251)

    def test_numeric_choice_can_select_by_list_index(self):
        streams = [FakeAudioStream(251, "160kbps"), FakeAudioStream(140, "128kbps")]

        self.assertEqual(choose_audio_stream(streams, "2").itag, 140)

    def test_numeric_choice_can_select_by_itag(self):
        streams = [FakeAudioStream(251, "160kbps"), FakeAudioStream(140, "128kbps")]

        self.assertEqual(choose_audio_stream(streams, "140").itag, 140)

    def test_rejects_unknown_audio_stream(self):
        with self.assertRaises(ValueError):
            choose_audio_stream([FakeAudioStream(251, "160kbps")], "999")


class PromptAudioStreamTests(unittest.TestCase):
    def test_prompt_shows_source_and_target_mp3_bitrate(self):
        output = []
        streams = [FakeAudioStream(251, "160kbps", "webm")]

        stream = prompt_audio_stream(
            audio_streams=streams,
            max_mp3_bitrate=320,
            input_func=lambda prompt: "",
            print_func=output.append,
        )

        self.assertEqual(stream.itag, 251)
        self.assertIn("1. 160kbps webm (itag 251, mp3 160kbps)", output)


class FullAutoDownloadTests(unittest.TestCase):
    def test_full_auto_video_downloads_video_and_audio_then_merges_mp4(self):
        output = []
        video_stream = FakeVideoStream(137, "720p", "mp4")
        audio_stream = FakeAudioStream(251, "160kbps", "webm")
        config = SimpleNamespace(
            full_auto=True,
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
                "engine.application.download_video.get_video_resolutions_no_higher_than",
                return_value=[720],
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
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_video_resolution_func=lambda *args: self.fail("video prompt should not be called"),
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 0)
        self.assertEqual(video_stream.saved_to, Path("content/.tmp/abc123/video.mp4"))
        self.assertEqual(audio_stream.saved_to, Path("content/.tmp/abc123/audio.webm"))
        merge.assert_called_once()
        self.assertEqual(merge.call_args.kwargs["video_path"], video_stream.saved_to)
        self.assertEqual(merge.call_args.kwargs["audio_path"], audio_stream.saved_to)
        self.assertEqual(merge.call_args.kwargs["output_path"], Path("content/Title.mp4"))
        self.assertFalse(merge.call_args.kwargs["transcode_video"])
        self.assertIn(
            "Full auto: выбрано лучшее видео не выше 720p: 720p mp4, 30fps (itag 137).",
            output,
        )
        self.assertIn("Готово. MP4 сохранён в content\\Title.mp4.", output)

    def test_full_auto_audio_uses_best_audio_stream(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm")
        config = SimpleNamespace(
            full_auto=True,
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
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            stream=stream,
            save_to=str(Path("content/audio")),
            filename="video.webm",
            interrupt_checker=None,
        )
        convert.assert_called_once()
        self.assertIn(
            "Full auto: выбрана лучшая аудио-дорожка 160kbps webm (itag 251, mp3 160kbps).",
            output,
        )

    def test_full_auto_audio_uses_source_extension_from_mime_type(self):
        output = []
        stream = FakeAudioStream(251, "160kbps", "webm", "audio/webm")
        config = SimpleNamespace(
            full_auto=True,
            audio_download_dir=Path("content/audio"),
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
        )

        with (
            patch(
                "engine.application.download_audio.get_audio_streams",
                return_value=[stream],
            ),
            patch("engine.application.download_audio.DownloadYTAudio") as downloader,
            patch("engine.application.download_audio.convert_to_mp3") as convert,
        ):
            downloader.return_value.download.return_value = "content/audio/Title.webm"
            convert.return_value = Path("content/audio/Title.mp3")
            result = download_audio(
                video=SimpleNamespace(title="Title"),
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            stream=stream,
            save_to=str(Path("content/audio")),
            filename="Title.webm",
            interrupt_checker=None,
        )
        self.assertTrue(
            any("Скачиваю аудио-дорожку: 160kbps webm" in line for line in output)
        )

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
                full_auto=True,
                audio_download_dir=temp_path,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
            )
            confirm_calls = []

            with (
                patch(
                    "engine.application.download_audio.get_audio_streams",
                    return_value=[stream],
                ),
                patch("engine.application.download_audio.DownloadYTAudio") as downloader,
            ):
                result = download_audio(
                    video=SimpleNamespace(
                        title="Title",
                        video_id="abc123",
                        watch_url="https://youtu.be/abc123",
                    ),
                    config=config,
                    input_func=lambda prompt: self.fail("input should not be called"),
                    print_func=output.append,
                    prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
                    download_history=history,
                    confirm_overwrite_func=lambda existing, planned: confirm_calls.append(
                        (existing, planned)
                    )
                    or False,
                )

        self.assertEqual(result, 0)
        downloader.assert_not_called()
        self.assertEqual(len(confirm_calls), 1)
        self.assertTrue(
            any("Качество в истории: audio 160kbps" in line for line in output)
        )
        self.assertIn("Пропущено: пользователь отказался от перезаписи.", output)

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
                full_auto=True,
                audio_download_dir=temp_path,
                default_mp3_bitrate=320,
                ffmpeg_path="ffmpeg",
            )

            with (
                patch(
                    "engine.application.download_audio.get_audio_streams",
                    return_value=[stream],
                ),
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
                    input_func=lambda prompt: self.fail("input should not be called"),
                    print_func=output.append,
                    prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
                    download_history=history,
                    confirm_overwrite_func=lambda *args: self.fail("confirm should not be called"),
                )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once()
        self.assertIn(
            "Запись о прошлой загрузке найдена, но конечного файла уже нет. Скачиваю заново.",
            output,
        )

    def test_successful_video_download_records_quality(self):
        output = []
        video_stream = FakeVideoStream(137, "720p", "mp4")
        audio_stream = FakeAudioStream(251, "160kbps", "webm")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history = InMemoryDownloadHistory()
            config = SimpleNamespace(
                full_auto=True,
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
                    "engine.application.download_video.get_video_resolutions_no_higher_than",
                    return_value=[720],
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
                    input_func=lambda prompt: self.fail("input should not be called"),
                    print_func=output.append,
                    prompt_video_resolution_func=lambda *args: self.fail("video prompt should not be called"),
                    prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
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


class DownloadMediaInteractiveTests(unittest.TestCase):
    def test_active_live_stream_is_reported_without_traceback(self):
        output = []

        with patch("engine.cli.handlers.YouTube") as youtube:
            video = youtube.return_value
            video.title = "Active live"
            with (
                patch(
                    "engine.cli.handlers.SQLiteDownloadHistory.default",
                    return_value=InMemoryDownloadHistory(),
                ),
                patch(
                    "engine.cli.handlers.run_video_download",
                    side_effect=LiveStreamError("video-id"),
                ),
            ):
                result = download_media_interactive(
                    mode="video",
                    input_func=lambda prompt: "https://www.youtube.com/live/KO9oWuU3KV0",
                    print_func=output.append,
                )

        self.assertEqual(result, 1)
        self.assertIn(
            "Активные live-трансляции не скачиваются. Дождитесь завершения и публикации архива.",
            output,
        )

    def test_live_stream_ended_is_reported_without_traceback(self):
        output = []

        with patch("engine.cli.handlers.YouTube") as youtube:
            video = youtube.return_value
            video.title = "Ended live"
            with (
                patch(
                    "engine.cli.handlers.SQLiteDownloadHistory.default",
                    return_value=InMemoryDownloadHistory(),
                ),
                patch(
                    "engine.cli.handlers.run_video_download",
                    side_effect=LiveStreamEnded("video-id", "ended"),
                ),
            ):
                result = download_media_interactive(
                    mode="video",
                    input_func=lambda prompt: "https://www.youtube.com/live/KO9oWuU3KV0",
                    print_func=output.append,
                )

        self.assertEqual(result, 1)
        self.assertIn(
            "Трансляция завершилась, но YouTube ещё не отдаёт архив как обычное видео. "
            "Повторите позже.",
            output,
        )


class PlaylistDownloadTests(unittest.TestCase):
    def test_playlist_download_stops_when_cancelled_before_processing(self):
        config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            full_auto=True,
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
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=lambda message: self.fail("print should not be called"),
                prompt_video_resolution_func=lambda *args: self.fail("video prompt should not be called"),
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
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
            full_auto=True,
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
            patch(
                "engine.application.download_playlist.download_audio",
                return_value=0,
            ) as download_audio_mock,
        ):
            result = download_playlist(
                playlist=playlist,
                media_mode="audio",
                config=config,
                input_func=lambda prompt: "https://youtube.com/playlist?list=123",
                print_func=output.append,
                prompt_video_resolution_func=lambda *args: self.fail("video prompt should not be called"),
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        expected_dir = Path("content/audio") / "MyPlaylist"
        self.assertEqual(result, 0)
        self.assertEqual(download_audio_mock.call_count, 2)
        for call in download_audio_mock.call_args_list:
            self.assertEqual(call.kwargs["config"].audio_download_dir, expected_dir)
            self.assertEqual(call.kwargs["config"].worker_limit, 6)
        self.assertIn(f"Каталог плейлиста: {expected_dir}", output)
        self.assertIn("Готово. Успешно: 2. Пропущено/ошибок: 0.", output)

    def test_video_playlist_uses_auto_title_directory(self):
        output = []
        config = AppConfig(
            download_dir=Path("content"),
            audio_download_dir=Path("content/audio"),
            default_video_quality=720,
            default_mp3_bitrate=320,
            ffmpeg_path="ffmpeg",
            full_auto=True,
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
            patch(
                "engine.application.download_playlist.download_video",
                return_value=0,
            ) as download_video_mock,
        ):
            result = download_playlist(
                playlist=playlist,
                media_mode="video",
                config=config,
                input_func=lambda prompt: "https://youtube.com/playlist?list=123",
                print_func=output.append,
                prompt_video_resolution_func=lambda *args: self.fail("video prompt should not be called"),
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        expected_dir = Path("content") / "Videos"
        self.assertEqual(result, 0)
        download_video_mock.assert_called_once()
        self.assertEqual(
            download_video_mock.call_args.kwargs["config"].download_dir,
            expected_dir,
        )
        self.assertEqual(download_video_mock.call_args.kwargs["config"].worker_limit, 5)
        self.assertIn(f"Каталог плейлиста: {expected_dir}", output)


if __name__ == "__main__":
    unittest.main()
