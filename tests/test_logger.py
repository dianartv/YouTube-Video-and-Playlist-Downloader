import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LoggerTests(unittest.TestCase):
    def test_import_does_not_create_logs_directory(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(repo_root), env.get("PYTHONPATH")])
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            code = (
                "from pathlib import Path\n"
                "import engine.service.logger\n"
                "assert not Path('logs').exists()\n"
            )
            subprocess.run(
                [sys.executable, "-c", code],
                cwd=temp_dir,
                env=env,
                check=True,
            )

    def test_configure_file_logger_creates_logs_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(repo_root), env.get("PYTHONPATH")])
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            code = (
                "from pathlib import Path\n"
                "from engine.service.logger import configure_file_logger, logger\n"
                "configure_file_logger()\n"
                "logger.info('ready')\n"
                "assert Path('logs/logs.log').is_file()\n"
            )
            subprocess.run(
                [sys.executable, "-c", code],
                cwd=temp_dir,
                env=env,
                check=True,
            )


if __name__ == "__main__":
    unittest.main()
