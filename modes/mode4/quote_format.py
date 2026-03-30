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


def format_quote_caption(quote: str, person_name: str) -> str:
    """
    Пример: "Пусть дела твои будут такими…" – Марк Аврелий
    (кавычки ASCII, тире — en dash U+2013).
    """
    q = (quote or "").strip()
    pn = (person_name or "").strip()
    if len(q) >= 2:
        if q[0] == q[-1] and q[0] in '"«"':
            q = q[1:-1].strip()
        elif q[0] == "«" and q[-1] == "»":
            q = q[1:-1].strip()
    if not q:
        return pn or ""
    body = f'"{q}"'
    if pn:
        return f"{body} – {pn}"
    return body
