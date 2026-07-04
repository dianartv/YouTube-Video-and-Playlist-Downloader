from collections.abc import Callable
from pathlib import Path

from engine.application.formatters import describe_aac_audio_stream, describe_video_stream
from engine.domain.naming import make_safe_path_name, make_video_file_stem
from engine.service.audio import parse_bitrate_kbps
from engine.service.logger import logger
from engine.service.video import VideoMergeError, merge_video_and_audio_to_mp4
from engine.youtube_tools.youtube_tools import (
    DownloadYTAudio,
    YouTube,
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
) -> int:
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

    title = getattr(video, "title", None)
    output_path = save_to / f"{make_video_file_stem(title)}.mp4"
    temp_name = make_safe_path_name(getattr(video, "video_id", "") or "") or make_video_file_stem(title)
    temp_dir = save_to / ".tmp" / temp_name
    temp_dir.mkdir(parents=True, exist_ok=True)

    video_filename = f"video.{getattr(video_stream, 'subtype', 'bin')}"
    audio_filename = f"audio.{getattr(audio_stream, 'subtype', 'bin')}"
    print_func(f"Скачиваю видео-поток: {describe_video_stream(video_stream)}")
    video_path = Path(video_stream.download(output_path=str(temp_dir), filename=video_filename))
    print_func(f"Видео-поток сохранён: {video_path}")

    print_func(
        "Скачиваю аудио-дорожку: "
        f"{describe_aac_audio_stream(audio_stream, config.default_mp3_bitrate)}"
    )
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
