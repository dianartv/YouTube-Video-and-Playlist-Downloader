from engine.errors.errors_handler import EmptyPlaylist
from engine.youtube_tools.youtube_tools import DownloadYTPlaylist
from engine.service.logger import logger

if __name__ == '__main__':

    youtube_playlist_url = 'https://www.youtube.com/playlist?list=PL0TLlA6h3_uA5miXyPDWVJoba0O2Qpc0O'
    resolution = 720

    try:
        playlist = DownloadYTPlaylist(playlist_url=youtube_playlist_url)

        playlist.download(
            resolution=resolution,
        )
    except EmptyPlaylist:
        logger.warning(f'Playlist is empty.')
