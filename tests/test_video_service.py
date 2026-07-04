import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.service.video import VideoMergeError, merge_video_and_audio_to_mp4


class FakeProcess:
    def __init__(self, stdout_lines, return_code=0):
        self.stdout = [line.encode("utf-8") for line in stdout_lines]
        self.return_code = return_code

    def wait(self):
        return self.return_code


class VideoServiceTests(unittest.TestCase):
    def test_merge_video_and_audio_to_mp4_copies_mp4_video_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / "video.mp4"
            audio_path = temp_path / "audio.webm"
            output_path = temp_path / "output.mp4"
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")
            progress = []

            with (
                patch("engine.service.video.resolve_ffmpeg_executable", return_value="ffmpeg"),
                patch(
                    "engine.service.video.subprocess.Popen",
                    return_value=FakeProcess(
                        [
                            "out_time_ms=5000000\n",
                            "out_time_ms=10000000\n",
                            "progress=end\n",
                        ],
                    ),
                ) as popen,
            ):
                result = merge_video_and_audio_to_mp4(
                    video_path=video_path,
                    audio_path=audio_path,
                    output_path=output_path,
                    source_audio_bitrate_kbps=160,
                    max_audio_bitrate_kbps=320,
                    duration_seconds=10,
                    progress_callback=progress.append,
                )

        command = popen.call_args.args[0]
        self.assertEqual(result, output_path)
        self.assertIn("-c:v", command)
        self.assertIn("copy", command)
        self.assertIn("-c:a", command)
        self.assertIn("aac", command)
        self.assertIn("-b:a", command)
        self.assertIn("160k", command)
        self.assertIn("FFmpeg: 50%", progress)
        self.assertIn("FFmpeg: 100%", progress)

    def test_merge_video_and_audio_to_mp4_transcodes_non_mp4_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / "video.webm"
            audio_path = temp_path / "audio.webm"
            output_path = temp_path / "output.mp4"
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            with (
                patch("engine.service.video.resolve_ffmpeg_executable", return_value="ffmpeg"),
                patch(
                    "engine.service.video.subprocess.Popen",
                    return_value=FakeProcess(["progress=end\n"]),
                ) as popen,
            ):
                merge_video_and_audio_to_mp4(
                    video_path=video_path,
                    audio_path=audio_path,
                    output_path=output_path,
                    source_audio_bitrate_kbps=160,
                    max_audio_bitrate_kbps=320,
                    transcode_video=True,
                )

        command = popen.call_args.args[0]
        self.assertIn("libx264", command)
        self.assertIn("-preset", command)
        self.assertIn("-crf", command)

    def test_merge_video_and_audio_to_mp4_raises_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / "video.mp4"
            audio_path = temp_path / "audio.webm"
            output_path = temp_path / "output.mp4"
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            with (
                patch("engine.service.video.resolve_ffmpeg_executable", return_value="ffmpeg"),
                patch(
                    "engine.service.video.subprocess.Popen",
                    return_value=FakeProcess(["ffmpeg error\n"], return_code=1),
                ),
                self.assertRaises(VideoMergeError),
            ):
                merge_video_and_audio_to_mp4(
                    video_path=video_path,
                    audio_path=audio_path,
                    output_path=output_path,
                    source_audio_bitrate_kbps=160,
                    max_audio_bitrate_kbps=320,
                )


if __name__ == "__main__":
    unittest.main()
