import tempfile
import unittest
from pathlib import Path

from engine.service.cancellation import CancellationToken, OperationCancelled


class FakeProcess:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True


class CancellationTokenTests(unittest.TestCase):
    def test_cancel_marks_token_and_terminates_registered_processes(self):
        token = CancellationToken()
        process = FakeProcess()
        token.register_process(process)

        token.cancel()

        self.assertTrue(token.is_cancelled())
        self.assertTrue(process.terminated)

    def test_register_process_terminates_when_already_cancelled(self):
        token = CancellationToken()
        process = FakeProcess()

        token.cancel()
        token.register_process(process)

        self.assertTrue(process.terminated)

    def test_raise_if_cancelled_raises_operation_cancelled(self):
        token = CancellationToken()
        token.cancel()

        with self.assertRaises(OperationCancelled):
            token.raise_if_cancelled()

    def test_cleanup_paths_deletes_registered_files_for_current_operation(self):
        token = CancellationToken()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.webm"
            partial = Path(temp_dir) / "partial.mp3"
            source.write_bytes(b"source")
            partial.write_bytes(b"partial")
            token.register_path(source)
            token.register_path(partial)

            token.cleanup_paths()

            self.assertFalse(source.exists())
            self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
