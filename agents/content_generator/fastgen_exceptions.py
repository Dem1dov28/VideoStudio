"""Ошибки FastGen, общие для Playwright- и HTTP-транспорта."""


class VideoGenerationError(RuntimeError):
    """Ошибка генерации, обнаруженная на стороне генератора (можно перегенерировать)."""

    def __init__(self, message: str, *, api_detail: dict | None = None):
        super().__init__(message)
        self.api_detail = api_detail


class FastGenCancelled(Exception):
    """Пользователь отменил пайплайн."""
    pass
