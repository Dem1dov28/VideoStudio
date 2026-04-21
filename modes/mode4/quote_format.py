"""Формат подписи цитаты для UI, истории и списка видео: «"текст" – Автор»."""

import re

# Типографские тире и минус (не ASCII-дефис внутри слова «как-то»)
_UNICODE_DASHES = ("\u2014", "\u2013", "\u2015", "\u2012", "\u2212")


def dashes_to_commas_for_voice(text: str) -> str:
    """
    Только для промпта FastGen: тире → запятая с пробелом, чтобы озвучка не «ломалась».

    Субтитры, история и format_quote_caption вызываются с оригиналом — без этой замены.
    """
    if not text:
        return text
    s = text
    for ch in _UNICODE_DASHES:
        s = s.replace(ch, ", ")
    # Тире как знак препинания: пробел - пробел (ASCII), не трогаем дефис внутри слова
    s = re.sub(r"\s+-\s+", ", ", s)
    s = re.sub(r",\s*,+", ", ", s)
    return s


def strip_quotes_for_voice(text: str) -> str:
    """
    Убрать кавычки из текста для промпта озвучки (видео-модели часто не произносят строку в кавычках как речь).
    Апостроф внутри слов (don't, кто-то) не трогаем.
    """
    if not text:
        return text
    s = dashes_to_commas_for_voice(text)
    for ch in (
        "\u00ab",
        "\u00bb",
        "\u201c",
        "\u201d",
        "\u201e",
        "\u201f",
        "\u2039",
        "\u203a",
        "\u2018",  # ‘
        "\u00b4",  # acute
        '"',
    ):
        s = s.replace(ch, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def unlink_split_quotes_across_segments(segments: list[str]) -> list[str]:
    """
    Одна реплика в кавычках разбита на несколько кадров: с конца каждого кроме последнего
    убираем «висячие» открывающие кавычки, с начала каждого кроме первого — лишние закрывающие,
    чтобы закрытие не оказывалось на стыке не там, где смысл.
    """
    if len(segments) < 2:
        return list(segments)
    out = list(segments)
    trailing_open = frozenset("«\u201c\u2018\u201e")
    leading_close = frozenset("»\u201d")
    ascii_dq = '"'
    for i in range(len(out)):
        s = out[i]
        if i < len(out) - 1:
            s = s.rstrip()
            while s:
                last = s[-1]
                if last in trailing_open or last == ascii_dq:
                    s = s[:-1].rstrip()
                else:
                    break
        if i > 0:
            s = s.lstrip()
            while s:
                first = s[0]
                if first in leading_close or first == ascii_dq:
                    s = s[1:].lstrip()
                else:
                    break
        out[i] = s
    return out


def strip_outer_quote_marks(text: str) -> str:
    """Убрать одну пару внешних кавычек «», "", "…" у цитаты."""
    q = (text or "").strip()
    if len(q) >= 2:
        if q[0] == q[-1] and q[0] in '"«"':
            return q[1:-1].strip()
        if q[0] == "«" and q[-1] == "»":
            return q[1:-1].strip()
    return q


def format_quote_caption(
    quote: str,
    person_name: str,
    *,
    include_quotes: bool = True,
) -> str:
    """
    Пример: "Пусть дела твои будут такими…" – Марк Аврелий
    (кавычки ASCII, тире — en dash U+2013).

    include_quotes: False — только текст цитаты без обрамляющих кавычек (для кадра без автора).
    """
    q = strip_outer_quote_marks(quote)
    pn = (person_name or "").strip()
    if not q:
        return pn or ""
    body = f'"{q}"' if include_quotes else q
    if pn:
        return f"{body} – {pn}"
    return body
