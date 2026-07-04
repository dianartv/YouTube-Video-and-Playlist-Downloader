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
