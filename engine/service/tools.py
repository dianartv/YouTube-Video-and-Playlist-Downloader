import os


def make_allowed_format(string: str) -> str:
    """Убирает символы, запрещённые в названии файла в Win64."""

    return ''.join([i for i in string if i not in r'\/?:*"><|'])


def get_file_rows(file_path: str):
    """Вовзращает коллекцию ссылок на PyYT видео."""

    with open(file_path, 'r', encoding='utf-8') as file:
        return [line.rstrip() for line in file]


def remove_temporary_files(
        folder: str, saved_format: str = '.mp3'
) -> None:
    """Удаляет файлы за исключением разрешённого расширения."""

    def _get_dir_files(path: str) -> list:
        """Все файлы в директории."""
        x = [i for i in os.walk(path)]
        for root, dirs, files in os.walk(path):
            return files

    def _remove_files_with_options(path: str, saved_format: str) -> None:
        files = _get_dir_files(path)
        for file in files:
            if saved_format not in file:
                os.remove(f'{path}\\{file}')

    _remove_files_with_options(path=folder, saved_format=saved_format)
