from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pytubefix.exceptions import LiveStreamEnded, LiveStreamError, VideoUnavailable

from engine.application.download_audio import download_audio
from engine.application.download_duplicates import ConfirmOverwriteFunc
from engine.domain.download_history import DownloadHistory
from engine.service.cancellation import CancellationToken, OperationCancelled
from engine.youtube_tools.youtube_tools import YouTube


InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
PromptAudioStreamFunc = Callable[[list, int, InputFunc, PrintFunc], object]


@dataclass(frozen=True)
class BulkFailure:
    index: int
    url: str
    reason: str


def download_audio_bulk(
    *,
    urls: list[str],
    config,
    input_func: InputFunc,
    print_func: PrintFunc,
    prompt_audio_stream_func: PromptAudioStreamFunc,
    download_history: DownloadHistory | None = None,
    confirm_overwrite_func: ConfirmOverwriteFunc | None = None,
    cancel_token: CancellationToken | None = None,
) -> int:
    prepared_urls = [url.strip() for url in urls if url.strip()]
    if not prepared_urls:
        print_func("Список ссылок пуст.")
        return 1

    worker_limit = max(1, int(getattr(config, "worker_limit", 1)))
    print_func(f"Список ссылок: {len(prepared_urls)}. Параллельных задач: {worker_limit}.")

    success_count = 0
    failures: list[BulkFailure] = []
    with ThreadPoolExecutor(max_workers=worker_limit) as executor:
        futures = {
            executor.submit(
                _download_one,
                index=index,
                total=len(prepared_urls),
                url=url,
                config=config,
                input_func=input_func,
                print_func=print_func,
                prompt_audio_stream_func=prompt_audio_stream_func,
                download_history=download_history,
                confirm_overwrite_func=confirm_overwrite_func,
                cancel_token=cancel_token,
            ): (index, url)
            for index, url in enumerate(prepared_urls, start=1)
        }

        for future in as_completed(futures):
            index, url = futures[future]
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()

            try:
                result = future.result()
            except OperationCancelled:
                for pending_future in futures:
                    pending_future.cancel()
                raise
            except Exception as exc:
                failures.append(BulkFailure(index=index, url=url, reason=_error_message(exc)))
                continue

            if result == 0:
                success_count += 1
            else:
                failures.append(
                    BulkFailure(
                        index=index,
                        url=url,
                        reason="загрузка вернула ошибку",
                    )
                )

    _print_bulk_summary(
        success_count=success_count,
        failures=failures,
        print_func=print_func,
    )
    return 0 if not failures else 1


def _download_one(
    *,
    index: int,
    total: int,
    url: str,
    config,
    input_func: InputFunc,
    print_func: PrintFunc,
    prompt_audio_stream_func: PromptAudioStreamFunc,
    download_history: DownloadHistory | None,
    confirm_overwrite_func: ConfirmOverwriteFunc | None,
    cancel_token: CancellationToken | None,
) -> int:
    item_print = _prefixed_print(index, total, print_func)
    item_print(f"Ссылка: {url}")
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()

    video = YouTube(url=url)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    item_print(f"Видео: {video.title}")

    return download_audio(
        video=video,
        config=config,
        input_func=input_func,
        print_func=item_print,
        prompt_audio_stream_func=prompt_audio_stream_func,
        cancel_token=cancel_token,
        download_history=download_history,
        confirm_overwrite_func=confirm_overwrite_func,
    )


def _prefixed_print(index: int, total: int, print_func: PrintFunc) -> PrintFunc:
    prefix = f"[{index}/{total}] "

    def wrapped(message: str) -> None:
        print_func(f"{prefix}{message}")

    return wrapped


def _print_bulk_summary(
    *,
    success_count: int,
    failures: list[BulkFailure],
    print_func: PrintFunc,
) -> None:
    failures = sorted(failures, key=lambda failure: failure.index)
    print_func("Итог списка ссылок:")
    print_func(f"Успешно: {success_count}. Пропущено/ошибок: {len(failures)}.")
    if not failures:
        return

    print_func("Пропущенные ссылки:")
    for failure in failures:
        print_func(f"{failure.index}. {failure.url} — {failure.reason}")


def _error_message(exc: Exception) -> str:
    if isinstance(exc, LiveStreamError):
        return "активная live-трансляция"
    if isinstance(exc, LiveStreamEnded):
        return "архив трансляции ещё недоступен"
    if isinstance(exc, VideoUnavailable):
        return "видео недоступно"

    return str(exc) or exc.__class__.__name__
