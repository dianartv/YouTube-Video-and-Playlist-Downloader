import shutil
import tempfile
import unittest
from pathlib import Path

from engine.service.config import (
    DEFAULT_AUDIO_DOWNLOAD_DIR,
    DEFAULT_DOWNLOAD_WORKER_LIMIT,
    DEFAULT_FFMPEG_PATH,
    DEFAULT_FULL_AUTO,
    DEFAULT_MP3_BITRATE,
    DEFAULT_PROCESS_WORKER_LIMIT,
    DEFAULT_VIDEO_QUALITY,
    PROJECT_ROOT,
    ensure_env_file,
    load_config,
    save_parallel_limits,
)


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_defaults_when_env_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / ".env")

        self.assertEqual(config.download_dir, PROJECT_ROOT / "content")
        self.assertEqual(config.audio_download_dir, PROJECT_ROOT / DEFAULT_AUDIO_DOWNLOAD_DIR)
        self.assertEqual(config.default_video_quality, DEFAULT_VIDEO_QUALITY)
        self.assertEqual(config.default_mp3_bitrate, DEFAULT_MP3_BITRATE)
        self.assertEqual(config.ffmpeg_path, DEFAULT_FFMPEG_PATH)
        self.assertEqual(config.full_auto, DEFAULT_FULL_AUTO)
        self.assertEqual(config.download_worker_limit, DEFAULT_DOWNLOAD_WORKER_LIMIT)
        self.assertEqual(config.process_worker_limit, DEFAULT_PROCESS_WORKER_LIMIT)

    def test_ensure_env_file_writes_default_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"

            ensure_env_file(env_path)
            config = load_config(env_path)

        self.assertEqual(config.download_dir, PROJECT_ROOT / "content")
        self.assertEqual(config.audio_download_dir, PROJECT_ROOT / "content" / "audio")
        self.assertEqual(config.default_video_quality, 720)
        self.assertEqual(config.default_mp3_bitrate, 320)
        self.assertEqual(config.ffmpeg_path, "ffmpeg")
        self.assertTrue(config.full_auto)
        self.assertEqual(config.download_worker_limit, 4)
        self.assertEqual(config.process_worker_limit, 4)

    def test_load_config_reads_custom_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DOWNLOAD_DIR=downloads",
                        "AUDIO_DOWNLOAD_DIR=downloads/audio",
                        "DEFAULT_VIDEO_QUALITY=1080",
                        "DEFAULT_MP3_BITRATE=192",
                        "FFMPEG_PATH=tools/ffmpeg.exe",
                        "FULL_AUTO=0",
                        "DOWNLOAD_WORKER_LIMIT=7",
                        "PROCESS_WORKER_LIMIT=3",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(env_path)

        self.assertEqual(config.download_dir, PROJECT_ROOT / "downloads")
        self.assertEqual(config.audio_download_dir, PROJECT_ROOT / "downloads" / "audio")
        self.assertEqual(config.default_video_quality, 1080)
        self.assertEqual(config.default_mp3_bitrate, 192)
        self.assertEqual(config.ffmpeg_path, "tools/ffmpeg.exe")
        self.assertFalse(config.full_auto)
        self.assertEqual(config.download_worker_limit, 7)
        self.assertEqual(config.process_worker_limit, 3)

    def test_load_config_uses_legacy_worker_limit_as_parallel_limits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("WORKER_LIMIT=7\n", encoding="utf-8")

            config = load_config(env_path)

        self.assertEqual(config.download_worker_limit, 7)
        self.assertEqual(config.process_worker_limit, 7)

    def test_load_config_rejects_invalid_default_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DEFAULT_VIDEO_QUALITY=fullhd\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_empty_download_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DOWNLOAD_DIR=\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_absolute_download_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(f"DOWNLOAD_DIR={Path(temp_dir)}\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_parent_traversal_download_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DOWNLOAD_DIR=../outside\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_symlink_escape_download_dir(self):
        link_path = PROJECT_ROOT / ".tmp-download-dir-link"
        outside_dir = Path(tempfile.mkdtemp())

        try:
            try:
                link_path.symlink_to(outside_dir, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"Cannot create directory symlink: {exc}")

            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text(
                    f"DOWNLOAD_DIR={link_path.name}\n",
                    encoding="utf-8",
                )

                with self.assertRaises(ValueError):
                    load_config(env_path)
        finally:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_load_config_rejects_non_positive_default_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DEFAULT_VIDEO_QUALITY=0\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_invalid_mp3_bitrate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DEFAULT_MP3_BITRATE=best\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_non_positive_mp3_bitrate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DEFAULT_MP3_BITRATE=0\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DOWNLOAD_DIR content\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_invalid_full_auto_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("FULL_AUTO=maybe\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config(env_path)

    def test_load_config_rejects_invalid_parallel_limits(self):
        invalid_values = ["0", "9", "many"]
        keys = ["DOWNLOAD_WORKER_LIMIT", "PROCESS_WORKER_LIMIT"]
        for key in keys:
            for value in invalid_values:
                with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as temp_dir:
                    env_path = Path(temp_dir) / ".env"
                    env_path.write_text(f"{key}={value}\n", encoding="utf-8")

                    with self.assertRaises(ValueError):
                        load_config(env_path)

    def test_load_config_rejects_invalid_legacy_worker_limit(self):
        invalid_values = ["0", "9", "many"]
        for value in invalid_values:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text(f"WORKER_LIMIT={value}\n", encoding="utf-8")

                with self.assertRaises(ValueError):
                    load_config(env_path)

    def test_save_parallel_limits_updates_existing_env_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            ensure_env_file(env_path)

            save_parallel_limits(6, 2, env_path)
            config = load_config(env_path)
            env_text = env_path.read_text(encoding="utf-8")

        self.assertEqual(config.download_worker_limit, 6)
        self.assertEqual(config.process_worker_limit, 2)
        self.assertNotIn("\nWORKER_LIMIT=", f"\n{env_text}")

    def test_save_parallel_limits_appends_missing_env_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DOWNLOAD_DIR=content\n", encoding="utf-8")

            save_parallel_limits(3, 5, env_path)
            config = load_config(env_path)

        self.assertEqual(config.download_worker_limit, 3)
        self.assertEqual(config.process_worker_limit, 5)


if __name__ == "__main__":
    unittest.main()
