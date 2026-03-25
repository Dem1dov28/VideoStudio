"""Формат подписи цитаты для UI, истории и списка видео: «"текст" – Автор»."""


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
