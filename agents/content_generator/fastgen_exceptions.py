"""Ошибки FastGen, общие для Playwright- и HTTP-транспорта."""


class VideoGenerationError(RuntimeError):
    """Ошибка генерации, обнаруженная на стороне генератора (можно перегенерировать)."""
    pass


class FastGenCancelled(Exception):
    """Пользователь отменил пайплайн."""
    pass
