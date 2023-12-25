from engine.youtube_tools.youtube_tools import YouTube, DownloadYTVideo
from pytube.exceptions import VideoUnavailable
from engine.service.logger import logger

if __name__ == '__main__':

    video_url = ''
    video_resolution = 720
    saved_videos_dir = r'data\videos'

    video = YouTube(url=video_url)

    try:
        save_from_yt = DownloadYTVideo(video=video)
        save_from_yt.download(resolution=video_resolution,
                              save_to=saved_videos_dir)
    except VideoUnavailable:
        logger.warning(f'Видео {video_url} - недоступно.')
