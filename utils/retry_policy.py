from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from loguru import logger

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    attempts: int = 3,
    base_delay_sec: float = 1.0,
    max_delay_sec: float = 20.0,
    jitter_sec: float = 0.25,
    is_retryable: Callable[[BaseException], bool] | None = None,
) -> T:
    """
    Unified retry helper with exponential backoff and jitter.
    """
    tries = max(1, int(attempts))
    last_error: BaseException | None = None
    for attempt in range(1, tries + 1):
        try:
            return await operation()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= tries:
                raise
            if is_retryable is not None and not is_retryable(exc):
                raise
            delay = min(max_delay_sec, base_delay_sec * (2 ** (attempt - 1)))
            if jitter_sec > 0:
                delay += random.uniform(0.0, jitter_sec)
            logger.warning(
                "[Retry] {} failed at attempt {}/{}: {}. Retry in {:.2f}s",
                operation_name,
                attempt,
                tries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{operation_name}: retry_async entered impossible state")
