"""
Server-side persistent queue for video generation.

Goal:
- Queue must work even when the browser tab is closed.
- Queue state should survive server restarts (simple JSON persistence).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings


@dataclass
class QueueItem:
    id: str
    created_at: float
    payload: dict[str, Any]
    topic: str = ""
    mode: int | None = None
    status: str = "queued"  # queued | starting | started | error | cancelled
    last_error: str | None = None


class QueueManager:
    def __init__(self, path: Path | None = None) -> None:
        settings.ensure_dirs()
        self._path = path or (settings.output_dir / "queue.json")
        self._lock = threading.RLock()
        self._items: list[QueueItem] = []
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._items = []
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8") or "[]")
                items: list[QueueItem] = []
                for x in raw if isinstance(raw, list) else []:
                    if not isinstance(x, dict):
                        continue
                    items.append(
                        QueueItem(
                            id=str(x.get("id") or ""),
                            created_at=float(x.get("created_at") or time.time()),
                            payload=dict(x.get("payload") or {}),
                            topic=str(x.get("topic") or ""),
                            mode=(int(x["mode"]) if isinstance(x.get("mode"), int) or str(x.get("mode", "")).isdigit() else None),
                            status=str(x.get("status") or "queued"),
                            last_error=(str(x["last_error"]) if x.get("last_error") else None),
                        )
                    )
                self._items = [it for it in items if it.id]
                logger.info(f"[Queue] Loaded {len(self._items)} item(s) from {self._path}")
            except Exception as e:
                logger.warning(f"[Queue] Failed to load queue file {self._path}: {e}")
                self._items = []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([asdict(x) for x in self._items], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[Queue] Failed to save queue file {self._path}: {e}")

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(x) for x in self._items]

    def add(self, payload: dict[str, Any]) -> QueueItem:
        now = time.time()
        item = QueueItem(
            id=str(int(now * 1000)),
            created_at=now,
            payload=dict(payload or {}),
            topic=str((payload or {}).get("topic") or ""),
            mode=(int(payload["mode"]) if isinstance((payload or {}).get("mode"), int) or str((payload or {}).get("mode", "")).isdigit() else None),
            status="queued",
        )
        with self._lock:
            self._items.append(item)
            self._save()
        return item

    def remove(self, item_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [x for x in self._items if x.id != str(item_id)]
            changed = len(self._items) != before
            if changed:
                self._save()
            return changed

    def move(self, item_id: str, direction: str) -> bool:
        """direction: 'up' | 'down' | 'top' | 'bottom'"""
        with self._lock:
            idx = next((i for i, x in enumerate(self._items) if x.id == str(item_id)), None)
            if idx is None:
                return False
            item = self._items.pop(idx)
            if direction == "up":
                new_idx = max(0, idx - 1)
            elif direction == "down":
                new_idx = min(len(self._items), idx + 1)
            elif direction == "top":
                new_idx = 0
            elif direction == "bottom":
                new_idx = len(self._items)
            else:
                self._items.insert(idx, item)
                return False
            self._items.insert(new_idx, item)
            self._save()
            return True

    def pop_next(self) -> QueueItem | None:
        with self._lock:
            for i, x in enumerate(self._items):
                if x.status == "queued":
                    x.status = "starting"
                    item = self._items.pop(i)
                    # remove from queue when starting (prevents duplicates on restarts)
                    self._save()
                    return item
            return None

    def push_front(self, item: QueueItem, *, status: str = "queued", last_error: str | None = None) -> None:
        with self._lock:
            item.status = status
            item.last_error = last_error
            self._items.insert(0, item)
            self._save()


_queue_manager: QueueManager | None = None


def get_queue_manager() -> QueueManager:
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager

