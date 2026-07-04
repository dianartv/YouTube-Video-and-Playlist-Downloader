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

Run the downloader through `uv` with an explicit mode flag, then paste a
YouTube URL.

```powershell
uv run python main.py --video
uv run python main.py --audio
```

Use `--video` to download the best video stream that already includes audio.
Use `--audio` or `--audio-only` to download the best audio stream and convert it
to MP3.

Default values are stored in `.env`:

```dotenv
DOWNLOAD_DIR=content
AUDIO_DOWNLOAD_DIR=content/audio
DEFAULT_VIDEO_QUALITY=720
DEFAULT_MP3_BITRATE=320
FFMPEG_PATH=ffmpeg
FULL_AUTO=1
```

Downloaded videos are written to `content/`. Audio-only MP3 files are written
to `content/audio/`. Runtime logs are written to `logs/`. Runtime output
directories are ignored by Git.

MP3 conversion uses FFmpeg. If `FFMPEG_PATH` is not available on the system
PATH, the app falls back to the `imageio-ffmpeg` bundled executable. MP3 bitrate
is capped at the downloaded audio bitrate; if the source bitrate is unknown,
`DEFAULT_MP3_BITRATE` is used.

`FULL_AUTO=1` keeps the interaction short: paste a link, choose video or audio,
then the app downloads the best available video-with-audio or best audio track.
Set `FULL_AUTO=0` to choose video quality or audio stream manually.

High-quality YouTube streams can be video-only. The current downloader skips
those in interactive mode so the saved file has audio. Supporting those
qualities would require a separate audio download and an FFmpeg/yt-dlp merge
step.

## Tests

```powershell
uv run python -m unittest discover -v
```
