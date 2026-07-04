import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engine.youtube_tools.video_cli import (
    choose_audio_stream,
    choose_video_resolution,
    prompt_audio_stream,
    prompt_video_resolution,
    download_audio,
    download_video,
)


class FakeAudioStream:
    def __init__(self, itag, abr, subtype="webm"):
        self.itag = itag
        self.abr = abr
        self.subtype = subtype


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
    def test_full_auto_video_uses_best_available_resolution(self):
        output = []
        config = SimpleNamespace(
            full_auto=True,
            download_dir=Path("content"),
            default_video_quality=720,
        )

        with (
            patch(
                "engine.youtube_tools.video_cli.get_available_resolutions",
                return_value=[1080, 720],
            ),
            patch(
                "engine.youtube_tools.video_cli.get_video_only_resolutions",
                return_value=[1440],
            ),
            patch("engine.youtube_tools.video_cli.DownloadYTVideo") as downloader,
        ):
            result = download_video(
                video=object(),
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
            )

        self.assertEqual(result, 0)
        downloader.return_value.download.assert_called_once_with(
            resolution=1080,
            save_to=str(Path("content")),
        )
        self.assertIn("Full auto: выбрано лучшее качество со звуком 1080p.", output)

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


if __name__ == "__main__":
    unittest.main()
