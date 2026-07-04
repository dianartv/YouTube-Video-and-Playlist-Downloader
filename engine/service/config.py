from dataclasses import dataclass
from pathlib import Path


DEFAULT_DOWNLOAD_DIR = "content"
DEFAULT_AUDIO_DOWNLOAD_DIR = "content/audio"
DEFAULT_VIDEO_QUALITY = 720
DEFAULT_MP3_BITRATE = 320
DEFAULT_FFMPEG_PATH = "ffmpeg"
DEFAULT_FULL_AUTO = True
DEFAULT_DOWNLOAD_WORKER_LIMIT = 4
DEFAULT_PROCESS_WORKER_LIMIT = 4
DEFAULT_WORKER_LIMIT = DEFAULT_DOWNLOAD_WORKER_LIMIT
MIN_WORKER_LIMIT = 1
MAX_WORKER_LIMIT = 8
DEFAULT_ENV_PATH = Path(".env")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, init=False)
class AppConfig:
    download_dir: Path
    audio_download_dir: Path
    default_video_quality: int
    default_mp3_bitrate: int
    ffmpeg_path: str
    full_auto: bool
    download_worker_limit: int
    process_worker_limit: int

    def __init__(
        self,
        *,
        download_dir: Path,
        audio_download_dir: Path,
        default_video_quality: int,
        default_mp3_bitrate: int,
        ffmpeg_path: str,
        full_auto: bool,
        download_worker_limit: int | None = None,
        process_worker_limit: int | None = None,
        worker_limit: int | None = None,
    ) -> None:
        if worker_limit is not None:
            if download_worker_limit is None:
                download_worker_limit = worker_limit
            if process_worker_limit is None:
                process_worker_limit = worker_limit

        object.__setattr__(self, "download_dir", download_dir)
        object.__setattr__(self, "audio_download_dir", audio_download_dir)
        object.__setattr__(self, "default_video_quality", default_video_quality)
        object.__setattr__(self, "default_mp3_bitrate", default_mp3_bitrate)
        object.__setattr__(self, "ffmpeg_path", ffmpeg_path)
        object.__setattr__(self, "full_auto", full_auto)
        object.__setattr__(
            self,
            "download_worker_limit",
            _validate_worker_limit(
                DEFAULT_DOWNLOAD_WORKER_LIMIT if download_worker_limit is None else download_worker_limit,
                "DOWNLOAD_WORKER_LIMIT",
            ),
        )
        object.__setattr__(
            self,
            "process_worker_limit",
            _validate_worker_limit(
                DEFAULT_PROCESS_WORKER_LIMIT if process_worker_limit is None else process_worker_limit,
                "PROCESS_WORKER_LIMIT",
            ),
        )

    @property
    def worker_limit(self) -> int:
        return self.download_worker_limit


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
                f"DOWNLOAD_WORKER_LIMIT={DEFAULT_DOWNLOAD_WORKER_LIMIT}",
                f"PROCESS_WORKER_LIMIT={DEFAULT_PROCESS_WORKER_LIMIT}",
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
        "DOWNLOAD_WORKER_LIMIT": str(DEFAULT_DOWNLOAD_WORKER_LIMIT),
        "PROCESS_WORKER_LIMIT": str(DEFAULT_PROCESS_WORKER_LIMIT),
    }
    env_values = _read_env_file(path)
    values.update(env_values)
    legacy_worker_limit = env_values.get("WORKER_LIMIT")
    if legacy_worker_limit is not None:
        if "DOWNLOAD_WORKER_LIMIT" not in env_values:
            values["DOWNLOAD_WORKER_LIMIT"] = legacy_worker_limit
        if "PROCESS_WORKER_LIMIT" not in env_values:
            values["PROCESS_WORKER_LIMIT"] = legacy_worker_limit

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

    download_worker_limit = _parse_worker_limit(
        values["DOWNLOAD_WORKER_LIMIT"],
        "DOWNLOAD_WORKER_LIMIT",
    )
    process_worker_limit = _parse_worker_limit(
        values["PROCESS_WORKER_LIMIT"],
        "PROCESS_WORKER_LIMIT",
    )

    return AppConfig(
        download_dir=_resolve_download_dir(values["DOWNLOAD_DIR"]),
        audio_download_dir=_resolve_download_dir(values["AUDIO_DOWNLOAD_DIR"]),
        default_video_quality=default_video_quality,
        default_mp3_bitrate=default_mp3_bitrate,
        ffmpeg_path=values["FFMPEG_PATH"].strip() or DEFAULT_FFMPEG_PATH,
        full_auto=_parse_bool(values["FULL_AUTO"]),
        download_worker_limit=download_worker_limit,
        process_worker_limit=process_worker_limit,
    )


def save_worker_limit(value: int, path: Path = DEFAULT_ENV_PATH) -> None:
    save_parallel_limits(value, value, path)


def save_parallel_limits(
    download_worker_limit: int,
    process_worker_limit: int,
    path: Path = DEFAULT_ENV_PATH,
) -> None:
    download_limit = _validate_worker_limit(download_worker_limit, "DOWNLOAD_WORKER_LIMIT")
    process_limit = _validate_worker_limit(process_worker_limit, "PROCESS_WORKER_LIMIT")
    if not path.exists():
        ensure_env_file(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    values = {
        "DOWNLOAD_WORKER_LIMIT": str(download_limit),
        "PROCESS_WORKER_LIMIT": str(process_limit),
    }
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key, _ = stripped.split("=", 1)
        normalized_key = key.strip()
        if normalized_key == "WORKER_LIMIT":
            continue

        if normalized_key in values:
            new_lines.append(f"{normalized_key}={values[normalized_key]}")
            updated_keys.add(normalized_key)
            continue

        new_lines.append(line)

    for key, value in values.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


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


def _parse_worker_limit(raw_value: str, key: str) -> int:
    try:
        return _validate_worker_limit(int(raw_value), key)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer from 1 to 8") from exc


def _validate_worker_limit(value: int, key: str) -> int:
    if value < MIN_WORKER_LIMIT or value > MAX_WORKER_LIMIT:
        raise ValueError(f"{key} must be from 1 to 8")

    return value
