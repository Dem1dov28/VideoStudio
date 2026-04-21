"""
Ровное разбиение притчи на N фрагментов по границам предложений (минимум перекоса по символам).
"""

from __future__ import annotations

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_COMMA_SPLIT = re.compile(r",\s+")


def _split_sentences(text: str) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(t) if p.strip()]
    return parts if parts else [t]


def _chunk_char_len(sents: list[str], i: int, j: int) -> int:
    """Длина объединения sents[i:j] с пробелами."""
    if i >= j:
        return 0
    return sum(len(sents[k]) for k in range(i, j)) + (j - i - 1)


def _ensure_min_pieces(sents: list[str], need: int) -> list[str]:
    """Если предложений мало, дробим длинные по запятым или по словам."""
    out = list(sents)
    safety = 0
    while len(out) < need and safety < 200:
        safety += 1
        longest_i = max(range(len(out)), key=lambda k: len(out[k]))
        piece = out[longest_i]
        if len(piece) < 24:
            break
        sub = [p.strip() for p in _COMMA_SPLIT.split(piece) if p.strip()]
        if len(sub) >= 2:
            out[longest_i : longest_i + 1] = sub
            continue
        mid = len(piece) // 2
        sp = piece.rfind(" ", 8, max(9, mid + 20))
        if sp <= 0:
            break
        a, b = piece[:sp].strip(), piece[sp:].strip()
        if len(a) < 8 or len(b) < 8:
            break
        out[longest_i : longest_i + 1] = [a, b]
    return out


def _partition_minimax(sents: list[str], n: int) -> list[str]:
    """Ровно n непрерывных групп предложений: минимизируем максимум длины группы (DP)."""
    m = len(sents)
    if n <= 1 or m <= 1:
        return [" ".join(sents).strip()] if sents else []
    if m < n:
        sents = _ensure_min_pieces(sents, n)
        m = len(sents)
    if m < n:
        return _char_slices(" ".join(sents), n)

    inf = 10**9
    # dp[k][j] = min max-chunk для sents[0:j] в k частей; br[k][j] = начало последней части
    dp: list[list[int]] = [[inf] * (m + 1) for _ in range(n + 1)]
    br: list[list[int]] = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        dp[1][j] = _chunk_char_len(sents, 0, j)
    for k in range(2, n + 1):
        for j in range(k, m + 1):
            for i in range(k - 1, j):
                seg_len = _chunk_char_len(sents, i, j)
                val = max(dp[k - 1][i], seg_len)
                if val < dp[k][j]:
                    dp[k][j] = val
                    br[k][j] = i
    parts: list[tuple[int, int]] = []
    j, k = m, n
    while k >= 1 and j > 0:
        if k == 1:
            parts.append((0, j))
            break
        i = br[k][j]
        parts.append((i, j))
        j, k = i, k - 1
    parts.reverse()
    return [" ".join(sents[a:b]).strip() for a, b in parts]


def _char_slices(text: str, n: int) -> list[str]:
    t = " ".join(text.split())
    if not t or n < 1:
        return [t] if t else []
    avg = len(t) / n
    out: list[str] = []
    start = 0
    for i in range(n):
        if i == n - 1:
            out.append(t[start:].strip())
            break
        target = int((i + 1) * avg)
        lo = max(start + 1, target - 30)
        hi = min(len(t), target + 40)
        cut = t.rfind(" ", lo, hi)
        if cut <= start:
            cut = t.find(" ", start + 1, len(t))
        if cut == -1 or cut <= start:
            cut = min(len(t), target)
        out.append(t[start:cut].strip())
        start = cut + 1
        while start < len(t) and t[start].isspace():
            start += 1
    return [s for s in out if s]


def _merge_undersized_segments(segments: list[str], min_n: int) -> list[str]:
    """Склеить слишком короткие куски с соседом, пока длины не станут ближе к средней (не ниже min_n частей)."""
    out = [s.strip() for s in segments if s.strip()]
    if len(out) <= min_n:
        return out
    safety = 0
    while len(out) > min_n and safety < len(segments) + 8:
        safety += 1
        avg = sum(len(s) for s in out) / len(out)
        i = min(range(len(out)), key=lambda k: len(out[k]))
        if len(out[i]) >= avg * 0.72:
            break
        if i == 0:
            out[:2] = [" ".join(out[:2]).strip()]
        elif i == len(out) - 1:
            out[-2:] = [" ".join(out[-2:]).strip()]
        else:
            if len(out[i - 1]) <= len(out[i + 1]):
                out[i - 1 : i + 1] = [" ".join(out[i - 1 : i + 1]).strip()]
            else:
                out[i : i + 2] = [" ".join(out[i : i + 2]).strip()]
    return [s for s in out if s]


def unlink_false_sentence_breaks(segments: list[str]) -> list[str]:
    """
    Убирает точку в конце фрагмента, если следующий фрагмент явно продолжает ту же фразу
    (начинается со строчной буквы). Так модель/переводчик не «режут» одно предложение на несколько кадров.
    """
    if len(segments) < 2:
        return list(segments)

    def is_continuation_starter(ch: str) -> bool:
        if not ch:
            return False
        if ch.isascii() and ch.isalpha() and ch.islower():
            return True
        o = ord(ch)
        if o == 0x0451:
            return True
        if 0x0430 <= o <= 0x044F:
            return True
        return False

    out = list(segments)
    for i in range(len(out) - 1):
        a = out[i].rstrip()
        b = (out[i + 1] or "").lstrip()
        if not a or not b:
            continue
        if not a.endswith("."):
            continue
        if is_continuation_starter(b[0]):
            out[i] = a[:-1].rstrip()
    return out


def split_parable_into_balanced_segments(
    text: str,
    min_n: int = 1,
    max_n: int = 500,
    target_chars: int = 102,
) -> list[str]:
    """
    Число фрагментов из длины текста; внутри — DP по предложениям для ~равной длины в символах.
    Верхняя граница max_n завышена намеренно — число кадров не искусственно ограничиваем.
    """
    t = " ".join((text or "").split())
    if not t:
        return []
    n = max(min_n, min(max_n, max(1, (len(t) + target_chars - 1) // target_chars)))
    sents = _split_sentences(t)
    if not sents:
        return [t]
    if len(sents) < n:
        sents = _ensure_min_pieces(sents, n)
    parts = _partition_minimax(sents, n)
    return _merge_undersized_segments(parts, min_n)
