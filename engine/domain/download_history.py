from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DownloadRecord:
    video_id: str
    media_type: str
    title: str
    output_path: Path
    source_url: str
    video_resolution: int | None = None
    video_itag: int | None = None
    audio_bitrate: int | None = None
    audio_itag: int | None = None
    output_bitrate: int | None = None
    container: str | None = None
    file_size_bytes: int | None = None
    downloaded_at: str = ""


class DownloadHistory(Protocol):
    def find(self, video_id: str, media_type: str) -> DownloadRecord | None:
        pass

    def upsert(self, record: DownloadRecord) -> None:
        pass
