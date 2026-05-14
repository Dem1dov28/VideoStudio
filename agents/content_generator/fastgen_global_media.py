"""
Глобальный лимит одновременных задач генерации изображений/видео FastGen (HTTP + Playwright).

Один процесс = один счётчик: картинки и видео делят общий пул слотов (FASTGEN_GLOBAL_MEDIA_CONCURRENCY).
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import Iterator

_lock = threading.Lock()
_sem: threading.Semaphore | None = None


def _ensure_sem() -> threading.Semaphore:
    global _sem
    with _lock:
        if _sem is None:
            from config import settings

            n = max(1, min(64, int(getattr(settings, "fastgen_global_media_concurrency", 10) or 10)))
            _sem = threading.Semaphore(n)
        return _sem


@contextmanager
def fastgen_global_media_slot_sync() -> Iterator[None]:
    """Синхронный слот (потоки Playwright / to_thread)."""
    sem = _ensure_sem()
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


@asynccontextmanager
async def async_fastgen_global_media_slot():
    """Async-слот: acquire в thread pool, release из любого контекста."""
    sem = _ensure_sem()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sem.acquire)
    try:
        yield
    finally:
        sem.release()
