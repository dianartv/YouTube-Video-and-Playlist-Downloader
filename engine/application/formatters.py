from engine.service.audio import choose_mp3_bitrate, parse_bitrate_kbps


def describe_video_stream(stream) -> str:
    resolution = getattr(stream, "resolution", "unknown")
    subtype = getattr(stream, "subtype", "unknown")
    itag = getattr(stream, "itag", "unknown")
    fps = getattr(stream, "fps", None)
    fps_text = f", {fps}fps" if fps else ""
    return f"{resolution} {subtype}{fps_text} (itag {itag})"


def describe_mp3_audio_stream(stream, max_bitrate_kbps: int) -> str:
    target_bitrate = _target_audio_bitrate(stream, max_bitrate_kbps)
    subtype = getattr(stream, "subtype", "unknown")
    itag = getattr(stream, "itag", "unknown")
    return f"{stream.abr} {subtype} (itag {itag}, mp3 {target_bitrate}kbps)"


def describe_aac_audio_stream(stream, max_bitrate_kbps: int) -> str:
    target_bitrate = _target_audio_bitrate(stream, max_bitrate_kbps)
    subtype = getattr(stream, "subtype", "unknown")
    itag = getattr(stream, "itag", "unknown")
    return f"{stream.abr} {subtype} (itag {itag}, AAC {target_bitrate}kbps)"


def _target_audio_bitrate(stream, max_bitrate_kbps: int) -> int:
    source_bitrate = parse_bitrate_kbps(getattr(stream, "abr", None))
    return choose_mp3_bitrate(source_bitrate, max_bitrate_kbps)
