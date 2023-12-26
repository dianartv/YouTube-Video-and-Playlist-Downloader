import os

from engine.service.tools import remove_temporary_files
from engine.youtube_tools.youtube_tools import YouTube, DownloadYTVideo
from pytube.exceptions import VideoUnavailable
from engine.service.logger import logger
from engine.converter.converter import convert_video_to_audio_ffmpeg


if __name__ == '__main__':

    video_url = 'https://www.youtube.com/watch?v=fc_JnGYWQrw'
    saved_audio_dir = r'data/audios'

    video = YouTube(url=video_url)

    try:
        save_from_yt = DownloadYTVideo(video=video)
        save_from_yt.download_audio(save_to=saved_audio_dir)

        saved_tmp_video_name = 'data/audios/' + video.default_filename
        saved_tmp_video_path = f'data/audios/{video.default_filename}'

        convert_video_to_audio_ffmpeg(video_file=saved_tmp_video_path)

        script_dir = os.path.dirname(os.path.realpath(__file__))
        remove_temporary_files(folder=f'{script_dir}/{saved_audio_dir}')

    except VideoUnavailable:
        logger.warning(f'Видео {video_url} - недоступно.')
