import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError

from engine.service.config import AppConfig
from engine.youtube_tools.video_cli import (
    choose_audio_stream,
    choose_video_resolution,
    download_audio,
    download_media_interactive,
    download_playlist_interactive,
    download_video,
    make_playlist_directory_name,
    prompt_audio_stream,
    prompt_video_resolution,
)


class FakeAudioStream:
    def __init__(self, itag, abr, subtype="webm"):
        self.itag = itag
        self.abr = abr
        self.subtype = subtype
        self.saved_to = None

    def download(self, output_path=None, filename=None):
        self.saved_to = Path(output_path) / filename
        return str(self.saved_to)


class FakeVideoStream:
    def __init__(self, itag, resolution, subtype="mp4", fps=30):
        self.itag = itag
        self.resolution = resolution
        self.subtype = subtype
        self.fps = fps
        self.saved_to = None

    def download(self, output_path=None, filename=None):
        self.saved_to = Path(output_path) / filename
        return str(self.saved_to)


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
                "engine.youtube_tools.video_cli.get_video_streams_no_higher_than",
                return_value=[video_stream],
            ),
            patch(
                "engine.youtube_tools.video_cli.get_video_resolutions_no_higher_than",
                return_value=[720],
            ),
            patch(
                "engine.youtube_tools.video_cli.get_audio_streams",
                return_value=[audio_stream],
            ),
            patch(
                "engine.youtube_tools.video_cli.merge_video_and_audio_to_mp4",
                return_value=Path("content/Title.mp4"),
            ) as merge,
        ):
            result = download_video(
                video=video,
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
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
                "engine.youtube_tools.video_cli.get_audio_streams",
                return_value=[stream, FakeAudioStream(140, "128kbps", "mp4")],
            ),
            patch("engine.youtube_tools.video_cli.DownloadYTAudio") as downloader,
            patch("engine.youtube_tools.video_cli.convert_to_mp3") as convert,
        ):
            downloader.return_value.download.return_value = "content/audio/audio.webm"
            convert.return_value = Path("content/audio/audio.mp3")
            result = download_audio(
                video=object(),
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            stream=stream,
            save_to=str(Path("content/audio")),
        )
        convert.assert_called_once()
        self.assertIn(
            "Full auto: выбрана лучшая аудио-дорожка 160kbps webm (itag 251, mp3 160kbps).",
            output,
        )


class DownloadMediaInteractiveTests(unittest.TestCase):
    def test_active_live_stream_is_reported_without_traceback(self):
        output = []

        with patch("engine.youtube_tools.video_cli.YouTube") as youtube:
            video = youtube.return_value
            video.title = "Active live"
            with patch(
                "engine.youtube_tools.video_cli.get_video_streams_no_higher_than",
                side_effect=LiveStreamError("video-id"),
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

        with patch("engine.youtube_tools.video_cli.YouTube") as youtube:
            video = youtube.return_value
            video.title = "Ended live"
            with patch(
                "engine.youtube_tools.video_cli.get_video_streams_no_higher_than",
                side_effect=LiveStreamEnded("video-id", "ended"),
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
        )
        playlist = SimpleNamespace(
            title="My/Playlist?",
            video_urls=["https://youtu.be/one", "https://youtu.be/two"],
        )

        with (
            patch("engine.youtube_tools.video_cli.configure_file_logger"),
            patch("engine.youtube_tools.video_cli.ensure_env_file"),
            patch("engine.youtube_tools.video_cli.load_config", return_value=config),
            patch("engine.youtube_tools.video_cli.Playlist", return_value=playlist),
            patch(
                "engine.youtube_tools.video_cli.YouTube",
                side_effect=[
                    SimpleNamespace(title="One"),
                    SimpleNamespace(title="Two"),
                ],
            ),
            patch(
                "engine.youtube_tools.video_cli.download_audio",
                return_value=0,
            ) as download_audio_mock,
        ):
            result = download_playlist_interactive(
                media_mode="audio",
                input_func=lambda prompt: "https://youtube.com/playlist?list=123",
                print_func=output.append,
            )

        expected_dir = Path("content/audio") / "MyPlaylist"
        self.assertEqual(result, 0)
        self.assertEqual(download_audio_mock.call_count, 2)
        for call in download_audio_mock.call_args_list:
            self.assertEqual(call.kwargs["config"].audio_download_dir, expected_dir)
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
        )
        playlist = SimpleNamespace(
            title="Videos",
            video_urls=["https://youtu.be/one"],
        )

        with (
            patch("engine.youtube_tools.video_cli.configure_file_logger"),
            patch("engine.youtube_tools.video_cli.ensure_env_file"),
            patch("engine.youtube_tools.video_cli.load_config", return_value=config),
            patch("engine.youtube_tools.video_cli.Playlist", return_value=playlist),
            patch(
                "engine.youtube_tools.video_cli.YouTube",
                return_value=SimpleNamespace(title="One"),
            ),
            patch(
                "engine.youtube_tools.video_cli.download_video",
                return_value=0,
            ) as download_video_mock,
        ):
            result = download_playlist_interactive(
                media_mode="video",
                input_func=lambda prompt: "https://youtube.com/playlist?list=123",
                print_func=output.append,
            )

        expected_dir = Path("content") / "Videos"
        self.assertEqual(result, 0)
        download_video_mock.assert_called_once()
        self.assertEqual(
            download_video_mock.call_args.kwargs["config"].download_dir,
            expected_dir,
        )
        self.assertIn(f"Каталог плейлиста: {expected_dir}", output)


if __name__ == "__main__":
    unittest.main()
