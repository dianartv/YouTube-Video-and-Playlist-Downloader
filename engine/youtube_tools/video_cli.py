from dataclasses import replace
from pathlib import Path
from typing import Callable

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError, VideoUnavailable

from engine.service.audio import (
    AudioConversionError,
    choose_mp3_bitrate,
    convert_to_mp3,
    parse_bitrate_kbps,
)
from engine.service.config import ensure_env_file, load_config
from engine.service.logger import configure_file_logger, logger
from engine.service.tools import make_allowed_format
from engine.service.video import VideoMergeError, merge_video_and_audio_to_mp4
from engine.youtube_tools.youtube_tools import (
    DownloadYTAudio,
    Playlist,
    YouTube,
    get_audio_streams,
    get_best_video_stream_for_resolution,
    get_video_resolutions_no_higher_than,
    get_video_streams_no_higher_than,
)


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
VIDEO_MODE = "video"
AUDIO_MODE = "audio"
DEFAULT_PLAYLIST_DIR_NAME = "playlist"


def choose_video_resolution(
    available_resolutions: list[int],
    default_resolution: int,
    user_choice: str,
) -> int:
    if not available_resolutions:
        raise ValueError("Список доступных качеств пуст.")

    effective_default = (
        default_resolution
        if default_resolution in available_resolutions
        else available_resolutions[0]
    )

    choice = user_choice.strip().lower().removesuffix("p")
    if not choice:
        return effective_default

    if not choice.isdigit():
        raise ValueError("Введите номер из списка, качество в формате 720 или нажмите Enter.")

    value = int(choice)
    if 1 <= value <= len(available_resolutions):
        return available_resolutions[value - 1]

    if value in available_resolutions:
        return value

    raise ValueError("Такого качества нет в списке доступных.")


