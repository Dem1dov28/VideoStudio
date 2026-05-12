"""
Subtitle overlay for MoviePy 2.x — text-only subtitle.

- Mode 4: активное слово подсвечивается (SUB_GOLD), синхрон Whisper по аудио
- Прочие режимы: строки по одной с кроссфейдом; без золотой караоке
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw

from agents.video_editor import design_tokens as dt
from agents.video_editor.fonts import load_ui_font
from config import settings

if TYPE_CHECKING:
    from PIL import ImageFont

_NUMBER_RE = re.compile(r"\d[\d.,]*%?")
# Standalone dash (тире должно идти вместе со словом, не отдельно)
_STANDALONE_DASH_RE = re.compile(r"^[\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]+$")

# Короткие слова и местоимения — не показывать отдельно (RU + EN)
_SHORT_OR_PRONOUN = frozenset(
    "и а в у с к о на по из до от за мы вы я ты же ли бы не ни но как что".split()
    + "он она оно они его её им ей нас вас их this that the a an is are was were i we you he she it".split()
)


def _merge_short_with_adjacent(words: list[str]) -> list[str]:
    """Склеить короткие слова (≤2 буквы) и местоимения со соседним словом."""
    if not words:
        return words
    result: list[str] = []

    def is_short(w: str) -> bool:
        w = w.strip()
        return len(w) <= 2 or (w and w.lower() in _SHORT_OR_PRONOUN)

    i = 0
    while i < len(words):
        w = words[i]
        if is_short(w):
            if i + 1 < len(words):
                result.append(w + " " + words[i + 1])
                i += 2
                continue
            if result:
                result[-1] = result[-1] + " " + w
                i += 1
                continue
        result.append(w)
        i += 1
    return result


def _merge_dashes_with_words(words: list[str]) -> list[str]:
    """Merge standalone dashes with adjacent word (— другое → —другое)."""
    result: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if _STANDALONE_DASH_RE.match(w):
            if i + 1 < len(words):
                result.append(w + words[i + 1])
                i += 2
                continue
            if result:
                result[-1] = result[-1] + w
                i += 1
                continue
        result.append(w)
        i += 1
    return result


def _pil_text_advance(draw: ImageDraw.ImageDraw, font: object, text: str, stroke_w: int) -> float:
    """Ширина строки для вёрстки; в старых Pillow у textlength нет stroke_width."""
    if not text:
        return 0.0
    try:
        return float(draw.textlength(text, font=font, stroke_width=stroke_w))
    except TypeError:
        bb = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
        return float(bb[2] - bb[0])


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_px: int,
    draw: ImageDraw.ImageDraw,
    *,
    stroke_width: int | None = None,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    tb_kw = {}
    if stroke_width is not None:
        tb_kw["stroke_width"] = stroke_width
    for word in words:
        candidate = (current + " " + word).strip()
        bb = draw.textbbox((0, 0), candidate, font=font, **tb_kw)
        w = bb[2] - bb[0]
        if w <= max_px:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _word_style_plain(word: str) -> tuple[tuple[int, int, int, int], int]:
    """All words white, numbers purple."""
    if _NUMBER_RE.search(word):
        return dt.SUB_PURPLE, 5
    return dt.SUB_WHITE, 5


def _norm_word_align(w: str) -> str:
    """Нормализация для сопоставления скрипта с токенами Whisper."""
    t = (w or "").strip().lower()
    t = re.sub(r"[^\w\d]", "", t, flags=re.UNICODE)
    if t:
        return t
    raw = (w or "").strip().lower()
    return raw[:1] if raw else "\u200b"


def _alignment_parts_for_display_words(words: list[str]) -> tuple[list[str], list[tuple[int, int]]]:
    """
    Экранные токены могут быть склейками коротких слов: "of teachers", "a long".
    Whisper возвращает эти слова отдельно, поэтому выравниваем по внутренним частям,
    а потом схлопываем интервалы обратно к экранному токену.
    """
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    for word in words:
        start = len(parts)
        raw_parts = [p for p in str(word or "").split() if p.strip()]
        if not raw_parts:
            raw_parts = [str(word or "")]
        for part in raw_parts:
            parts.append(_norm_word_align(part))
        spans.append((start, len(parts)))
    return parts, spans


def _collapse_part_times_to_display_words(
    part_times: list[tuple[float, float]],
    spans: list[tuple[int, int]],
) -> list[tuple[float, float]] | None:
    if not part_times:
        return None
    out: list[tuple[float, float]] = []
    for start, end in spans:
        if start < 0 or end <= start or end > len(part_times):
            return None
        out.append((float(part_times[start][0]), float(part_times[end - 1][1])))
    return out


def _script_alignment_head_timeline_skewed(
    aligned: list[tuple[float, float]],
    word_timestamps: list[tuple[float, float]],
    *,
    n_script: int,
) -> bool:
    """
    Если первые ~25% слов скрипта по выравниванию укладываются в доли секунды на общей
    шкале речи Whisper, пословный SequenceMatcher почти наверняка склеил начало фразы в
    один короткий чанк — подсветка «перелетает» к середине («pray … a long time»).
    """
    if n_script < 12 or len(aligned) != n_script or len(word_timestamps) < 2:
        return False
    t_audio0 = float(word_timestamps[0][0])
    t_audio1 = float(word_timestamps[-1][1])
    span = t_audio1 - t_audio0
    if span < 1.0:
        return False
    q = max(3, n_script // 4)
    t_q_end = float(aligned[q - 1][1])
    head_frac = (t_q_end - t_audio0) / span
    return head_frac < 0.088


def _align_script_to_whisper_proportional(
    script_words: list[str],
    word_timestamps: list[tuple[float, float]],
) -> list[tuple[float, float]] | None:
    """Старый пропорциональный маппинг — запасной путь без текста Whisper."""
    if not word_timestamps or not script_words:
        return None
    K, N = len(word_timestamps), len(script_words)
    if K == N:
        return list(word_timestamps)
    t0, t1 = word_timestamps[0][0], word_timestamps[-1][1]
    total = t1 - t0
    if total <= 0:
        return None
    result: list[tuple[float, float]] = []
    if N <= K:
        ratio = K / N
        for i in range(N):
            j0 = min(int(i * ratio), K - 1)
            j1 = min(int((i + 1) * ratio), K)
            start = word_timestamps[j0][0]
            end = word_timestamps[j1 - 1][1] if j1 > j0 else word_timestamps[j0][1]
            result.append((start, end))
    else:
        ratio = N / K
        for i in range(N):
            k = min(int(i / ratio), K - 1)
            seg_s, seg_e = word_timestamps[k]
            seg_len = seg_e - seg_s
            sub_count = max(1, int((k + 1) * ratio) - int(k * ratio))
            sub_i = i - int(k * ratio)
            sub_i = min(sub_i, sub_count - 1)
            step = seg_len / sub_count
            start = seg_s + sub_i * step
            end = seg_s + (sub_i + 1) * step
            result.append((start, end))
    return result


def apply_whisper_word_start_lead(
    wt: list[tuple[float, float]],
    *,
    lead_sec: float,
) -> list[tuple[float, float]]:
    """
    Сдвигает границы слов чуть раньше: Whisper часто ставит start позже слышимого слога —
    подсветка/смена строки меньше отстают (режим цитаты / несколько фрагментов и др.).
    """
    if lead_sec <= 0 or not wt:
        return list(wt)
    min_span = 0.042
    out: list[tuple[float, float]] = []
    for a, b in wt:
        fa, fb = float(a), float(b)
        na = max(0.0, fa - lead_sec)
        nb = max(na + min_span, fb - lead_sec * 0.35)
        out.append((na, nb))
    return _enforce_monotonic_word_times(out)


def _enforce_monotonic_word_times(
    ts: list[tuple[float, float]], *, eps: float = 0.012
) -> list[tuple[float, float]]:
    """Убирает сильные перекрытия границ слов (Whisper иногда даёт end > next.start)."""
    if not ts:
        return ts
    out: list[tuple[float, float]] = [ts[0]]
    for i in range(1, len(ts)):
        a, b = float(ts[i][0]), float(ts[i][1])
        pa, pb = out[-1]
        if a < pb:
            a = pb + eps * 0.35
        if b < a + eps:
            b = a + eps
        out.append((a, b))
    return out


def sanitize_quote_word_timestamps_for_display(
    ts: list[tuple[float, float]],
    duration: float,
    *,
    min_span: float = 0.056,
    max_gap: float = 0.42,
    max_passes: int = 8,
) -> list[tuple[float, float]]:
    """
    Лёгкая постобработка после align_script_to_whisper.

    Раньше здесь «схлопывали» большие зазоры между словами (ставили следующее слово
    ближе по времени). Это убирало залипание подсветки в паузах, но сдвигало *start*
    следующего слова раньше реальной речи — после первой части абзаца или второго клипа
    накапливался явный рассинхрон («каша»).

    Сейчас: только монотонность, слегка удлиняем слишком короткие интервалы за счёт
    зазора *до следующего слова* (не трогаем start следующего слова) и хвоста клипа.
    Большие паузы в распознавании Whisper остаются — подсветка может чуть запаздывать
    в паузе, зато не опережает голос.
    """
    if not ts or duration <= 0.02:
        return ts
    out = [(float(a), float(b)) for a, b in ts]
    out = _enforce_monotonic_word_times(out)

    for _ in range(max_passes):
        out = _enforce_monotonic_word_times(out)
        changed = False
        for i in range(len(out)):
            a, b = out[i]
            if b - a >= min_span - 1e-9:
                continue
            need = min_span - (b - a)
            if i + 1 < len(out):
                na, nb = out[i + 1]
                gap = na - b
                floor_gap = min(max_gap * 0.5, 0.12)
                take = min(need, max(0.0, gap - floor_gap))
                if take <= 1e-9:
                    continue
                out[i] = (a, b + take)
                changed = True
            else:
                tail = duration - b
                take = min(need, max(0.0, tail - 0.035))
                if take <= 1e-9:
                    continue
                out[i] = (a, b + take)
                changed = True
        if not changed:
            break

    out = _enforce_monotonic_word_times(out)
    eps = 0.015
    fixed: list[tuple[float, float]] = []
    for a, b in out:
        a = max(0.0, min(a, max(0.0, duration - eps * 2)))
        b = max(a + 0.032, min(b, duration))
        fixed.append((a, b))
    return _enforce_monotonic_word_times(fixed)


def _enforce_min_word_span(
    ts: list[tuple[float, float]],
    duration: float,
    *,
    min_dur: float = 0.056,
    eps: float = 0.008,
) -> list[tuple[float, float]]:
    """
    Растягивает слишком короткие интервалы Whisper — иначе караоке «скачет» и визуально догоняет голос.
    Не выходит за duration и за начало следующего слова (если есть).
    """
    if not ts or duration <= 0.02:
        return ts
    out: list[tuple[float, float]] = [(float(a), float(b)) for a, b in ts]
    n = len(out)
    for i in range(n):
        a, b = out[i]
        cap_next = duration if i + 1 >= n else out[i + 1][0] - eps
        if b - a < min_dur and cap_next > a + eps:
            out[i] = (a, min(cap_next, a + min_dur))
    for i in range(1, n):
        a, b = out[i]
        pm = out[i - 1][1]
        if a < pm + eps:
            na = pm + eps
            nb = max(b, na + min_dur * 0.45)
            out[i] = (na, min(nb, duration))
    if out[-1][1] > duration:
        out[-1] = (min(out[-1][0], duration - eps * 2), duration)
    return out


def _draw_mode4_quote_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[list[tuple[str, int]]],
    line_heights: list[int],
    max_lh: int,
    line_gap: int,
    width: int,
    font: object,
    stroke_w: int,
    y_band: int,
    active_index: int | None,
) -> int:
    """Рисует строки цитаты Mode 4; active_index=None — все слова белые (преролл до Whisper)."""
    for li, (ln, lh) in enumerate(zip(lines, line_heights)):
        words_line = [w for w, _ in ln]
        disp = " ".join(words_line)
        total_line_w = _pil_text_advance(draw, font, disp, stroke_w)
        x0 = int(round((width - total_line_w) / 2.0))
        y_text = y_band + (max_lh - lh) // 2

        def _word_start_x_row(words_row: list[str], j: int) -> float:
            if j <= 0:
                return 0.0
            prefix = " ".join(words_row[0:j]) + " "
            return _pil_text_advance(draw, font, prefix, stroke_w)

        for j, (word, wi) in enumerate(ln):
            cx = x0 + int(round(_word_start_x_row(words_line, j)))
            is_act = active_index is not None and wi == active_index
            fill = dt.SUB_GOLD if is_act else dt.SUB_WHITE
            if _NUMBER_RE.search(word) and not is_act:
                fill = dt.SUB_PURPLE
            draw.text(
                (cx, y_text),
                word,
                font=font,
                fill=fill,
                stroke_width=stroke_w,
                stroke_fill=(20, 12, 30, 245),
            )
        y_band += max_lh + (line_gap if li < len(lines) - 1 else 0)
    return y_band


def align_script_to_whisper(
    script_words: list[str],
    word_timestamps: list[tuple[float, float]],
    whisper_words: list[str] | None = None,
) -> list[tuple[float, float]] | None:
    """
    Сопоставляет слова скрипта (после merge коротких) с таймкодами Whisper.
    Сначала выравнивание по тексту (SequenceMatcher), иначе — пропорциональный fallback.

    Сначала разворачивает экранные склейки коротких слов ("of the", "a long") в
    внутренние части, сопоставимые с токенами Whisper. Иначе даже идеальный транскрипт
    получает низкий ratio и ошибочно уходит в пропорциональный fallback.
    """
    # Ниже этого порога пословное выравнивание чаще ломает тайминг, чем помогает.
    _MIN_TEXT_MATCH_RATIO = 0.78

    if not word_timestamps or not script_words:
        return None
    K = len(word_timestamps)
    align_words, display_spans = _alignment_parts_for_display_words(script_words)
    N = len(align_words)
    if not align_words:
        return None
    if whisper_words is None or len(whisper_words) != K:
        raw = _align_script_to_whisper_proportional(align_words, word_timestamps)
        if not raw:
            return None
        collapsed = _collapse_part_times_to_display_words(
            _enforce_monotonic_word_times(raw), display_spans
        )
        return _enforce_monotonic_word_times(collapsed) if collapsed else None

    seq_a = align_words
    seq_b = [_norm_word_align(w) for w in whisper_words]
    if N == K and seq_a == seq_b:
        collapsed = _collapse_part_times_to_display_words(
            _enforce_monotonic_word_times(list(word_timestamps)), display_spans
        )
        return _enforce_monotonic_word_times(collapsed) if collapsed else None

    sm = SequenceMatcher(a=seq_a, b=seq_b, autojunk=False)
    if sm.ratio() < _MIN_TEXT_MATCH_RATIO:
        raw = _align_script_to_whisper_proportional(align_words, word_timestamps)
        if not raw:
            return None
        collapsed = _collapse_part_times_to_display_words(
            _enforce_monotonic_word_times(raw), display_spans
        )
        return _enforce_monotonic_word_times(collapsed) if collapsed else None
    result: list[tuple[float, float] | None] = [None] * N
    pending_lead_start: float | None = None

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for di in range(i2 - i1):
                result[i1 + di] = (
                    float(word_timestamps[j1 + di][0]),
                    float(word_timestamps[j1 + di][1]),
                )
        elif tag == "replace":
            ws = align_words[i1:i2]
            chunk = word_timestamps[j1:j2]
            if not chunk or not ws:
                continue
            t0, t1w = float(chunk[0][0]), float(chunk[-1][1])
            if len(ws) == 1:
                result[i1] = (t0, t1w)
            else:
                weights = [max(1, len(_norm_word_align(w)) or 1) for w in ws]
                total_w = sum(weights)
                span = max(t1w - t0, 0.02)
                nws = len(ws)
                # Нижняя доля чанка на каждое слово скрипта — иначе 5–15 слов в 0.15–0.25 с
                # дают «пролёт» подсветки и длинную паузу до следующего токена Whisper.
                floor_each = min(0.10, span / max(nws, 1) * 1.65)
                if floor_each * nws > span - 1e-9:
                    floor_each = span / nws
                remainder = max(0.0, span - floor_each * nws)
                durs: list[float] = []
                for idx, w in enumerate(ws):
                    share = (weights[idx] / total_w) if total_w else 1.0 / nws
                    durs.append(max(0.032, floor_each + remainder * share))
                tot = sum(durs)
                if tot > span + 1e-9:
                    sf = span / tot
                    durs = [max(0.03, d * sf) for d in durs]
                    tot2 = sum(durs)
                    if tot2 < span - 1e-9:
                        durs[-1] += span - tot2
                cur = t0
                for idx in range(nws):
                    ne = t1w if idx == nws - 1 else min(t1w, cur + durs[idx])
                    if ne <= cur + 0.028:
                        ne = min(t1w, cur + 0.036)
                    result[i1 + idx] = (cur, ne)
                    cur = ne
        elif tag == "insert":
            if j2 <= j1:
                continue
            t_ins0 = float(word_timestamps[j1][0])
            t_ins1 = float(word_timestamps[j2 - 1][1])
            if i1 == 0:
                pending_lead_start = (
                    t_ins0 if pending_lead_start is None else min(pending_lead_start, t_ins0)
                )
            if i1 > 0:
                pi = i1 - 1
                if result[pi] is not None:
                    s, e = result[pi]
                    result[pi] = (s, max(e, t_ins1))
            if i1 < N and result[i1] is not None:
                s, e = result[i1]
                result[i1] = (min(s, t_ins0), e)
        # delete: заполним интерполяцией ниже

    if pending_lead_start is not None:
        fi = next((i for i, r in enumerate(result) if r is not None), None)
        if fi is not None:
            s, e = result[fi]
            result[fi] = (min(s, pending_lead_start), e)

    # Интерполяция для «осиротевших» слов скрипта (delete / пропуски)
    for i in range(N):
        if result[i] is not None:
            continue
        prev_t: tuple[float, float] | None = None
        next_t: tuple[float, float] | None = None
        for j in range(i - 1, -1, -1):
            if result[j] is not None:
                prev_t = result[j]
                break
        for j in range(i + 1, N):
            if result[j] is not None:
                next_t = result[j]
                break
        if prev_t and next_t:
            t0, t1 = prev_t[1], next_t[0]
            if t1 <= t0:
                t1 = t0 + 0.04
            result[i] = (t0, t1)
        elif prev_t:
            result[i] = (prev_t[1], prev_t[1] + 0.08)
        elif next_t:
            result[i] = (max(0.0, next_t[0] - 0.08), next_t[0])
        else:
            raw = _align_script_to_whisper_proportional(align_words, word_timestamps)
            if not raw:
                return None
            collapsed = _collapse_part_times_to_display_words(
                _enforce_monotonic_word_times(raw), display_spans
            )
            return _enforce_monotonic_word_times(collapsed) if collapsed else None

    if any(r is None for r in result):
        raw = _align_script_to_whisper_proportional(align_words, word_timestamps)
        if not raw:
            return None
        collapsed = _collapse_part_times_to_display_words(
            _enforce_monotonic_word_times(raw), display_spans
        )
        return _enforce_monotonic_word_times(collapsed) if collapsed else None

    out = [(float(a), float(b)) for a, b in result]
    out = _enforce_monotonic_word_times(out)
    if _script_alignment_head_timeline_skewed(out, word_timestamps, n_script=N):
        raw = _align_script_to_whisper_proportional(align_words, word_timestamps)
        if not raw:
            return None
        collapsed = _collapse_part_times_to_display_words(
            _enforce_monotonic_word_times(raw), display_spans
        )
        return _enforce_monotonic_word_times(collapsed) if collapsed else None
    collapsed = _collapse_part_times_to_display_words(out, display_spans)
    return _enforce_monotonic_word_times(collapsed) if collapsed else None


def _active_word_index(
    t: float,
    duration: float,
    words: list[str],
    word_timestamps: list[tuple[float, float]] | None,
) -> int:
    """
    Return which word is active at time t (0..duration).
    If word_timestamps provided: use exact (start, end) in seconds per word.
    In gaps between words: show last completed word (avoids flicker to word 0).
    Else: use word-length-weighted allocation (longer words get more time).
    """
    n = len(words)
    if n == 0:
        return 0
    if n == 1:
        return 0

    if word_timestamps and len(word_timestamps) == n:
        for i, (start, end) in enumerate(word_timestamps):
            if start <= t < end:
                return i
        if t >= word_timestamps[-1][1]:
            return n - 1
        # In gap: show last completed word (prevents flicker to word 0)
        for i in range(n - 1, -1, -1):
            if word_timestamps[i][1] <= t:
                return i
        return 0

    progress = max(0.0, min(1.0, t / duration)) if duration > 0 else 1.0
    # Word-length-weighted: longer words take proportionally more time
    weights = [max(1, len(w)) for w in words]
    total_w = sum(weights)
    cum = 0.0
    for i, w in enumerate(weights):
        cum += w / total_w
        if progress <= cum or i == n - 1:
            return i
    return n - 1


def _draw_line(
    img: Image.Image,
    line_words: list[tuple[str, int]],
    width: int,
    height: int,
    font,
    draw: ImageDraw.ImageDraw,
) -> None:
    """Draw one line of subtitle words (all white, numbers purple)."""
    display_text = " ".join(w for w, _ in line_words)
    bb_line = draw.textbbox((0, 0), display_text, font=font)
    line_h = bb_line[3] - bb_line[1]
    # Центр строки на середине нижней половины (0.75 от высоты)
    center_y = height * dt.SUBTITLE_VERTICAL_CENTER_FRAC
    text_y = int(center_y - line_h / 2)
    line_w = bb_line[2] - bb_line[0]
    x = (width - line_w) // 2
    y = text_y
    space_w = draw.textbbox((0, 0), " ", font=font)[2] - draw.textbbox((0, 0), " ", font=font)[0]
    cx = x
    for word, _ in line_words:
        style, stroke = _word_style_plain(word)
        bw = draw.textbbox((0, 0), word, font=font)[2] - draw.textbbox((0, 0), word, font=font)[0]
        draw.text((cx, y), word, font=font, fill=style, stroke_width=stroke, stroke_fill=(20, 12, 30, 245))
        cx += bw + space_w


def _blend_overlays(
    ov_a: np.ndarray,
    ov_b: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """Blend two RGBA overlays: result = a * (1-alpha) + b * alpha."""
    a = np.clip(alpha, 0.0, 1.0)
    out = ov_a.copy()
    mask = ov_b[:, :, 3:4] > 0
    for c in range(4):
        out[:, :, c] = np.where(
            mask.squeeze(),
            (ov_a[:, :, c] * (1 - a) + ov_b[:, :, c] * a).astype(np.uint8),
            out[:, :, c],
        )
    out[:, :, 3] = np.maximum(ov_a[:, :, 3], (ov_b[:, :, 3] * a).astype(np.uint8))
    return out


def _render_subtitle_block_static(
    text: str,
    width: int,
    height: int,
    *,
    font_divisor: int = 15,
) -> np.ndarray:
    """
    Весь текст сегмента сразу: перенос по ширине, несколько строк, без пословного караоке.
    Меньший шрифт, чем обычные субтитры (mode 13).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    plain = (text or "").strip()
    if not plain:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    div = max(10, min(26, int(font_divisor)))
    font_size = max(18, min(34, width // div))
    font = load_ui_font(font_size, bold=True)
    stroke_w = max(2, font_size // 12)

    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X
    lines: list[str] = []
    for para in (p.strip() for p in plain.replace("\r\n", "\n").split("\n")):
        if not para:
            continue
        lines.extend(_wrap_text(para, font, max_text_w, draw, stroke_width=stroke_w))
    if not lines:
        return np.array(img)

    line_heights: list[int] = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_heights.append(bb[3] - bb[1])

    line_gap = max(8, font_size // 5) + stroke_w
    max_lh = max(line_heights)
    n = len(lines)
    total_h = n * max_lh + (n - 1) * line_gap
    center_y = height * dt.SUBTITLE_VERTICAL_CENTER_FRAC
    y_band = int(center_y - total_h / 2)
    y_band = max(dt.SUBTITLE_PAD_Y, y_band)

    for line, lh in zip(lines, line_heights):
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_w = bb[2] - bb[0]
        x = (width - line_w) // 2
        y_text = y_band + (max_lh - lh) // 2
        if _NUMBER_RE.search(line):
            # Одна строка может содержать числа — упростим: весь ряд белый, кроме токенов
            words_line = line.split()
            cx = x
            space_w = _pil_text_advance(draw, font, " ", stroke_w)
            for w in words_line:
                fill = dt.SUB_PURPLE if _NUMBER_RE.search(w) else dt.SUB_WHITE
                draw.text(
                    (cx, y_text),
                    w,
                    font=font,
                    fill=fill,
                    stroke_width=stroke_w,
                    stroke_fill=(20, 12, 30, 245),
                )
                cx += int(_pil_text_advance(draw, font, w, stroke_w) + space_w)
        else:
            draw.text(
                (x, y_text),
                line,
                font=font,
                fill=dt.SUB_WHITE,
                stroke_width=stroke_w,
                stroke_fill=(20, 12, 30, 245),
            )
        y_band += max_lh + line_gap

    return np.array(img)


def _mode4_quote_font_size(width: int) -> int:
    """Размер шрифта для Mode 4 (цитаты) с масштабом из env."""
    # Для 9:16 базу держим крупнее обычных «универсальных» сабов в цитатах.
    base_size = width // 12
    raw_scale = float(getattr(settings, "mode4_quote_subtitle_scale", 1.2) or 1.2)
    scale = max(0.7, min(2.0, raw_scale))
    return max(42, min(120, int(round(base_size * scale))))


def get_mode4_quote_font_size(width: int) -> int:
    """Public helper for logging/debug in assembler."""
    return _mode4_quote_font_size(width)


def _render_subtitle_timed_plain(
    text: str,
    width: int,
    height: int,
    t: float,
    duration: float,
    *,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    transition_state: dict | None = None,
    max_words_per_line: int = 2,
    font_scale: float = 1.0,
) -> np.ndarray:
    """
    Plain-Whisper для Mode 4: короткая активная строка без золотого слова.
    Нужен для поведения «как раньше» — по 2-3 слова в строке, а не весь текст сразу.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    plain = (text or "").strip()
    if not plain:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    safe_scale = max(0.7, min(2.0, float(font_scale or 1.0)))
    base_font_size = max(44, min(72, width // 11))
    font_size = max(44, min(110, int(round(base_font_size * safe_scale))))
    font = load_ui_font(font_size, bold=True)

    raw = plain.split()
    words = _merge_dashes_with_words(raw)
    words = _merge_short_with_adjacent(words)
    ts_for_display: list[tuple[float, float]] | None = None
    if word_timestamps and tts_words and len(tts_words) == len(word_timestamps):
        if len(words) == len(word_timestamps):
            ts_for_display = _enforce_monotonic_word_times(list(word_timestamps))
        else:
            ts_for_display = align_script_to_whisper(words, word_timestamps, tts_words)

    if not words:
        return np.array(img)
    if ts_for_display and len(ts_for_display) == len(words):
        ts_for_display = _enforce_min_word_span(ts_for_display, float(duration))
        ts_for_display = sanitize_quote_word_timestamps_for_display(
            ts_for_display, float(duration)
        )

    active_index = _active_word_index(t, duration, words, ts_for_display)
    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X

    lines: list[list[tuple[str, int]]] = []
    line: list[tuple[str, int]] = []
    for i, w in enumerate(words):
        candidate = " ".join(wd for wd, _ in line) + (" " + w if line else w)
        bb = draw.textbbox((0, 0), candidate, font=font)
        too_wide = (bb[2] - bb[0]) > max_text_w
        too_long = len(line) >= max_words_per_line
        if line and (too_wide or too_long):
            lines.append(line)
            line = [(w, i)]
        else:
            line.append((w, i))
    if line:
        lines.append(line)

    ideal_line_idx = 0
    for idx, ln in enumerate(lines):
        if any(gi == active_index for _, gi in ln):
            ideal_line_idx = idx
            break
    line_words = lines[ideal_line_idx] if lines else [(words[active_index], active_index)]

    TRANSITION_DUR = 0.24
    STABLE_FWD = 0.08
    STABLE_BWD = 0.18
    SWITCH_COOLDOWN = 0.26
    use_transition = transition_state is not None and len(lines) > 1
    if use_transition and transition_state:
        cur = transition_state.get("line_idx", -1)
        req_line = transition_state.get("requested_line_idx", -1)
        req_start = transition_state.get("request_start_t", 0.0)
        last_switch = transition_state.get("last_switch_t", -999.0)

        if ideal_line_idx != cur:
            if cur < 0:
                transition_state["line_idx"] = ideal_line_idx
                transition_state["line_words"] = line_words
                transition_state["requested_line_idx"] = -1
                transition_state["last_switch_t"] = t
            elif (t - last_switch) < SWITCH_COOLDOWN:
                line_words = lines[cur] if 0 <= cur < len(lines) else line_words
            else:
                stable = STABLE_BWD if ideal_line_idx < cur else STABLE_FWD
                if ideal_line_idx == req_line and (t - req_start) >= stable:
                    old_words = transition_state.get("line_words")
                    if old_words is None and 0 <= cur < len(lines):
                        old_words = lines[cur]
                    transition_state["prev_line_words"] = old_words or line_words
                    transition_state["line_idx"] = ideal_line_idx
                    transition_state["line_words"] = line_words
                    transition_state["switch_t"] = t
                    transition_state["last_switch_t"] = t
                    transition_state["requested_line_idx"] = -1
                else:
                    if ideal_line_idx != req_line:
                        transition_state["requested_line_idx"] = ideal_line_idx
                        transition_state["request_start_t"] = t
                    line_words = lines[cur] if 0 <= cur < len(lines) else line_words

        prev_words = transition_state.get("prev_line_words")
        elapsed = t - transition_state.get("switch_t", t)
        cur_displayed = transition_state.get("line_idx", ideal_line_idx)
        displayed_words = lines[cur_displayed] if 0 <= cur_displayed < len(lines) else line_words
        if elapsed < TRANSITION_DUR and prev_words and prev_words != displayed_words:
            raw_blend = elapsed / TRANSITION_DUR
            progress = raw_blend * raw_blend * (3.0 - 2.0 * raw_blend)
            img_prev = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            dr_prev = ImageDraw.Draw(img_prev)
            _draw_line(img_prev, prev_words, width, height, font, dr_prev)
            img_next = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            dr_next = ImageDraw.Draw(img_next)
            _draw_line(img_next, displayed_words, width, height, font, dr_next)
            return _blend_overlays(np.array(img_prev), np.array(img_next), progress)

    _draw_line(img, line_words, width, height, font, draw)
    return np.array(img)


def render_subtitle_overlay(
    text: str,
    width: int,
    height: int,
    t: float,
    duration: float,
    *,
    karaoke: bool = True,
    word_timestamps: list[tuple[float, float]] | None = None,
    tts_words: list[str] | None = None,
    transition_state: dict | None = None,
    static_font_divisor: int = 15,
    timed_plain: bool = False,
    timed_plain_font_scale: float = 1.0,
) -> np.ndarray:
    """
    Full-frame RGBA with a bottom text subtitle (no background pill).
    karaoke=True: одна строка за раз + подсветка «активного» слова (эвристика / Whisper).
    karaoke=False: весь текст сегмента сразу, меньший шрифт (mode 13).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text or not text.strip():
        return np.array(img)

    if not karaoke and timed_plain:
        return _render_subtitle_timed_plain(
            text.strip(),
            width,
            height,
            t,
            duration,
            word_timestamps=word_timestamps,
            tts_words=tts_words,
            transition_state=transition_state,
            font_scale=timed_plain_font_scale,
        )

    if not karaoke:
        return _render_subtitle_block_static(
            text.strip(), width, height, font_divisor=static_font_divisor
        )

    draw = ImageDraw.Draw(img)
    font_size = max(56, min(92, width // 9))
    font = load_ui_font(font_size, bold=True)

    raw = text.strip().split()
    words = _merge_dashes_with_words(raw)
    words = _merge_short_with_adjacent(words)
    # Синхронизация: таймкоды Whisper (озвучка FastGen) → слова скрипта
    ts_for_display: list[tuple[float, float]] | None = None
    if word_timestamps and tts_words and len(tts_words) == len(word_timestamps):
        if len(words) == len(word_timestamps):
            ts_for_display = _enforce_monotonic_word_times(list(word_timestamps))
        else:
            ts_for_display = align_script_to_whisper(words, word_timestamps, tts_words)

    if not words:
        return np.array(img)

    if ts_for_display and len(ts_for_display) == len(words):
        ts_for_display = _enforce_min_word_span(ts_for_display, float(duration))
        ts_for_display = sanitize_quote_word_timestamps_for_display(
            ts_for_display, float(duration)
        )

    preroll = bool(
        ts_for_display and len(ts_for_display) > 0 and t < float(ts_for_display[0][0])
    )
    if preroll:
        active_index = 0
    else:
        active_index = _active_word_index(t, duration, words, ts_for_display)

    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X

    lines: list[list[tuple[str, int]]] = []
    line: list[tuple[str, int]] = []
    for i, w in enumerate(words):
        candidate = " ".join(wd for wd, _ in line) + (" " + w if line else w)
        bb = draw.textbbox((0, 0), candidate, font=font)
        if (bb[2] - bb[0]) <= max_text_w:
            line.append((w, i))
        else:
            if line:
                lines.append(line)
            line = [(w, i)]
    if line:
        lines.append(line)

    ideal_line_idx = 0
    for idx, ln in enumerate(lines):
        if any(gi == active_index for _, gi in ln):
            ideal_line_idx = idx
            break
    line_words = lines[ideal_line_idx] if lines else [(words[active_index], active_index)]

    TRANSITION_DUR = 0.28
    STABLE_FWD = 0.10   # вперёд (0→1): быстрее — строка появляется с первым словом
    STABLE_BWD = 0.22   # назад (1→0): дольше — защита от мерцания при скачках active_index
    SWITCH_COOLDOWN = 0.35
    use_transition = transition_state is not None and len(lines) > 1
    if use_transition and transition_state:
        cur = transition_state.get("line_idx", -1)
        req_line = transition_state.get("requested_line_idx", -1)
        req_start = transition_state.get("request_start_t", 0.0)
        last_switch = transition_state.get("last_switch_t", -999.0)

        if ideal_line_idx != cur:
            if cur < 0:
                transition_state["line_idx"] = ideal_line_idx
                transition_state["line_words"] = line_words
                transition_state["requested_line_idx"] = -1
                transition_state["last_switch_t"] = t
            elif (t - last_switch) < SWITCH_COOLDOWN:
                line_words = lines[cur] if 0 <= cur < len(lines) else line_words
            else:
                stable = STABLE_BWD if ideal_line_idx < cur else STABLE_FWD
                if ideal_line_idx == req_line and (t - req_start) >= stable:
                    old_words = transition_state.get("line_words")
                    if old_words is None and 0 <= cur < len(lines):
                        old_words = lines[cur]
                    transition_state["prev_line_words"] = old_words or line_words
                    transition_state["line_idx"] = ideal_line_idx
                    transition_state["line_words"] = line_words
                    transition_state["switch_t"] = t
                    transition_state["last_switch_t"] = t
                    transition_state["requested_line_idx"] = -1
                else:
                    if ideal_line_idx != req_line:
                        transition_state["requested_line_idx"] = ideal_line_idx
                        transition_state["request_start_t"] = t
                    line_words = lines[cur] if 0 <= cur < len(lines) else line_words

        prev_words = transition_state.get("prev_line_words")
        elapsed = t - transition_state.get("switch_t", t)
        cur_displayed = transition_state.get("line_idx", ideal_line_idx)
        displayed_words = lines[cur_displayed] if 0 <= cur_displayed < len(lines) else line_words
        if elapsed < TRANSITION_DUR and prev_words and prev_words != displayed_words:
            raw = elapsed / TRANSITION_DUR
            progress = raw * raw * (3.0 - 2.0 * raw)  # smoothstep
            img_prev = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            dr_prev = ImageDraw.Draw(img_prev)
            _draw_line(img_prev, prev_words, width, height, font, dr_prev)
            img_next = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            dr_next = ImageDraw.Draw(img_next)
            _draw_line(img_next, displayed_words, width, height, font, dr_next)
            arr_prev = np.array(img_prev)
            arr_next = np.array(img_next)
            blended = _blend_overlays(arr_prev, arr_next, progress)
            return blended

    img_out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dr_out = ImageDraw.Draw(img_out)
    _draw_line(img_out, line_words, width, height, font, dr_out)
    return np.array(img_out)


def render_static_quote_caption_overlay(
    text: str,
    width: int,
    height: int,
    t: float,
    duration: float,
    *,
    fade_in: float = 0.45,
    bottom_frac: float = 0.88,
) -> np.ndarray:
    """
    Полная подпись «"цитата" – Автор» несколькими строками у нижнего края (Mode 4).
    Без пословной синхронизации с Whisper — текст виден на протяжении ролика.
    Межстрочный интервал фиксированный; textbbox с учётом обводки — без наложения строк.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text or not text.strip():
        return np.array(img)
    draw = ImageDraw.Draw(img)
    font_size = _mode4_quote_font_size(width)
    font = load_ui_font(font_size, bold=True)
    stroke_w = 5
    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X
    lines = _wrap_text(
        text.strip(), font, max_text_w, draw, stroke_width=stroke_w,
    )
    if not lines:
        return np.array(img)

    line_heights: list[int] = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_heights.append(bb[3] - bb[1])
    # Фиксированный зазор между полосами строк + одинаковая высота полосы (max высота строки)
    line_gap = max(14, font_size // 4) + stroke_w
    max_lh = max(line_heights)
    n = len(lines)
    total_h = n * max_lh + (n - 1) * line_gap
    bottom_y = int(height * bottom_frac)
    y_band = max(dt.SUBTITLE_PAD_Y, bottom_y - total_h)

    alpha_m = min(1.0, t / fade_in) if fade_in > 0 else 1.0
    for line, lh in zip(lines, line_heights):
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_w = bb[2] - bb[0]
        x = (width - line_w) // 2
        y_text = y_band + (max_lh - lh) // 2
        draw.text(
            (x, y_text),
            line,
            font=font,
            fill=dt.SUB_WHITE,
            stroke_width=stroke_w,
            stroke_fill=(20, 12, 30, 245),
        )
        y_band += max_lh + line_gap

    arr = np.array(img)
    if alpha_m < 1.0:
        arr = arr.copy()
        arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * alpha_m).astype(np.uint8)
    return arr


def render_quote_header_overlay(
    text: str,
    width: int,
    height: int,
    t: float,
    duration: float,
    *,
    fade_in: float = 0.35,
    top_frac: float = 0.05,
) -> np.ndarray:
    """
    Фиксированный заголовок у верхнего края (Mode 4): крупный жёлтый текст с тёмной обводкой.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text or not text.strip():
        return np.array(img)
    draw = ImageDraw.Draw(img)
    # Заметно крупнее обычных субтитров; на узком 9:16 — верхняя граница ~ширина/7
    font_size = max(46, min(92, width // 7))
    font = load_ui_font(font_size, bold=True)
    stroke_w = max(5, font_size // 9)
    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X
    lines = _wrap_text(text.strip(), font, max_text_w, draw, stroke_width=stroke_w)
    if not lines:
        return np.array(img)

    line_heights: list[int] = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_heights.append(bb[3] - bb[1])
    line_gap = max(12, font_size // 5) + stroke_w
    max_lh = max(line_heights)
    n = len(lines)
    total_h = n * max_lh + (n - 1) * line_gap
    y0 = max(dt.SUBTITLE_PAD_Y, int(height * top_frac))
    y_band = y0

    alpha_m = min(1.0, t / fade_in) if fade_in > 0 else 1.0
    # Яркий жёлтый как акцент (тот же золотой токен, что караоке-слово)
    yellow_fill = tuple(dt.SUB_GOLD[:3])

    for line, lh in zip(lines, line_heights):
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        line_w = bb[2] - bb[0]
        x = (width - line_w) // 2
        y_text = y_band + (max_lh - lh) // 2
        draw.text(
            (x, y_text),
            line,
            font=font,
            fill=yellow_fill,
            stroke_width=stroke_w,
            stroke_fill=(24, 18, 6, 255),
        )
        y_band += max_lh + line_gap

    arr = np.array(img)
    if alpha_m < 1.0:
        arr = arr.copy()
        arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * alpha_m).astype(np.uint8)
    return arr


def render_mode4_quote_karaoke_overlay(
    quote_text: str,
    author_name: str | None,
    width: int,
    height: int,
    t: float,
    duration: float,
    word_timestamps: list[tuple[float, float]] | None,
    tts_words: list[str] | None,
    *,
    fade_in: float = 0.22,
    bottom_frac: float = 0.88,
) -> np.ndarray:
    """
    Mode 4: многострочная цитата у нижнего края; текущее слово — SUB_GOLD, остальные белые.
    Таймкоды Whisper по дорожке FastGen (word_timestamps + tts_words → align к словам скрипта).
    До первого таймкода Whisper текст показывается целиком белым (без «пустого» начала фрагмента).
    Автор под цитатой отдельной строкой (без караоке).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    qt = (quote_text or "").strip()
    if not qt:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    font_size = _mode4_quote_font_size(width)
    font = load_ui_font(font_size, bold=True)
    stroke_w = 5

    raw = qt.split()
    words = _merge_dashes_with_words(raw)
    words = _merge_short_with_adjacent(words)
    ts_for_display: list[tuple[float, float]] | None = None
    if word_timestamps and tts_words and len(tts_words) == len(word_timestamps):
        if len(words) == len(word_timestamps):
            ts_for_display = _enforce_monotonic_word_times(list(word_timestamps))
        else:
            ts_for_display = align_script_to_whisper(words, word_timestamps, tts_words)

    if not words:
        return np.array(img)

    if ts_for_display and len(ts_for_display) == len(words):
        ts_for_display = _enforce_min_word_span(ts_for_display, float(duration))
        ts_for_display = sanitize_quote_word_timestamps_for_display(
            ts_for_display, float(duration)
        )

    max_text_w = int(width * dt.SUBTITLE_MAX_WIDTH_FRAC) - 2 * dt.SUBTITLE_PAD_X
    lines: list[list[tuple[str, int]]] = []
    line: list[tuple[str, int]] = []
    for i, w in enumerate(words):
        candidate = " ".join(wd for wd, _ in line) + (" " + w if line else w)
        bb = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_w)
        if (bb[2] - bb[0]) <= max_text_w:
            line.append((w, i))
        else:
            if line:
                lines.append(line)
            line = [(w, i)]
    if line:
        lines.append(line)

    line_heights: list[int] = []
    for ln in lines:
        disp = " ".join(w for w, _ in ln)
        bb = draw.textbbox((0, 0), disp, font=font, stroke_width=stroke_w)
        line_heights.append(bb[3] - bb[1])
    # Одна высота полосы для всех строк — иначе у кириллицы (р, у, д…) межстрочка «гуляет», латиница визуально ровнее
    max_lh = max(line_heights) if line_heights else 0
    line_gap = max(6, font_size // 10) + max(2, stroke_w // 2)

    author_line = ""
    author_h = 0
    author_gap = 0
    an = (author_name or "").strip()
    if an:
        author_line = f"– {an}"
        bb_a = draw.textbbox((0, 0), author_line, font=font, stroke_width=stroke_w)
        author_h = bb_a[3] - bb_a[1]
        author_gap = line_gap

    n = len(lines)
    total_quote_h = n * max_lh + (n - 1) * line_gap if n else 0
    total_h = total_quote_h + (author_gap + author_h if author_h else 0)
    bottom_y = int(height * bottom_frac)
    y_band0 = max(dt.SUBTITLE_PAD_Y, bottom_y - total_h)

    preroll = bool(
        ts_for_display
        and len(ts_for_display) > 0
        and t < float(ts_for_display[0][0])
    )
    if preroll:
        active_index: int | None = None
    else:
        active_index = _active_word_index(t, duration, words, ts_for_display)

    y_band = _draw_mode4_quote_lines(
        draw,
        lines,
        line_heights,
        max_lh,
        line_gap,
        width,
        font,
        stroke_w,
        y_band0,
        active_index,
    )

    if author_line:
        aw = _pil_text_advance(draw, font, author_line, stroke_w)
        ax = int(round((width - aw) / 2.0))
        ay = y_band + author_gap
        draw.text(
            (ax, ay),
            author_line,
            font=font,
            fill=(*dt.TEXT_MUTED, 255),
            stroke_width=stroke_w,
            stroke_fill=(20, 12, 30, 245),
        )

    arr = np.array(img)
    alpha_m = min(1.0, t / fade_in) if fade_in > 0 else 1.0
    if alpha_m < 1.0:
        arr = arr.copy()
        arr[:, :, 3] = (arr[:, :, 3].astype(np.float32) * alpha_m).astype(np.uint8)
    return arr


# ── Backwards-compatible alias (static frame = no karaoke progression) ─────

def _make_subtitle_frame(text: str, width: int, height: int) -> np.ndarray:
    """Single-state subtitle (e.g. tests); full brightness on first word via t=large."""
    return render_subtitle_overlay(text, width, height, t=1e9, duration=1.0, karaoke=False)


def add_subtitle_to_clip(clip, text: str, fade_in_duration: float = 0.30):
    """Legacy helper: composite static subtitle with fade-in (rarely used)."""
    from moviepy import CompositeVideoClip, ImageClip, VideoClip

    if not text or not text.strip():
        return clip
    w, h = clip.size
    static_arr = _make_subtitle_frame(text, w, h)
    dur = clip.duration

    def make_alpha_frame(t: float) -> np.ndarray:
        alpha = min(1.0, t / fade_in_duration) if fade_in_duration > 0 else 1.0
        fr = static_arr.copy()
        fr[:, :, 3] = (fr[:, :, 3] * alpha).astype(np.uint8)
        return fr

    subtitle_clip = VideoClip(lambda t: make_alpha_frame(t), duration=dur).with_fps(clip.fps)
    return CompositeVideoClip([clip, subtitle_clip])
