from pathlib import Path
from typing import Callable

from pytubefix.exceptions import VideoUnavailable

from engine.service.config import ensure_env_file, load_config
from engine.service.audio import (
    AudioConversionError,
    convert_to_mp3,
    parse_bitrate_kbps,
    choose_mp3_bitrate,
)
from engine.service.logger import configure_file_logger, logger
from engine.youtube_tools.youtube_tools import (
    DownloadYTAudio,
    DownloadYTVideo,
    YouTube,
    get_available_resolutions,
    get_audio_streams,
    get_video_only_resolutions,
)


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
VIDEO_MODE = "video"
AUDIO_MODE = "audio"


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
    print_func("Доступное качество со звуком:")
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


def download_video(video: YouTube, config, input_func: InputFunc, print_func: PrintFunc) -> int:
    available_resolutions = get_available_resolutions(video, only_with_audio=True)
    if not available_resolutions:
        print_func("Не удалось получить список качеств со звуком.")
        return 1

    video_only_resolutions = get_video_only_resolutions(video)
    if config.full_auto:
        resolution = available_resolutions[0]
        print_func(f"Full auto: выбрано лучшее качество со звуком {resolution}p.")
        if video_only_resolutions:
            values = ", ".join(f"{value}p" for value in video_only_resolutions)
            print_func(f"Без аудио, пропущено: {values}")
    else:
        resolution = prompt_video_resolution(
            available_resolutions=available_resolutions,
            default_resolution=config.default_video_quality,
            video_only_resolutions=video_only_resolutions,
            input_func=input_func,
            print_func=print_func,
        )

    save_to = Path(config.download_dir)
    save_to.mkdir(parents=True, exist_ok=True)
    DownloadYTVideo(video=video).download(resolution=resolution, save_to=str(save_to))
    print_func(f"Готово. Видео сохранено в {config.download_dir}.")
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
    except VideoUnavailable:
        logger.warning(f"Видео {video_url} - недоступно.")
        print_func("Видео недоступно.")
        return 1


def download_video_interactive(
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    return download_media_interactive(
        mode=VIDEO_MODE,
        input_func=input_func,
        print_func=print_func,
    )
