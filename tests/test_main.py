import unittest
from unittest.mock import patch

from engine.youtube_tools.video_cli import AUDIO_MODE, VIDEO_MODE
from main import main, parse_args


class MainArgumentTests(unittest.TestCase):
    def test_parse_args_accepts_video_mode(self):
        self.assertEqual(parse_args(["--video"]).mode, VIDEO_MODE)

    def test_parse_args_accepts_audio_mode(self):
        self.assertEqual(parse_args(["--audio"]).mode, AUDIO_MODE)

    def test_parse_args_accepts_audio_only_alias(self):
        self.assertEqual(parse_args(["--audio-only"]).mode, AUDIO_MODE)

    def test_parse_args_accepts_playlist_with_audio_mode(self):
        args = parse_args(["--playlist", "--audio"])

        self.assertTrue(args.playlist)
        self.assertEqual(args.mode, AUDIO_MODE)

    def test_parse_args_accepts_playlist_with_video_mode(self):
        args = parse_args(["--playlist", "--video"])

        self.assertTrue(args.playlist)
        self.assertEqual(args.mode, VIDEO_MODE)

    def test_main_passes_mode_to_downloader(self):
        with patch("main.download_media_interactive", return_value=0) as downloader:
            result = main(["--audio"])

        self.assertEqual(result, 0)
        downloader.assert_called_once_with(mode=AUDIO_MODE)

    def test_main_passes_playlist_mode_to_playlist_downloader(self):
        with patch("main.download_playlist_interactive", return_value=0) as downloader:
            result = main(["--playlist", "--audio"])

        self.assertEqual(result, 0)
        downloader.assert_called_once_with(media_mode=AUDIO_MODE)


if __name__ == "__main__":
    unittest.main()
