import argparse
from collections.abc import Sequence

from engine.youtube_tools.video_cli import AUDIO_MODE, VIDEO_MODE, download_media_interactive


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download YouTube video-with-audio or audio-only MP3.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--video",
        action="store_const",
        const=VIDEO_MODE,
        dest="mode",
        help="download the best video stream that already includes audio",
    )
    mode.add_argument(
        "--audio",
        "--audio-only",
        action="store_const",
        const=AUDIO_MODE,
        dest="mode",
        help="download the best audio stream and convert it to MP3",
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return download_media_interactive(mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
