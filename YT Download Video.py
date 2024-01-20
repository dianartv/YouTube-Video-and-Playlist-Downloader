from engine.youtube_tools.youtube_tools import VideoDownloader
from pytube.exceptions import VideoUnavailable
from engine.service.logger import logger

if __name__ == '__main__':

    video_url = 'https://youtu.be/vZwbA6QTheo'

    video = VideoDownloader(
        video_url=video_url,
    )

    try:
        video.download()
    except VideoUnavailable:
        logger.warning(f'Видео {video_url} - недоступно.')
