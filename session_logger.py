"""
Session Logger — изолированное логирование для каждой сессии пайплайна.

Каждая сессия получает свой собственный логгер с уникальным sink,
что гарантирует полную изоляцию логов между параллельными генерациями.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from loguru import logger as _global_logger


class SessionLogger:
    """
    Изолированный логгер для одной сессии.
    
    Каждый SessionLogger имеет:
    - Свою очередь логов для SSE
    - Свой sink в loguru (не shared)
    - Уникальный префикс с session_id во всех сообщениях
    """
    
    def __init__(self, session_id: str, queue: asyncio.Queue | None = None):
        self.session_id = session_id
        self.queue = queue or asyncio.Queue()
        self._sink_id: int | None = None
        self._logs: list[dict] = []
        self._start_time = time.time()
        
    def bind_to_loguru(self, loop: asyncio.AbstractEventLoop) -> None:
        """Создать sink для этой сессии в loguru."""
        if self._sink_id is not None:
            return
            
        def sink_handler(message):
            rec = message.record
            # Проверяем, что этот лог относится к нашей сессии
            log_session_id = rec["extra"].get("session_id")
            if log_session_id != self.session_id:
                return
                
            entry = {
                "type": "log",
                "time": rec["time"].strftime("%H:%M:%S"),
                "level": rec["level"].name,
                "text": rec["message"],
                "session_id": self.session_id,
            }
            # Добавляем в локальный буфер
            self._logs.append(entry)
            # Отправляем в очередь для SSE
            try:
                asyncio.run_coroutine_threadsafe(self.queue.put(entry), loop)
            except Exception:
                pass
        
        # Формат с session_id для отладки
        fmt = f"<green>{{time:HH:mm:ss}}</green> | <level>{{level: <8}}</level> | <cyan>[{self.session_id[:8]}]</cyan> {{message}}"
        self._sink_id = _global_logger.add(
            sink_handler,
            format=fmt,
            level="DEBUG",
            enqueue=False
        )
    
    def unbind(self) -> None:
        """Удалить sink из loguru."""
        if self._sink_id is not None:
            try:
                _global_logger.remove(self._sink_id)
            except Exception:
                pass
            self._sink_id = None
    
    def get_logger(self):
        """Получить logger с привязанным session_id."""
        return _global_logger.bind(session_id=self.session_id)
    
    def info(self, message: str) -> None:
        """Лог INFO уровня."""
        self.get_logger().info(message)
    
    def debug(self, message: str) -> None:
        """Лог DEBUG уровня."""
        self.get_logger().debug(message)
    
    def success(self, message: str) -> None:
        """Лог SUCCESS уровня."""
        self.get_logger().success(message)
    
    def warning(self, message: str) -> None:
        """Лог WARNING уровня."""
        self.get_logger().warning(message)
    
    def error(self, message: str) -> None:
        """Лог ERROR уровня."""
        self.get_logger().error(message)
    
    def get_logs(self) -> list[dict]:
        """Получить все логи сессии."""
        return self._logs.copy()
    
    async def put_done(self, result: dict) -> None:
        """Отправить событие завершения."""
        await self.queue.put({"type": "done", **result})
    
    async def put_error(self, error: str) -> None:
        """Отправить событие ошибки."""
        await self.queue.put({"type": "error", "error": error})


class SessionLoggerManager:
    """
    Менеджер для управления логгерами сессий.
    Гарантирует, что каждая сессия имеет только один активный логгер.
    """
    
    _instance: SessionLoggerManager | None = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loggers: dict[str, SessionLogger] = {}
        return cls._instance
    
    async def create_logger(self, session_id: str, queue: asyncio.Queue | None = None) -> SessionLogger:
        """Создать новый логгер для сессии."""
        async with self._lock:
            # Если уже есть - удаляем старый
            if session_id in self._loggers:
                self._loggers[session_id].unbind()
            
            logger = SessionLogger(session_id, queue)
            self._loggers[session_id] = logger
            return logger
    
    def get_logger(self, session_id: str) -> SessionLogger | None:
        """Получить существующий логгер."""
        return self._loggers.get(session_id)
    
    async def remove_logger(self, session_id: str) -> None:
        """Удалить логгер сессии."""
        async with self._lock:
            if session_id in self._loggers:
                self._loggers[session_id].unbind()
                del self._loggers[session_id]
    
    def get_all_logs(self, session_id: str) -> list[dict]:
        """Получить все логи сессии."""
        logger = self._loggers.get(session_id)
        return logger.get_logs() if logger else []


# Singleton instance
session_logger_manager = SessionLoggerManager()


def get_session_logger(session_id: str) -> SessionLogger | None:
    """Получить логгер сессии (convenience function)."""
    return session_logger_manager.get_logger(session_id)
