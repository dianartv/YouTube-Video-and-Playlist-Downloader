import subprocess
import os


def convert_video_to_audio_ffmpeg(video_file, output_ext="mp3"):
    """Converts video to audio directly using `ffmpeg` command
    with the help of subprocess module"""
    filename, ext = os.path.splitext(video_file)
    subprocess.call(
        ["ffmpeg", "-y", "-i", video_file, f"{filename}.{output_ext}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )
