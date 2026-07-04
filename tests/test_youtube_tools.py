import unittest
from types import SimpleNamespace

from engine.errors.errors_handler import ItagDoesNotExist
from engine.youtube_tools.youtube_tools import (
    DownloadYTAudio,
    YouTube,
    download_stream,
    get_audio_streams,
    get_best_video_stream_for_resolution,
    get_best_video_stream_no_higher_than,
    get_video_resolutions_no_higher_than,
    get_video_streams_no_higher_than,
)


class FakeStream:
    def __init__(self):
        self.saved_to = None

    def download(self, save_to=None, output_path=None, filename=None, interrupt_checker=None):
        if interrupt_checker is not None and interrupt_checker():
            return None

        save_to = output_path or save_to
        self.saved_to = f"{save_to}/{filename}" if filename else save_to
        return f"{save_to}/{filename or 'audio.webm'}"


class FakeProgressStream:
    filesize = 100

    def __init__(self, video):
        self.video = video

    def download(self, output_path=None, filename=None, interrupt_checker=None):
        self.video.stream_monostate.on_progress(self, b"chunk", 75)
        self.video.stream_monostate.on_progress(self, b"chunk", 25)
        return f"{output_path}/{filename}"


class FakeFormatStream:
    def __init__(
        self,
        itag,
        resolution,
        stream_type="video",
        includes_audio_track=False,
        abr=None,
        subtype="mp4",
        fps=30,
    ):
        self.itag = itag
        self.resolution = resolution
        self.type = stream_type
        self.includes_audio_track = includes_audio_track
        self.abr = abr
        self.subtype = subtype
        self.fps = fps


class FakeVideoWithStreams:
    def __init__(self, streams):
        self.fmt_streams = streams

    def get_video_stream_format_codes(
        self,
        only_video=True,
        only_with_audio=False,
        sorted_by_itag=True,
        sorted_by_resolution=True,
    ):
        return YouTube.get_video_stream_format_codes(
            self,
            only_video=only_video,
            only_with_audio=only_with_audio,
            sorted_by_itag=sorted_by_itag,
            sorted_by_resolution=sorted_by_resolution,
        )


class DownloadYTAudioTests(unittest.TestCase):
    def test_downloads_selected_audio_stream(self):
        video = object()
        stream = FakeStream()

        result = DownloadYTAudio(video).download(stream=stream, save_to="content/audio")

        self.assertEqual(result, "content/audio/audio.webm")
        self.assertEqual(stream.saved_to, "content/audio")

    def test_downloads_selected_audio_stream_can_be_interrupted(self):
        video = object()
        stream = FakeStream()

        result = DownloadYTAudio(video).download(
            stream=stream,
            save_to="content/audio",
            interrupt_checker=lambda: True,
        )

        self.assertIsNone(result)
        self.assertIsNone(stream.saved_to)

    def test_downloads_selected_audio_stream_with_filename(self):
        video = object()
        stream = FakeStream()

        result = DownloadYTAudio(video).download(
            stream=stream,
            save_to="content/audio",
            filename="audio.webm",
        )

        self.assertEqual(result, "content/audio/audio.webm")
        self.assertEqual(stream.saved_to, "content/audio/audio.webm")

    def test_download_stream_reports_percent_progress_and_restores_callback(self):
        old_callback = object()
        video = SimpleNamespace(stream_monostate=SimpleNamespace(on_progress=old_callback))

        def register_on_progress_callback(callback):
            video.stream_monostate.on_progress = callback

        video.register_on_progress_callback = register_on_progress_callback
        progress = []

        result = download_stream(
            video=video,
            stream=FakeProgressStream(video),
            save_to="content/audio",
            filename="audio.webm",
            progress_callback=progress.append,
        )

        self.assertEqual(result, "content/audio/audio.webm")
        self.assertEqual(progress, [0, 25, 75, 100])
        self.assertIs(video.stream_monostate.on_progress, old_callback)


class AudioStreamTests(unittest.TestCase):
    def test_get_audio_streams_returns_audio_sorted_by_bitrate(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(18, "360p", includes_audio_track=True),
                FakeFormatStream(139, None, "audio", True, "48kbps"),
                FakeFormatStream(251, None, "audio", True, "160kbps", "webm"),
                FakeFormatStream(140, None, "audio", True, "128kbps"),
            ]
        )

        streams = get_audio_streams(fake_video)

        self.assertEqual([stream.itag for stream in streams], [251, 140, 139])


class VideoStreamSelectionTests(unittest.TestCase):
    def test_video_stream_sorting_ignores_streams_without_resolution(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(140, None),
                FakeFormatStream(18, "360p"),
                FakeFormatStream(22, "720p"),
            ]
        )

        streams = YouTube.get_video_stream_format_codes(fake_video)

        self.assertEqual([stream.resolution for stream in streams], ["720p", "360p", None])

    def test_get_video_streams_no_higher_than_filters_by_env_limit(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(137, "1080p", subtype="mp4"),
                FakeFormatStream(136, "720p", subtype="mp4"),
                FakeFormatStream(244, "480p", subtype="webm"),
                FakeFormatStream(140, None, "audio", True, "128kbps"),
            ]
        )

        streams = get_video_streams_no_higher_than(fake_video, max_resolution=720)

        self.assertEqual([stream.itag for stream in streams], [136, 244])

    def test_get_video_streams_no_higher_than_prefers_mp4_at_same_resolution(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(248, "1080p", subtype="webm"),
                FakeFormatStream(137, "1080p", subtype="mp4"),
                FakeFormatStream(136, "720p", subtype="mp4"),
            ]
        )

        best_stream = get_best_video_stream_no_higher_than(
            fake_video,
            max_resolution=1080,
        )

        self.assertEqual(best_stream.itag, 137)

    def test_get_best_video_stream_no_higher_than_raises_when_missing(self):
        fake_video = FakeVideoWithStreams([FakeFormatStream(137, "1080p", subtype="mp4")])

        with self.assertRaises(ItagDoesNotExist):
            get_best_video_stream_no_higher_than(fake_video, max_resolution=720)

    def test_get_video_resolutions_no_higher_than_returns_unique_values(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(137, "1080p", subtype="mp4"),
                FakeFormatStream(248, "1080p", subtype="webm"),
                FakeFormatStream(136, "720p", subtype="mp4"),
            ]
        )

        resolutions = get_video_resolutions_no_higher_than(
            fake_video,
            max_resolution=1080,
        )

        self.assertEqual(resolutions, [1080, 720])

    def test_get_best_video_stream_for_resolution_returns_sorted_match(self):
        streams = [
            FakeFormatStream(248, "1080p", subtype="webm"),
            FakeFormatStream(137, "1080p", subtype="mp4"),
        ]
        fake_video = FakeVideoWithStreams(streams)
        sorted_streams = get_video_streams_no_higher_than(fake_video, 1080)

        stream = get_best_video_stream_for_resolution(sorted_streams, 1080)

        self.assertEqual(stream.itag, 137)


if __name__ == "__main__":
    unittest.main()
