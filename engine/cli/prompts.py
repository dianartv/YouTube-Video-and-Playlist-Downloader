from collections.abc import Callable

from engine.application.formatters import describe_mp3_audio_stream
from engine.domain.download_history import DownloadRecord
from engine.domain.selection import choose_audio_stream, choose_video_resolution


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]


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


def prompt_audio_stream(
    audio_streams: list,
    max_mp3_bitrate: int,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
):
    print_func("Доступные аудио-дорожки:")
    for index, stream in enumerate(audio_streams, start=1):
        print_func(f"{index}. {describe_mp3_audio_stream(stream, max_mp3_bitrate)}")

    while True:
        try:
            return choose_audio_stream(
                audio_streams=audio_streams,
                user_choice=input_func("Выберите аудио или нажмите Enter для лучшего: "),
            )
        except ValueError as exc:
            print_func(str(exc))


def prompt_overwrite_download(
    existing_record: DownloadRecord,
    planned_record: DownloadRecord,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> bool:
    answer = input_func("Файл уже существует. Перезаписать? [y/N]: ").strip().lower()
    return answer in {"y", "yes", "д", "да"}
