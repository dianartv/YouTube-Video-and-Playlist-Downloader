from engine.youtube_tools.youtube_tools import YouTube, DownloadYTContent
from pytube.exceptions import VideoUnavailable
from engine.service.logger import logger

if __name__ == '__main__':

    video_url = 'https://www.youtube.com/watch?v=lSv8AgzfpKg'
    video_resolution = 720

    video = YouTube(url=video_url)

    try:
        save_from_yt = DownloadYTContent(video=video)
        save_from_yt.download_video(resolution=video_resolution)
    except VideoUnavailable:
        logger.warning(f'Видео {video_url} - недоступно.')
