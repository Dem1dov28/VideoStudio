"""
Pipeline control: pause, resume, cancel.
Used by server and orchestrator to allow user to control running pipelines.
"""

from __future__ import annotations

import asyncio
import threading


def fastgen_cancel_event(control: dict | None) -> threading.Event | None:
    """Событие отмены для потоков FastGen (Playwright); при set — закрыть окна Chromium."""
    if not control:
        return None
    ev = control.get("fastgen_cancel_event")
    return ev if isinstance(ev, threading.Event) else None


async def checkpoint(control: dict | None) -> None:
    """
    Called at pipeline step boundaries.
    - If cancelled: raise CancelledError
    - If paused: block until resumed
    """
    if control is None:
        return
    if control.get("cancelled"):
        raise asyncio.CancelledError("Pipeline cancelled by user")
    pause_event = control.get("pause_event")
    if pause_event and not pause_event.is_set():
        while not pause_event.is_set():
            await asyncio.sleep(0.3)
            if control.get("cancelled"):
                raise asyncio.CancelledError("Pipeline cancelled by user")
