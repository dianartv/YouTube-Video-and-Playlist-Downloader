from engine.errors.errors_handler import EmptyPlaylist
from engine.youtube_tools.youtube_tools import DownloadYTPlaylist
from engine.service.logger import logger

if __name__ == '__main__':

    youtube_playlist_url = ''
    save_to = r'data\playlists'

    try:
        playlist = DownloadYTPlaylist(playlist_url=youtube_playlist_url)

        playlist.download(
            resolution=7201,
            save_to=f'{save_to}\\{playlist.playlist_title}'
        )
    except EmptyPlaylist:
        logger.warning(f'Playlist is empty.')


