def make_allowed_format(string: str) -> str:
    """Убирает символы, запрещённые в названии файла в Win64."""

    return ''.join([i for i in string if i not in r'\/?:*"><|'])


def get_file_rows(file_path: str):
    """Вовзращает коллекцию ссылок на PyYT видео."""

    with open(file_path, 'r', encoding='utf-8') as file:
        return [line.rstrip() for line in file]
