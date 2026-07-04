DEFAULT_PLAYLIST_DIR_NAME = "playlist"
DEFAULT_VIDEO_FILE_STEM = "video"
FORBIDDEN_PATH_CHARS = r'\/?:*"><|'


def make_playlist_directory_name(title: str | None) -> str:
    name = make_safe_path_name(title)
    return name or DEFAULT_PLAYLIST_DIR_NAME


def make_video_file_stem(title: str | None) -> str:
    name = make_safe_path_name(title)
    return name or DEFAULT_VIDEO_FILE_STEM


def make_safe_path_name(value: str | None) -> str:
    cleaned = "".join(char for char in value or "" if char not in FORBIDDEN_PATH_CHARS)
    return cleaned.strip().strip(".")

