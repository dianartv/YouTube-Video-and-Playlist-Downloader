import unittest

from engine.errors.errors_handler import EmptyPlaylist, ItagDoesNotExist
from engine.youtube_tools.youtube_tools import (
    DownloadYTPlaylist,
    DownloadYTAudio,
    DownloadYTVideo,
    YouTube,
    get_available_resolutions,
    get_audio_streams,
    get_best_audio_stream,
    get_resolution_itag,
    get_video_only_resolutions,
)


class FakeStream:
    def __init__(self):
        self.saved_to = None

    def download(self, save_to=None, output_path=None):
        save_to = output_path or save_to
        self.saved_to = save_to
        return f"{save_to}/audio.webm"


class FakeStreams:
    def __init__(self, stream):
        self.stream = stream
        self.requested_itag = None

    def get_by_itag(self, itag):
        self.requested_itag = itag
        return self.stream


class FakeVideo:
    def __init__(self, resolution_itag=None, best_itag=137):
        self.resolution_itag = resolution_itag
        self.best_itag = best_itag
        self.stream = FakeStream()
        self.streams = FakeStreams(self.stream)

    def get_resolution_itag(self, resolution, only_with_audio=True):
        if self.resolution_itag is None:
            raise ItagDoesNotExist(f"Missing itag for {resolution}")
        return self.resolution_itag

    def get_best_quality_itag(self, only_with_audio=True):
        return self.best_itag


class FakeFormatStream:
    def __init__(
        self,
        itag,
        resolution,
        stream_type="video",
        includes_audio_track=False,
        abr=None,
        subtype="mp4",
    ):
        self.itag = itag
        self.resolution = resolution
        self.type = stream_type
        self.includes_audio_track = includes_audio_track
        self.abr = abr
        self.subtype = subtype


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

    def get_resolution_itag(self, resolution, only_with_audio=True):
        return YouTube.get_resolution_itag(
            self,
            resolution=resolution,
            only_with_audio=only_with_audio,
        )

    def get_best_quality_itag(self, only_with_audio=True):
        return YouTube.get_best_quality_itag(
            self,
            only_with_audio=only_with_audio,
        )


class ResolutionItagTests(unittest.TestCase):
    def test_returns_requested_resolution_itag_when_available(self):
        video = FakeVideo(resolution_itag=22)

        self.assertEqual(get_resolution_itag(720, video), 22)

    def test_falls_back_to_best_quality_when_resolution_is_missing(self):
        video = FakeVideo(resolution_itag=None, best_itag=137)

        with self.assertLogs(level="WARNING") as logs:
            itag = get_resolution_itag(7201, video)

        self.assertEqual(itag, 137)
        self.assertIn("Разрешение 7201 со звуком недоступно.", logs.output[0])


class DownloadYTVideoTests(unittest.TestCase):
    def test_downloads_stream_matching_selected_itag(self):
        video = FakeVideo(resolution_itag=22)

        DownloadYTVideo(video).download(resolution=720, save_to="data/videos")

        self.assertEqual(video.streams.requested_itag, 22)
        self.assertEqual(video.stream.saved_to, "data/videos")


class DownloadYTAudioTests(unittest.TestCase):
    def test_downloads_selected_audio_stream(self):
        video = FakeVideo()
        stream = FakeStream()

        result = DownloadYTAudio(video).download(stream=stream, save_to="content/audio")

        self.assertEqual(result, "content/audio/audio.webm")
        self.assertEqual(stream.saved_to, "content/audio")


class DownloadYTPlaylistTests(unittest.TestCase):
    def test_empty_playlist_raises_domain_error(self):
        with self.assertRaises(EmptyPlaylist):
            DownloadYTPlaylist._create_yt_playlist([])


class AvailableResolutionTests(unittest.TestCase):
    def test_get_available_resolutions_returns_unique_video_resolutions_with_audio(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(18, "360p", includes_audio_track=True),
                FakeFormatStream(140, None, "audio"),
                FakeFormatStream(135, "480p", includes_audio_track=True),
                FakeFormatStream(136, "720p", includes_audio_track=False),
                FakeFormatStream(137, "1080p", includes_audio_track=False),
            ]
        )

        self.assertEqual(
            get_available_resolutions(fake_video),
            [480, 360],
        )

    def test_get_available_resolutions_can_include_video_only_resolutions(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(18, "360p", includes_audio_track=True),
                FakeFormatStream(136, "720p", includes_audio_track=False),
                FakeFormatStream(137, "1080p", includes_audio_track=False),
            ]
        )

        self.assertEqual(
            get_available_resolutions(fake_video, only_with_audio=False),
            [1080, 720, 360],
        )

    def test_get_video_only_resolutions_excludes_resolutions_with_audio(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(18, "360p", includes_audio_track=True),
                FakeFormatStream(134, "360p", includes_audio_track=False),
                FakeFormatStream(136, "720p", includes_audio_track=False),
                FakeFormatStream(137, "1080p", includes_audio_track=False),
            ]
        )

        self.assertEqual(get_video_only_resolutions(fake_video), [1080, 720])

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

    def test_resolution_itag_falls_back_to_best_quality_with_audio(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(18, "360p", includes_audio_track=True),
                FakeFormatStream(137, "1080p", includes_audio_track=False),
            ]
        )

        with self.assertLogs(level="WARNING") as logs:
            itag = get_resolution_itag(1080, fake_video)

        self.assertEqual(itag, 18)
        self.assertIn("Разрешение 1080 со звуком недоступно.", logs.output[0])


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

    def test_get_best_audio_stream_returns_highest_bitrate_audio(self):
        fake_video = FakeVideoWithStreams(
            [
                FakeFormatStream(139, None, "audio", True, "48kbps"),
                FakeFormatStream(251, None, "audio", True, "160kbps"),
            ]
        )

        self.assertEqual(get_best_audio_stream(fake_video).itag, 251)


if __name__ == "__main__":
    unittest.main()
