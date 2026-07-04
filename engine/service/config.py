from dataclasses import dataclass
from pathlib import Path


DEFAULT_DOWNLOAD_DIR = "content"
DEFAULT_AUDIO_DOWNLOAD_DIR = "content/audio"
DEFAULT_VIDEO_QUALITY = 720
DEFAULT_MP3_BITRATE = 320
DEFAULT_FFMPEG_PATH = "ffmpeg"
DEFAULT_FULL_AUTO = True
DEFAULT_WORKER_LIMIT = 4
MIN_WORKER_LIMIT = 1
MAX_WORKER_LIMIT = 8
DEFAULT_ENV_PATH = Path(".env")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    download_dir: Path
    audio_download_dir: Path
    default_video_quality: int
    default_mp3_bitrate: int
    ffmpeg_path: str
    full_auto: bool
    worker_limit: int


def ensure_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    if path.exists():
        return

    path.write_text(
        "\n".join(
            [
                f"DOWNLOAD_DIR={DEFAULT_DOWNLOAD_DIR}",
                f"AUDIO_DOWNLOAD_DIR={DEFAULT_AUDIO_DOWNLOAD_DIR}",
                f"DEFAULT_VIDEO_QUALITY={DEFAULT_VIDEO_QUALITY}",
                f"DEFAULT_MP3_BITRATE={DEFAULT_MP3_BITRATE}",
                f"FFMPEG_PATH={DEFAULT_FFMPEG_PATH}",
                f"FULL_AUTO={int(DEFAULT_FULL_AUTO)}",
                f"WORKER_LIMIT={DEFAULT_WORKER_LIMIT}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def load_config(path: Path = DEFAULT_ENV_PATH) -> AppConfig:
    values = {
        "DOWNLOAD_DIR": DEFAULT_DOWNLOAD_DIR,
        "AUDIO_DOWNLOAD_DIR": DEFAULT_AUDIO_DOWNLOAD_DIR,
        "DEFAULT_VIDEO_QUALITY": str(DEFAULT_VIDEO_QUALITY),
        "DEFAULT_MP3_BITRATE": str(DEFAULT_MP3_BITRATE),
        "FFMPEG_PATH": DEFAULT_FFMPEG_PATH,
        "FULL_AUTO": str(int(DEFAULT_FULL_AUTO)),
        "WORKER_LIMIT": str(DEFAULT_WORKER_LIMIT),
    }
    values.update(_read_env_file(path))

    try:
        default_video_quality = int(values["DEFAULT_VIDEO_QUALITY"])
    except ValueError as exc:
        raise ValueError("DEFAULT_VIDEO_QUALITY must be an integer") from exc

    if default_video_quality <= 0:
        raise ValueError("DEFAULT_VIDEO_QUALITY must be greater than zero")

    try:
        default_mp3_bitrate = int(values["DEFAULT_MP3_BITRATE"])
    except ValueError as exc:
        raise ValueError("DEFAULT_MP3_BITRATE must be an integer") from exc

    if default_mp3_bitrate <= 0:
        raise ValueError("DEFAULT_MP3_BITRATE must be greater than zero")

    worker_limit = _parse_worker_limit(values["WORKER_LIMIT"])

    return AppConfig(
        download_dir=_resolve_download_dir(values["DOWNLOAD_DIR"]),
        audio_download_dir=_resolve_download_dir(values["AUDIO_DOWNLOAD_DIR"]),
        default_video_quality=default_video_quality,
        default_mp3_bitrate=default_mp3_bitrate,
        ffmpeg_path=values["FFMPEG_PATH"].strip() or DEFAULT_FFMPEG_PATH,
        full_auto=_parse_bool(values["FULL_AUTO"]),
        worker_limit=worker_limit,
    )


def save_worker_limit(value: int, path: Path = DEFAULT_ENV_PATH) -> None:
    worker_limit = _validate_worker_limit(value)
    if not path.exists():
        ensure_env_file(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _ = stripped.split("=", 1)
        if key.strip() == "WORKER_LIMIT":
            lines[index] = f"WORKER_LIMIT={worker_limit}"
            updated = True
            break

    if not updated:
        lines.append(f"WORKER_LIMIT={worker_limit}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise ValueError(f"Malformed .env line: {line}")

        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("'\"")

    return result


def _resolve_download_dir(raw_value: str) -> Path:
    value = raw_value.strip()
    if not value:
        raise ValueError("DOWNLOAD_DIR must not be empty")

    path = Path(value)
    if path.is_absolute():
        raise ValueError("DOWNLOAD_DIR must be a relative path")

    if ".." in path.parts:
        raise ValueError("DOWNLOAD_DIR must stay inside the project")

    project_root = PROJECT_ROOT.resolve()
    download_dir = (project_root / path).resolve()
    if not download_dir.is_relative_to(project_root):
        raise ValueError("DOWNLOAD_DIR must stay inside the project")

    return download_dir


def _parse_bool(raw_value: str) -> bool:
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True

    if value in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError("FULL_AUTO must be 1 or 0")


def _parse_worker_limit(raw_value: str) -> int:
    try:
        return _validate_worker_limit(int(raw_value))
    except ValueError as exc:
        raise ValueError("WORKER_LIMIT must be an integer from 1 to 8") from exc


def _validate_worker_limit(value: int) -> int:
    if value < MIN_WORKER_LIMIT or value > MAX_WORKER_LIMIT:
        raise ValueError("WORKER_LIMIT must be from 1 to 8")

    return value
