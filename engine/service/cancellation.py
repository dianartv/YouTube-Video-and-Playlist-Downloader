import subprocess
import threading
from pathlib import Path


class OperationCancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._paths: set[Path] = set()
        self._processes: set[subprocess.Popen] = set()

    def cancel(self) -> None:
        self._cancelled.set()
        self.terminate_processes()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise OperationCancelled("Операция отменена.")

    def register_path(self, path: str | Path | None) -> None:
        if path is None:
            return

        with self._lock:
            self._paths.add(Path(path))

    def register_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.add(process)
            should_terminate = self.is_cancelled()

        if should_terminate and process.poll() is None:
            process.terminate()

    def unregister_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def terminate_processes(self) -> None:
        with self._lock:
            processes = list(self._processes)

        for process in processes:
            if process.poll() is None:
                process.terminate()

    def cleanup_paths(self) -> None:
        with self._lock:
            paths = sorted(self._paths, key=lambda value: len(value.parts), reverse=True)

        for path in paths:
            _delete_path(path)


def _delete_path(path: Path) -> None:
    try:
        if path.is_dir():
            path.rmdir()
        elif path.exists():
            path.unlink()
    except OSError:
        pass
