"""
Subtitle overlay for MoviePy 2.x — text-only subtitle.

- Mode 4: активное слово подсвечивается (SUB_GOLD), синхрон Whisper по аудио
- Прочие режимы: строки по одной с кроссфейдом; без золотой караоке
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw

from agents.video_editor import design_tokens as dt
from agents.video_editor.fonts import load_ui_font

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


def align_script_to_whisper(
    script_words: list[str],
    word_timestamps: list[tuple[float, float]],
) -> list[tuple[float, float]] | None:
    """
    Сопоставляет слова скрипта с таймкодами Whisper (разная длина).
    Возвращает (start, end) для каждого слова скрипта.
    """
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
        # Скрипт короче — объединяем интервалы Whisper
        ratio = K / N
        for i in range(N):
            j0 = min(int(i * ratio), K - 1)
            j1 = min(int((i + 1) * ratio), K)
            start = word_timestamps[j0][0]
            end = word_timestamps[j1 - 1][1] if j1 > j0 else word_timestamps[j0][1]
            result.append((start, end))
    else:
        # Скрипт длиннее — распределяем по интервалам
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
) -> np.ndarray:
    """
    Full-frame RGBA with a bottom text subtitle (no background pill).
    All words white, numbers purple. Line transitions crossfade over 0.25s.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text or not text.strip():
        return np.array(img)

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
            ts_for_display = word_timestamps
        else:
            ts_for_display = align_script_to_whisper(words, word_timestamps)

    if not words:
        return np.array(img)

    # Не показывать субтитры до начала первой фразы (озвучка FastGen может начинаться с паузы)
    if ts_for_display and len(ts_for_display) > 0 and t < ts_for_display[0][0]:
        return np.array(img)

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
    font_size = max(30, min(54, width // 16))
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
    fade_in: float = 0.45,
    bottom_frac: float = 0.88,
) -> np.ndarray:
    """
    Mode 4: многострочная цитата у нижнего края; текущее слово — SUB_GOLD, остальные белые.
    Таймкоды Whisper по дорожке FastGen (word_timestamps + tts_words → align к словам скрипта).
    Автор под цитатой отдельной строкой (без караоке).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    qt = (quote_text or "").strip()
    if not qt:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    font_size = max(30, min(54, width // 16))
    font = load_ui_font(font_size, bold=True)
    stroke_w = 5

    raw = qt.split()
    words = _merge_dashes_with_words(raw)
    words = _merge_short_with_adjacent(words)
    ts_for_display: list[tuple[float, float]] | None = None
    if word_timestamps and tts_words and len(tts_words) == len(word_timestamps):
        if len(words) == len(word_timestamps):
            ts_for_display = word_timestamps
        else:
            ts_for_display = align_script_to_whisper(words, word_timestamps)

    if not words:
        return np.array(img)

    if ts_for_display and len(ts_for_display) > 0 and t < ts_for_display[0][0]:
        return np.array(img)

    active_index = _active_word_index(t, duration, words, ts_for_display)

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
    y_band = max(dt.SUBTITLE_PAD_Y, bottom_y - total_h)

    # Позиции слов через textlength префиксов — как у одной строки с пробелами:
    # одинаковые зазоры + кернинг; textbbox по словам + отдельный пробел даёт «рваные» промежутки.
    def _word_start_x(words_row: list[str], j: int) -> float:
        if j <= 0:
            return 0.0
        prefix = " ".join(words_row[0:j]) + " "
        return _pil_text_advance(draw, font, prefix, stroke_w)

    for li, (ln, lh) in enumerate(zip(lines, line_heights)):
        words_line = [w for w, _ in ln]
        disp = " ".join(words_line)
        total_line_w = _pil_text_advance(draw, font, disp, stroke_w)
        x0 = int(round((width - total_line_w) / 2.0))
        y_text = y_band + (max_lh - lh) // 2
        for j, (word, wi) in enumerate(ln):
            cx = x0 + int(round(_word_start_x(words_line, j)))
            is_act = wi == active_index
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
