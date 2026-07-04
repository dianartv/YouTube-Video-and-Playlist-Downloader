from collections.abc import Callable
from pathlib import Path

from engine.application.download_duplicates import (
    ConfirmOverwriteFunc,
    save_download_record,
    should_download_record,
)
from engine.application.formatters import describe_aac_audio_stream, describe_video_stream
from engine.application.progress import ProgressFunc, ffmpeg_progress_adapter
from engine.domain.download_history import DownloadHistory, DownloadRecord
from engine.domain.modes import VIDEO_MODE
from engine.domain.naming import make_safe_path_name, make_video_file_stem
from engine.service.audio import choose_mp3_bitrate, parse_bitrate_kbps
from engine.service.cancellation import CancellationToken, OperationCancelled
from engine.service.logger import logger
from engine.service.video import VideoMergeError, merge_video_and_audio_to_mp4
from engine.youtube_tools.youtube_tools import (
    DownloadYTAudio,
    YouTube,
    download_stream,
    get_audio_streams,
    get_best_video_stream_for_resolution,
    get_video_resolutions_no_higher_than,
    get_video_streams_no_higher_than,
)


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
PromptVideoResolutionFunc = Callable[[list[int], int, list[int] | None, InputFunc, PrintFunc], int]
PromptAudioStreamFunc = Callable[[list, int, InputFunc, PrintFunc], object]


