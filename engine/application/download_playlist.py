from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError, VideoUnavailable

from engine.application.download_duplicates import ConfirmOverwriteFunc
from engine.application.download_audio import download_audio
from engine.application.download_video import download_video
from engine.domain.download_history import DownloadHistory
from engine.domain.modes import AUDIO_MODE, VIDEO_MODE
from engine.domain.naming import DEFAULT_PLAYLIST_DIR_NAME, make_playlist_directory_name
from engine.service.logger import logger
from engine.youtube_tools.youtube_tools import Playlist, YouTube


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
PromptVideoResolutionFunc = Callable[[list[int], int, list[int] | None, InputFunc, PrintFunc], int]
PromptAudioStreamFunc = Callable[[list, int, InputFunc, PrintFunc], object]


def get_playlist_output_dir(config, media_mode: str, playlist_title: str | None) -> Path:
    base_dir = config.audio_download_dir if media_mode == AUDIO_MODE else config.download_dir
    return Path(base_dir) / make_playlist_directory_name(playlist_title)


def download_playlist(
    playlist: Playlist,
    media_mode: str,
    config,
    input_func: InputFunc,
    print_func: PrintFunc,
    prompt_video_resolution_func: PromptVideoResolutionFunc,
    prompt_audio_stream_func: PromptAudioStreamFunc,
    download_history: DownloadHistory | None = None,
    confirm_overwrite_func: ConfirmOverwriteFunc | None = None,
) -> int:
    if media_mode not in {VIDEO_MODE, AUDIO_MODE}:
        raise ValueError("media_mode must be video or audio")

    video_urls = list(playlist.video_urls)
    if not video_urls:
        print_func("Плейлист пуст.")
        return 1

    playlist_title = playlist.title or DEFAULT_PLAYLIST_DIR_NAME
    playlist_dir = get_playlist_output_dir(config, media_mode, playlist_title)
    playlist_dir.mkdir(parents=True, exist_ok=True)
    playlist_config = replace(
        config,
        download_dir=playlist_dir,
        audio_download_dir=playlist_dir,
    )

    print_func(f"Плейлист: {playlist_title}")
    print_func(f"Видео в плейлисте: {len(video_urls)}")
    print_func(f"Каталог плейлиста: {playlist_dir}")

    success_count = 0
    failed_count = 0

    for index, video_url in enumerate(video_urls, start=1):
        print_func(f"[{index}/{len(video_urls)}] {video_url}")
        try:
            video = YouTube(url=video_url)
            print_func(f"Видео: {video.title}")
            if media_mode == AUDIO_MODE:
                result = download_audio(
                    video=video,
                    config=playlist_config,
                    input_func=input_func,
                    print_func=print_func,
                    prompt_audio_stream_func=prompt_audio_stream_func,
                    download_history=download_history,
                    confirm_overwrite_func=confirm_overwrite_func,
                )
            else:
                result = download_video(
                    video=video,
                    config=playlist_config,
                    input_func=input_func,
                    print_func=print_func,
                    prompt_video_resolution_func=prompt_video_resolution_func,
                    prompt_audio_stream_func=prompt_audio_stream_func,
                    download_history=download_history,
                    confirm_overwrite_func=confirm_overwrite_func,
                )
        except LiveStreamError:
            logger.warning(f"Трансляция {video_url} ещё идёт.")
            print_func("Пропущено: активная live-трансляция.")
            failed_count += 1
            continue
        except LiveStreamEnded:
            logger.warning(f"Архив трансляции {video_url} ещё недоступен.")
            print_func("Пропущено: трансляция завершилась, но архив ещё недоступен.")
            failed_count += 1
            continue
        except VideoUnavailable:
            logger.warning(f"Видео {video_url} - недоступно.")
            print_func("Пропущено: видео недоступно.")
            failed_count += 1
            continue
        except Exception as exc:
            logger.exception(f"Не удалось скачать {video_url}: {exc}")
            print_func(f"Пропущено: ошибка загрузки: {exc}")
            failed_count += 1
            continue

        if result == 0:
            success_count += 1
        else:
            failed_count += 1

    print_func(f"Готово. Успешно: {success_count}. Пропущено/ошибок: {failed_count}.")
    return 0 if failed_count == 0 else 1
