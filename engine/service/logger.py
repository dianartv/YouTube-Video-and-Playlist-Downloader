import logging
from pathlib import Path

logger = logging.getLogger("youtube_downloader")
logger.setLevel(logging.INFO)


def configure_file_logger(log_dir: str | Path = "logs") -> None:
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)
    log_file = (log_dir / "logs.log").resolve()

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            if Path(handler.baseFilename).resolve() == log_file:
                return

    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
