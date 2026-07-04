from collections.abc import Callable
from pathlib import Path

from engine.application.download_duplicates import (
    ConfirmOverwriteFunc,
    save_download_record,
    should_download_record,
)
from engine.application.formatters import describe_mp3_audio_stream
from engine.domain.download_history import DownloadHistory, DownloadRecord
from engine.domain.modes import AUDIO_MODE
from engine.domain.naming import make_video_file_stem
from engine.service.audio import (
    AudioConversionError,
    choose_mp3_bitrate,
    convert_to_mp3,
    parse_bitrate_kbps,
)
from engine.service.cancellation import CancellationToken, OperationCancelled
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
    cancel_token: CancellationToken | None = None,
    download_history: DownloadHistory | None = None,
    confirm_overwrite_func: ConfirmOverwriteFunc | None = None,
) -> int:
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    audio_streams = get_audio_streams(video)
    if not audio_streams:
        print_func("Не удалось получить список аудио-дорожек.")
        return 1
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

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
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    expected_source_path = _expected_stream_path(stream, save_to)
    planned_mp3_path = (
        expected_source_path or _fallback_source_path(video, stream, save_to)
    ).with_suffix(".mp3")
    source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
    target_bitrate = choose_mp3_bitrate(source_bitrate, config.default_mp3_bitrate)
    planned_record = _build_audio_download_record(
        video=video,
        stream=stream,
        output_path=planned_mp3_path,
        source_bitrate=source_bitrate,
        target_bitrate=target_bitrate,
    )
    if not should_download_record(
        history=download_history,
        planned_record=planned_record,
        confirm_overwrite_func=confirm_overwrite_func,
        print_func=print_func,
    ):
        return 0

    print_func(f"Скачиваю аудио-дорожку: {describe_mp3_audio_stream(stream, config.default_mp3_bitrate)}")
    if cancel_token is not None:
        cancel_token.register_path(expected_source_path)

    downloaded = DownloadYTAudio(video=video).download(
        stream=stream,
        save_to=str(save_to),
        interrupt_checker=cancel_token.is_cancelled if cancel_token is not None else None,
    )
    if downloaded is None:
        raise OperationCancelled("Скачивание аудио отменено.")

    downloaded_path = Path(downloaded)
    if cancel_token is not None:
        cancel_token.register_path(downloaded_path)

    print_func(f"Аудио-дорожка сохранена: {downloaded_path}")
    mp3_path = downloaded_path.with_suffix(".mp3")
    if cancel_token is not None:
        cancel_token.register_path(mp3_path)

    try:
        print_func("Конвертирую аудио в MP3.")
        convert_to_mp3(
            input_path=downloaded_path,
            output_path=mp3_path,
            source_bitrate_kbps=source_bitrate,
            max_bitrate_kbps=config.default_mp3_bitrate,
            ffmpeg_path=config.ffmpeg_path,
            cancel_token=cancel_token,
        )
    except AudioConversionError as exc:
        logger.warning(f"Не удалось сконвертировать аудио в MP3: {exc}")
        print_func(f"Аудио скачано, но MP3-конвертация не выполнена: {exc}")
        return 1

    if downloaded_path != mp3_path and downloaded_path.exists():
        downloaded_path.unlink()

    save_download_record(
        history=download_history,
        record=planned_record,
        output_path=mp3_path,
    )
    print_func(f"Готово. MP3 сохранён в {mp3_path} ({target_bitrate}kbps).")
    return 0


def _expected_stream_path(stream, save_to: Path) -> Path | None:
    get_file_path = getattr(stream, "get_file_path", None)
    if get_file_path is None:
        return None

    return Path(get_file_path(output_path=str(save_to)))


def _fallback_source_path(video: YouTube, stream, save_to: Path) -> Path:
    subtype = getattr(stream, "subtype", None) or "bin"
    return save_to / f"{make_video_file_stem(getattr(video, 'title', None))}.{subtype}"


def _build_audio_download_record(
    *,
    video: YouTube,
    stream,
    output_path: Path,
    source_bitrate: int | None,
    target_bitrate: int,
) -> DownloadRecord:
    return DownloadRecord(
        video_id=str(getattr(video, "video_id", "") or ""),
        media_type=AUDIO_MODE,
        title=str(getattr(video, "title", "") or "video"),
        output_path=output_path,
        source_url=str(getattr(video, "watch_url", "") or ""),
        audio_bitrate=source_bitrate,
        audio_itag=_optional_int(getattr(stream, "itag", None)),
        output_bitrate=target_bitrate,
        container="mp3",
    )


def _optional_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
