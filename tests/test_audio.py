import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.service.audio import (
    AudioConversionError,
    choose_mp3_bitrate,
    convert_to_mp3,
    parse_bitrate_kbps,
)
from engine.service.cancellation import CancellationToken, OperationCancelled


class AudioServiceTests(unittest.TestCase):
    def test_parse_bitrate_kbps_reads_youtube_abr(self):
        self.assertEqual(parse_bitrate_kbps("160kbps"), 160)

    def test_parse_bitrate_kbps_returns_none_for_unknown_value(self):
        self.assertIsNone(parse_bitrate_kbps(None))
        self.assertIsNone(parse_bitrate_kbps("unknown"))

    def test_choose_mp3_bitrate_does_not_exceed_source_bitrate(self):
        self.assertEqual(choose_mp3_bitrate(160, 320), 160)

    def test_choose_mp3_bitrate_uses_default_when_source_is_unknown(self):
        self.assertEqual(choose_mp3_bitrate(None, 320), 320)

    def test_convert_to_mp3_uses_limited_bitrate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "audio.webm"
            output_path = Path(temp_dir) / "audio.mp3"
            input_path.write_bytes(b"fake audio")

            with (
                patch(
                    "engine.service.audio.resolve_ffmpeg_executable",
                    return_value="ffmpeg",
                ),
                patch("engine.service.audio.subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess([], 0, b"", b"")

                self.assertEqual(
                    convert_to_mp3(
                        input_path=input_path,
                        output_path=output_path,
                        source_bitrate_kbps=160,
                        max_bitrate_kbps=320,
                    ),
                    output_path,
                )

        command = run.call_args.args[0]
        self.assertIn("-b:a", command)
        self.assertEqual(command[command.index("-b:a") + 1], "160k")

    def test_convert_to_mp3_raises_conversion_error_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "audio.webm"
            output_path = Path(temp_dir) / "audio.mp3"
            input_path.write_bytes(b"fake audio")

            with (
                patch(
                    "engine.service.audio.resolve_ffmpeg_executable",
                    return_value="ffmpeg",
                ),
                patch("engine.service.audio.subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess([], 1, b"", b"failed")

                with self.assertRaises(AudioConversionError):
                    convert_to_mp3(
                        input_path=input_path,
                        output_path=output_path,
                        source_bitrate_kbps=160,
                        max_bitrate_kbps=320,
                    )

    def test_convert_to_mp3_decodes_ffmpeg_error_bytes_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "audio.webm"
            output_path = Path(temp_dir) / "audio.mp3"
            input_path.write_bytes(b"fake audio")

            with (
                patch(
                    "engine.service.audio.resolve_ffmpeg_executable",
                    return_value="ffmpeg",
                ),
                patch("engine.service.audio.subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess(
                    [],
                    1,
                    b"",
                    b"bad byte: \x98",
                )

                with self.assertRaises(AudioConversionError) as exc:
                    convert_to_mp3(
                        input_path=input_path,
                        output_path=output_path,
                        source_bitrate_kbps=160,
                        max_bitrate_kbps=320,
                    )

        self.assertIn("bad byte:", str(exc.exception))

    def test_convert_to_mp3_does_not_start_ffmpeg_when_cancelled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "audio.webm"
            output_path = Path(temp_dir) / "audio.mp3"
            input_path.write_bytes(b"fake audio")
            token = CancellationToken()
            token.cancel()

            with (
                patch("engine.service.audio.subprocess.Popen") as popen,
                self.assertRaises(OperationCancelled),
            ):
                convert_to_mp3(
                    input_path=input_path,
                    output_path=output_path,
                    source_bitrate_kbps=160,
                    max_bitrate_kbps=320,
                    cancel_token=token,
                )

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