def prompt_video_resolution(
    available_resolutions: list[int],
    default_resolution: int,
    video_only_resolutions: list[int] | None = None,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    print_func("Доступное качество видео:")
    for index, resolution in enumerate(available_resolutions, start=1):
        print_func(f"{index}. {resolution}p")

    if video_only_resolutions:
        values = ", ".join(f"{resolution}p" for resolution in video_only_resolutions)
        print_func(f"Без аудио, не скачивается в этом режиме: {values}")

    effective_default = (
        default_resolution
        if default_resolution in available_resolutions
        else available_resolutions[0]
    )
    if effective_default != default_resolution:
        print_func(
            f"Качество {default_resolution}p из .env недоступно. "
            f"По Enter будет выбрано {effective_default}p."
        )

    while True:
        choice = input_func(
            f"Выберите номер/качество или нажмите Enter для {effective_default}p: "
        )
        try:
            return choose_video_resolution(
                available_resolutions=available_resolutions,
                default_resolution=default_resolution,
                user_choice=choice,
            )
        except ValueError as exc:
            print_func(str(exc))


def choose_audio_stream(audio_streams: list, user_choice: str):
    if not audio_streams:
        raise ValueError("Список аудио-дорожек пуст.")

    choice = user_choice.strip()
    if not choice:
        return audio_streams[0]

    if not choice.isdigit():
        raise ValueError("Введите номер из списка, itag или нажмите Enter.")

    value = int(choice)
    if 1 <= value <= len(audio_streams):
        return audio_streams[value - 1]

    for stream in audio_streams:
        if stream.itag == value:
            return stream

    raise ValueError("Такой аудио-дорожки нет в списке.")


def prompt_audio_stream(
    audio_streams: list,
    max_mp3_bitrate: int,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
):
    print_func("Доступные аудио-дорожки:")
    for index, stream in enumerate(audio_streams, start=1):
        source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
        target_bitrate = choose_mp3_bitrate(source_bitrate, max_mp3_bitrate)
        subtype = getattr(stream, "subtype", "unknown")
        print_func(
            f"{index}. {stream.abr} {subtype} "
            f"(itag {stream.itag}, mp3 {target_bitrate}kbps)"
        )

    while True:
        try:
            return choose_audio_stream(
                audio_streams=audio_streams,
                user_choice=input_func("Выберите аудио или нажмите Enter для лучшего: "),
            )
        except ValueError as exc:
            print_func(str(exc))


def make_playlist_directory_name(title: str | None) -> str:
    name = make_allowed_format(title or "").strip().strip(".")
    return name or DEFAULT_PLAYLIST_DIR_NAME


def get_playlist_output_dir(config, media_mode: str, playlist_title: str | None) -> Path:
    base_dir = config.audio_download_dir if media_mode == AUDIO_MODE else config.download_dir
    return Path(base_dir) / make_playlist_directory_name(playlist_title)


def make_video_file_stem(title: str | None) -> str:
    name = make_allowed_format(title or "").strip().strip(".")
    return name or "video"


def describe_video_stream(stream) -> str:
    resolution = getattr(stream, "resolution", "unknown")
    subtype = getattr(stream, "subtype", "unknown")
    itag = getattr(stream, "itag", "unknown")
    fps = getattr(stream, "fps", None)
    fps_text = f", {fps}fps" if fps else ""
    return f"{resolution} {subtype}{fps_text} (itag {itag})"


def describe_audio_stream(stream, max_bitrate_kbps: int) -> str:
    source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
    target_bitrate = choose_mp3_bitrate(source_bitrate, max_bitrate_kbps)
    subtype = getattr(stream, "subtype", "unknown")
    itag = getattr(stream, "itag", "unknown")
    return f"{stream.abr} {subtype} (itag {itag}, AAC {target_bitrate}kbps)"


def download_video(video: YouTube, config, input_func: InputFunc, print_func: PrintFunc) -> int:
    video_streams = get_video_streams_no_higher_than(
        video,
        max_resolution=config.default_video_quality,
    )
    if not video_streams:
        print_func(
            f"Не удалось получить видеопотоки не выше {config.default_video_quality}p."
        )
        return 1

    audio_streams = get_audio_streams(video)
    if not audio_streams:
        print_func("Не удалось получить список аудио-дорожек.")
        return 1

    available_resolutions = get_video_resolutions_no_higher_than(
        video,
        max_resolution=config.default_video_quality,
    )
    if config.full_auto:
        video_stream = video_streams[0]
        audio_stream = audio_streams[0]
        print_func(
            "Full auto: выбрано лучшее видео "
            f"не выше {config.default_video_quality}p: {describe_video_stream(video_stream)}."
        )
        print_func(
            f"Full auto: выбрана лучшая аудио-дорожка: "
            f"{describe_audio_stream(audio_stream, config.default_mp3_bitrate)}."
        )
    else:
        resolution = prompt_video_resolution(
            available_resolutions=available_resolutions,
            default_resolution=config.default_video_quality,
            input_func=input_func,
            print_func=print_func,
        )
        video_stream = get_best_video_stream_for_resolution(video_streams, resolution)
        audio_stream = prompt_audio_stream(
            audio_streams=audio_streams,
            max_mp3_bitrate=config.default_mp3_bitrate,
            input_func=input_func,
            print_func=print_func,
        )

    save_to = Path(config.download_dir)
    save_to.mkdir(parents=True, exist_ok=True)

    title = getattr(video, "title", None)
    output_path = save_to / f"{make_video_file_stem(title)}.mp4"
    temp_dir = save_to / ".tmp" / (make_allowed_format(getattr(video, "video_id", "") or "") or make_video_file_stem(title))
    temp_dir.mkdir(parents=True, exist_ok=True)

    video_filename = f"video.{getattr(video_stream, 'subtype', 'bin')}"
    audio_filename = f"audio.{getattr(audio_stream, 'subtype', 'bin')}"
    print_func(f"Скачиваю видео-поток: {describe_video_stream(video_stream)}")
    video_path = Path(video_stream.download(output_path=str(temp_dir), filename=video_filename))
    print_func(f"Видео-поток сохранён: {video_path}")

    print_func(f"Скачиваю аудио-дорожку: {describe_audio_stream(audio_stream, config.default_mp3_bitrate)}")
    audio_path = Path(
        DownloadYTAudio(video=video).download(
            stream=audio_stream,
            save_to=str(temp_dir),
            filename=audio_filename,
        )
    )
    print_func(f"Аудио-дорожка сохранена: {audio_path}")

    transcode_video = getattr(video_stream, "subtype", None) != "mp4"
    if transcode_video:
        print_func("Видео-поток не MP4: FFmpeg перекодирует видео в H.264.")
    else:
        print_func("Видео-поток MP4: FFmpeg скопирует видео без перекодирования.")

    source_audio_bitrate = parse_bitrate_kbps(getattr(audio_stream, "abr", None))
    try:
        merged_path = merge_video_and_audio_to_mp4(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            source_audio_bitrate_kbps=source_audio_bitrate,
            max_audio_bitrate_kbps=config.default_mp3_bitrate,
            ffmpeg_path=config.ffmpeg_path,
            transcode_video=transcode_video,
            duration_seconds=getattr(video, "length", None),
            progress_callback=print_func,
        )
    except VideoMergeError as exc:
        logger.warning(f"Не удалось склеить видео и аудио в MP4: {exc}")
        print_func(f"Видео и аудио скачаны, но MP4 не собран: {exc}")
        return 1

    for path in (video_path, audio_path):
        if path.exists():
            path.unlink()
    if temp_dir.exists() and not any(temp_dir.iterdir()):
        temp_dir.rmdir()

    print_func(f"Готово. MP4 сохранён в {merged_path}.")
    return 0


def download_audio(video: YouTube, config, input_func: InputFunc, print_func: PrintFunc) -> int:
    audio_streams = get_audio_streams(video)
    if not audio_streams:
        print_func("Не удалось получить список аудио-дорожек.")
        return 1

    if config.full_auto:
        stream = audio_streams[0]
        source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
        target_bitrate = choose_mp3_bitrate(source_bitrate, config.default_mp3_bitrate)
        subtype = getattr(stream, "subtype", "unknown")
        print_func(
            f"Full auto: выбрана лучшая аудио-дорожка "
            f"{stream.abr} {subtype} (itag {stream.itag}, mp3 {target_bitrate}kbps)."
        )
    else:
        stream = prompt_audio_stream(
            audio_streams=audio_streams,
            max_mp3_bitrate=config.default_mp3_bitrate,
            input_func=input_func,
            print_func=print_func,
        )
    save_to = Path(config.audio_download_dir)
    save_to.mkdir(parents=True, exist_ok=True)

    downloaded_path = Path(DownloadYTAudio(video=video).download(stream=stream, save_to=str(save_to)))
    mp3_path = downloaded_path.with_suffix(".mp3")
    source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
    target_bitrate = choose_mp3_bitrate(source_bitrate, config.default_mp3_bitrate)

    try:
        convert_to_mp3(
            input_path=downloaded_path,
            output_path=mp3_path,
            source_bitrate_kbps=source_bitrate,
            max_bitrate_kbps=config.default_mp3_bitrate,
            ffmpeg_path=config.ffmpeg_path,
        )
    except AudioConversionError as exc:
        logger.warning(f"Не удалось сконвертировать аудио в MP3: {exc}")
        print_func(f"Аудио скачано, но MP3-конвертация не выполнена: {exc}")
        return 1

    if downloaded_path != mp3_path and downloaded_path.exists():
        downloaded_path.unlink()

    print_func(f"Готово. MP3 сохранён в {mp3_path} ({target_bitrate}kbps).")
    return 0


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
        video = YouTube(url=video_url)
        print_func(f"Видео: {video.title}")
        if mode == AUDIO_MODE:
            return download_audio(
                video=video,
                config=config,
                input_func=input_func,
                print_func=print_func,
            )

        return download_video(
            video=video,
            config=config,
            input_func=input_func,
            print_func=print_func,
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
    if media_mode not in {VIDEO_MODE, AUDIO_MODE}:
        raise ValueError("media_mode must be video or audio")

    configure_file_logger()
    ensure_env_file()
    config = load_config()

    playlist_url = input_func("Вставьте ссылку на плейлист: ").strip()
    if not playlist_url:
        print_func("Ссылка не указана.")
        return 1

    playlist = Playlist(playlist_url)
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
                )
            else:
                result = download_video(
                    video=video,
                    config=playlist_config,
                    input_func=input_func,
                    print_func=print_func,
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


def download_video_interactive(
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    return download_media_interactive(
        mode=VIDEO_MODE,
        input_func=input_func,
        print_func=print_func,
    )
