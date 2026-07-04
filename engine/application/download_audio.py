from collections.abc import Callable
from pathlib import Path

from engine.application.formatters import describe_mp3_audio_stream
from engine.service.audio import (
    AudioConversionError,
    choose_mp3_bitrate,
    convert_to_mp3,
    parse_bitrate_kbps,
)
from engine.service.logger import logger
from engine.youtube_tools.youtube_tools import DownloadYTAudio, YouTube, get_audio_streams


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
PromptAudioStreamFunc = Callable[[list, int, InputFunc, PrintFunc], object]


def download_audio(
    video: YouTube,
    config,
    input_func: InputFunc,
    print_func: PrintFunc,
    prompt_audio_stream_func: PromptAudioStreamFunc,
) -> int:
    audio_streams = get_audio_streams(video)
    if not audio_streams:
        print_func("Не удалось получить список аудио-дорожек.")
        return 1

    if config.full_auto:
        stream = audio_streams[0]
        print_func(
            "Full auto: выбрана лучшая аудио-дорожка "
            f"{describe_mp3_audio_stream(stream, config.default_mp3_bitrate)}."
        )
    else:
        stream = prompt_audio_stream_func(
            audio_streams,
            config.default_mp3_bitrate,
            input_func,
            print_func,
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
