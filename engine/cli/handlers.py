from collections.abc import Callable

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError, VideoUnavailable

from engine.application.download_audio import download_audio as run_audio_download
from engine.application.download_playlist import download_playlist
from engine.application.download_video import download_video as run_video_download
from engine.cli.prompts import (
    prompt_audio_stream,
    prompt_overwrite_download,
    prompt_video_resolution,
)
from engine.domain.modes import AUDIO_MODE, VIDEO_MODE
from engine.service.config import ensure_env_file, load_config
from engine.service.download_history import SQLiteDownloadHistory
from engine.service.logger import configure_file_logger, logger
from engine.youtube_tools.youtube_tools import Playlist, YouTube


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]


def download_media_interactive(
    mode: str,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    if mode not in {VIDEO_MODE, AUDIO_MODE}:
        raise ValueError("mode must be video or audio")

    configure_file_logger()
    ensure_env_file()
    config = load_config()

    video_url = input_func("Вставьте ссылку на видео: ").strip()
    if not video_url:
        print_func("Ссылка не указана.")
        return 1

    try:
        download_history = SQLiteDownloadHistory.default()
        video = YouTube(url=video_url)
        print_func(f"Видео: {video.title}")
        if mode == AUDIO_MODE:
            return run_audio_download(
                video=video,
                config=config,
                input_func=input_func,
                print_func=print_func,
                prompt_audio_stream_func=prompt_audio_stream,
                download_history=download_history,
                confirm_overwrite_func=lambda existing, planned: prompt_overwrite_download(
                    existing,
                    planned,
                    input_func,
                    print_func,
                ),
            )

        return run_video_download(
            video=video,
            config=config,
            input_func=input_func,
            print_func=print_func,
            prompt_video_resolution_func=prompt_video_resolution,
            prompt_audio_stream_func=prompt_audio_stream,
            download_history=download_history,
            confirm_overwrite_func=lambda existing, planned: prompt_overwrite_download(
                existing,
                planned,
                input_func,
                print_func,
            ),
        )
    except LiveStreamError:
        logger.warning(f"Трансляция {video_url} ещё идёт.")
        print_func("Активные live-трансляции не скачиваются. Дождитесь завершения и публикации архива.")
        return 1
    except LiveStreamEnded:
        logger.warning(f"Архив трансляции {video_url} ещё недоступен.")
        print_func(
            "Трансляция завершилась, но YouTube ещё не отдаёт архив как обычное видео. "
            "Повторите позже."
        )
        return 1
    except VideoUnavailable:
        logger.warning(f"Видео {video_url} - недоступно.")
        print_func("Видео недоступно.")
        return 1


def download_playlist_interactive(
    media_mode: str,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    configure_file_logger()
    ensure_env_file()
    config = load_config()

    playlist_url = input_func("Вставьте ссылку на плейлист: ").strip()
    if not playlist_url:
        print_func("Ссылка не указана.")
        return 1

    download_history = SQLiteDownloadHistory.default()
    playlist = Playlist(playlist_url)
    return download_playlist(
        playlist=playlist,
        media_mode=media_mode,
        config=config,
        input_func=input_func,
        print_func=print_func,
        prompt_video_resolution_func=prompt_video_resolution,
        prompt_audio_stream_func=prompt_audio_stream,
        download_history=download_history,
        confirm_overwrite_func=lambda existing, planned: prompt_overwrite_download(
            existing,
            planned,
            input_func,
            print_func,
        ),
    )


def download_video_interactive(
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    return download_media_interactive(
        mode=VIDEO_MODE,
        input_func=input_func,
        print_func=print_func,
    )
