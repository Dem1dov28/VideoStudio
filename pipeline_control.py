"""
Pipeline control: pause, resume, cancel.
Used by server and orchestrator to allow user to control running pipelines.
"""

from __future__ import annotations

import asyncio


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
