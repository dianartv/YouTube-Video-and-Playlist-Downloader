from engine.youtube_tools.youtube_tools import YouTube, DownloadYTContent
from pytube.exceptions import VideoUnavailable
from engine.service.logger import logger


if __name__ == '__main__':

    video_url = 'https://www.youtube.com/watch?v=d-fq6IOu8XA'

    try:
        save_from_yt = DownloadYTContent(video=YouTube(url=video_url))
        save_from_yt.download_audio()

    except VideoUnavailable:
        logger.warning(f'Видео {video_url} - недоступно.')
