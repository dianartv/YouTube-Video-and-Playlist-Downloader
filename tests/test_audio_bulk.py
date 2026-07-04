import unittest
from threading import Lock
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch

from engine.application.download_audio_bulk import download_audio_bulk
from engine.service.cancellation import CancellationToken, OperationCancelled


class AudioBulkTests(unittest.TestCase):
    def test_bulk_download_skips_broken_links_and_prints_summary(self):
        output = []
        config = SimpleNamespace(worker_limit=2)

        def youtube(url):
            if url == "bad":
                raise ValueError("bad url")

            return SimpleNamespace(title=f"Title {url}")

        with (
            patch("engine.application.download_audio_bulk.YouTube", side_effect=youtube),
            patch("engine.application.download_audio_bulk.download_audio", return_value=0) as download_audio,
        ):
            result = download_audio_bulk(
                urls=["one", "bad", "two"],
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 1)
        self.assertEqual(download_audio.call_count, 2)
        self.assertIn("Итог списка ссылок:", output)
        self.assertIn("Успешно: 2. Пропущено/ошибок: 1.", output)
        self.assertIn("2. bad — bad url", output)

    def test_bulk_download_returns_success_when_all_links_finish(self):
        output = []
        config = SimpleNamespace(worker_limit=2)

        with (
            patch(
                "engine.application.download_audio_bulk.YouTube",
                side_effect=lambda url: SimpleNamespace(title=f"Title {url}"),
            ),
            patch("engine.application.download_audio_bulk.download_audio", return_value=0),
        ):
            result = download_audio_bulk(
                urls=["one", "two"],
                config=config,
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 0)
        self.assertIn("Успешно: 2. Пропущено/ошибок: 0.", output)

    def test_bulk_download_limits_processing_separately_from_downloads(self):
        output = []
        active_processing = 0
        max_active_processing = 0
        lock = Lock()

        def download_audio(**kwargs):
            nonlocal active_processing
            nonlocal max_active_processing

            with kwargs["processing_limiter"]:
                with lock:
                    active_processing += 1
                    max_active_processing = max(max_active_processing, active_processing)
                sleep(0.01)
                with lock:
                    active_processing -= 1

            return 0

        with (
            patch(
                "engine.application.download_audio_bulk.YouTube",
                side_effect=lambda url: SimpleNamespace(title=f"Title {url}"),
            ),
            patch("engine.application.download_audio_bulk.download_audio", side_effect=download_audio),
        ):
            result = download_audio_bulk(
                urls=["one", "two", "three"],
                config=SimpleNamespace(download_worker_limit=3, process_worker_limit=1),
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=output.append,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
            )

        self.assertEqual(result, 0)
        self.assertEqual(max_active_processing, 1)
        self.assertIn(
            "Список ссылок: 3. Параллельных скачиваний: 3. Одновременных обработок: 1.",
            output,
        )

    def test_bulk_download_honors_cancellation_before_youtube_request(self):
        token = CancellationToken()
        token.cancel()

        with (
            patch("engine.application.download_audio_bulk.YouTube") as youtube,
            self.assertRaises(OperationCancelled),
        ):
            download_audio_bulk(
                urls=["one", "two"],
                config=SimpleNamespace(worker_limit=2),
                input_func=lambda prompt: self.fail("input should not be called"),
                print_func=lambda message: None,
                prompt_audio_stream_func=lambda *args: self.fail("audio prompt should not be called"),
                cancel_token=token,
            )

        youtube.assert_not_called()


if __name__ == "__main__":
    unittest.main()
