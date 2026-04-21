"""
Azure OpenAI / OpenRouter: распознавание отказа по политике контента (content_filter).
"""

from __future__ import annotations


CONTENT_FILTER_USER_MESSAGE_RU = (
    "Модель заблокировала запрос фильтром контента. "
    "Попробуйте: другую модель (в OpenRouter — без провайдера Azure), в портале Azure ослабить Content filtering для деплоя, "
    "или чуть сократить и переформулировать текст."
)


def iter_exception_chain(exc: BaseException):
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        yield e
        e = e.__cause__ or e.__context__


def is_provider_content_filter_error(exc: BaseException) -> bool:
    """True если в цепочке исключений виден типичный ответ Azure/OpenRouter content_filter."""
    blob = " ".join(str(e) for e in iter_exception_chain(exc)).lower()
    if "content_filter" in blob.replace(" ", ""):
        return True
    if "content filter" in blob:
        return True
    if "responsibleaipolicyviolation" in blob.replace(" ", "").replace("_", ""):
        return True
    if "content management policy" in blob:
        return True
    return False