def download_video(
    video: YouTube,
    config,
    input_func: InputFunc,
    print_func: PrintFunc,
    prompt_video_resolution_func: PromptVideoResolutionFunc,
    prompt_audio_stream_func: PromptAudioStreamFunc,
    cancel_token: CancellationToken | None = None,
    download_history: DownloadHistory | None = None,
    confirm_overwrite_func: ConfirmOverwriteFunc | None = None,
    progress_callback: ProgressFunc | None = None,
) -> int:
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    video_streams = get_video_streams_no_higher_than(
        video,
        max_resolution=config.default_video_quality,
    )
    if not video_streams:
        print_func(
            f"Не удалось получить видеопотоки не выше {config.default_video_quality}p."
        )
        return 1
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    audio_streams = get_audio_streams(video)
    if not audio_streams:
        print_func("Не удалось получить список аудио-дорожек.")
        return 1
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

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
            "Full auto: выбрана лучшая аудио-дорожка: "
            f"{describe_aac_audio_stream(audio_stream, config.default_mp3_bitrate)}."
        )
    else:
        resolution = prompt_video_resolution_func(
            available_resolutions,
            config.default_video_quality,
            None,
            input_func,
            print_func,
        )
        video_stream = get_best_video_stream_for_resolution(video_streams, resolution)
        audio_stream = prompt_audio_stream_func(
            audio_streams,
            config.default_mp3_bitrate,
            input_func,
            print_func,
        )

    save_to = Path(config.download_dir)
    save_to.mkdir(parents=True, exist_ok=True)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    title = getattr(video, "title", None)
    output_path = save_to / f"{make_video_file_stem(title)}.mp4"
    source_audio_bitrate = parse_bitrate_kbps(getattr(audio_stream, "abr", None))
    target_audio_bitrate = choose_mp3_bitrate(
        source_audio_bitrate,
        config.default_mp3_bitrate,
    )
    planned_record = _build_video_download_record(
        video=video,
        video_stream=video_stream,
        audio_stream=audio_stream,
        output_path=output_path,
        source_audio_bitrate=source_audio_bitrate,
        target_audio_bitrate=target_audio_bitrate,
    )
    if not should_download_record(
        history=download_history,
        planned_record=planned_record,
        confirm_overwrite_func=confirm_overwrite_func,
        print_func=print_func,
    ):
        return 0

    temp_name = make_safe_path_name(getattr(video, "video_id", "") or "") or make_video_file_stem(title)
    temp_dir = save_to / ".tmp" / temp_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    if cancel_token is not None:
        cancel_token.register_path(temp_dir)

    video_filename = f"video.{getattr(video_stream, 'subtype', 'bin')}"
    audio_filename = f"audio.{getattr(audio_stream, 'subtype', 'bin')}"
    print_func(f"Скачиваю видео-поток: {describe_video_stream(video_stream)}")
    expected_video_path = temp_dir / video_filename
    if cancel_token is not None:
        cancel_token.register_path(expected_video_path)

    downloaded_video = download_stream(
        video=video,
        stream=video_stream,
        save_to=str(temp_dir),
        filename=video_filename,
        interrupt_checker=cancel_token.is_cancelled if cancel_token is not None else None,
        progress_callback=progress_callback,
    )
    if downloaded_video is None:
        raise OperationCancelled("Скачивание видео отменено.")

    video_path = Path(downloaded_video)
    if cancel_token is not None:
        cancel_token.register_path(video_path)

    print_func(f"Видео-поток сохранён: {video_path}")

    print_func(
        "Скачиваю аудио-дорожку: "
        f"{describe_aac_audio_stream(audio_stream, config.default_mp3_bitrate)}"
    )
    expected_audio_path = temp_dir / audio_filename
    if cancel_token is not None:
        cancel_token.register_path(expected_audio_path)

    downloaded_audio = DownloadYTAudio(video=video).download(
        stream=audio_stream,
        save_to=str(temp_dir),
        filename=audio_filename,
        interrupt_checker=cancel_token.is_cancelled if cancel_token is not None else None,
        progress_callback=progress_callback,
    )
    if downloaded_audio is None:
        raise OperationCancelled("Скачивание аудио отменено.")

    audio_path = Path(downloaded_audio)
    if cancel_token is not None:
        cancel_token.register_path(audio_path)

    print_func(f"Аудио-дорожка сохранена: {audio_path}")

    transcode_video = getattr(video_stream, "subtype", None) != "mp4"
    if transcode_video:
        print_func("Видео-поток не MP4: FFmpeg перекодирует видео в H.264.")
    else:
        print_func("Видео-поток MP4: FFmpeg скопирует видео без перекодирования.")

    if cancel_token is not None:
        cancel_token.register_path(output_path)

    try:
        print_func("Собираю MP4.")
        merged_path = merge_video_and_audio_to_mp4(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            source_audio_bitrate_kbps=source_audio_bitrate,
            max_audio_bitrate_kbps=config.default_mp3_bitrate,
            ffmpeg_path=config.ffmpeg_path,
            transcode_video=transcode_video,
            duration_seconds=getattr(video, "length", None),
            progress_callback=ffmpeg_progress_adapter(progress_callback),
            cancel_token=cancel_token,
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

    save_download_record(
        history=download_history,
        record=planned_record,
        output_path=merged_path,
    )
    print_func(f"Готово. MP4 сохранён в {merged_path}.")
    return 0


def _build_video_download_record(
    *,
    video: YouTube,
    video_stream,
    audio_stream,
    output_path: Path,
    source_audio_bitrate: int | None,
    target_audio_bitrate: int,
) -> DownloadRecord:
    return DownloadRecord(
        video_id=str(getattr(video, "video_id", "") or ""),
        media_type=VIDEO_MODE,
        title=str(getattr(video, "title", "") or "video"),
        output_path=output_path,
        source_url=str(getattr(video, "watch_url", "") or ""),
        video_resolution=_resolution_value(getattr(video_stream, "resolution", None)),
        video_itag=_optional_int(getattr(video_stream, "itag", None)),
        audio_bitrate=source_audio_bitrate,
        audio_itag=_optional_int(getattr(audio_stream, "itag", None)),
        output_bitrate=target_audio_bitrate,
        container="mp4",
    )


def _resolution_value(value) -> int | None:
    if value is None:
        return None

    try:
        return int(str(value).removesuffix("p"))
    except ValueError:
        return None


def _optional_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
