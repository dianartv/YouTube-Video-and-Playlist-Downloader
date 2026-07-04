# YouTube Video and Playlist Downloader

Small Python scripts for downloading YouTube videos and playlists with
`pytubefix`.

## Requirements

- Python 3.14
- `uv`

The project uses `.python-version`, `pyproject.toml`, and `uv.lock` instead of
`requirements.txt`.

## Setup

```powershell
uv sync
```

## Usage

Run the desktop GUI through `uv`, then use the tabs for video, audio, playlist,
or settings.

```powershell
uv run python main.py
```

Video downloads use the best video stream not higher than the selected quality,
download the best audio stream separately, and merge them into an MP4 file with
FFmpeg. Audio downloads use the best audio stream and convert it to MP3.
Playlist mode processes every item from a YouTube playlist. The playlist
directory name is taken from the YouTube playlist title automatically.

Default values are stored in `.env`:

```dotenv
DOWNLOAD_DIR=content
AUDIO_DOWNLOAD_DIR=content/audio
DEFAULT_VIDEO_QUALITY=720
DEFAULT_MP3_BITRATE=320
FFMPEG_PATH=ffmpeg
DOWNLOAD_WORKER_LIMIT=4
PROCESS_WORKER_LIMIT=4
```

Downloaded videos are written to `content/`. Audio-only MP3 files are written
to `content/audio/`. Runtime logs are written to `logs/`. Runtime output
directories are ignored by Git.

Playlist videos are written to `content/<playlist title>/`. Playlist audio MP3
files are written to `content/audio/<playlist title>/`.

Download history is stored in `content/.downloads.sqlite3`. If the same
YouTube video is requested again for the same mode (`video` or `audio`) and the
previous final file still exists, the app shows the saved quality and asks
whether to overwrite. If the history entry exists but the final file was
deleted, the app downloads normally and refreshes the history entry.

Finished YouTube live broadcasts are downloaded like regular videos after
YouTube publishes the archive streams. Active live streams are not downloaded;
if an ended stream is not available as an archive yet, retry later.

MP3 conversion uses FFmpeg. If `FFMPEG_PATH` is not available on the system
PATH, the app falls back to the `imageio-ffmpeg` bundled executable. MP3 bitrate
is capped at the downloaded audio bitrate; if the source bitrate is unknown,
`DEFAULT_MP3_BITRATE` is used.

Video mode also uses FFmpeg. The GUI shows download and conversion progress in
the progress bar. MP4 video streams are copied without re-encoding; non-MP4
video streams are transcoded to H.264 before saving the final MP4.

`DOWNLOAD_WORKER_LIMIT` limits simultaneous downloads in bulk-style flows.
`PROCESS_WORKER_LIMIT` limits simultaneous FFmpeg processing tasks.

## Tests

```powershell
uv run python -m unittest discover -v
```
