"""
Правила промптов и соотношения сторон для FastGen (общие для HTTP API и Playwright UI).
"""

from __future__ import annotations

import re

from config import settings

# К fast-gen.ai: цензура «известные люди» — не подставляем имена, только визуальное описание.
_FASTGEN_NO_NAMES_SUFFIX = (
    "No proper names of real celebrities, politicians, or religious figures — only generic figures by role, era, clothing, and mood; "
    "no recognizable likeness."
)

_FASTGEN_HISTORICAL_LOCK_SUFFIX = (
    "AUTHENTIC HISTORICAL WORLD: this must look like a genuinely premodern setting, not a modern reenactment. "
    "Use only period-appropriate clothing, interiors, tools, furniture, architecture, props, and lighting. "
    "Favor stone, wood, bronze, iron, rough plaster, woven cloth, parchment, scrolls, quills, market stalls, courtyards, "
    "temples, workshops, oil lamps, candles, daylight, and other era-appropriate materials. "
    "Exclude all contemporary technology, office-like layouts, synthetic materials, electrical devices, and modern interior design. "
    "If people are reading, writing, teaching, trading, or planning, show parchment, scrolls, quills, wooden tables, "
    "stone interiors, oil lamps, and hand tools only."
)

_MULTI_IMAGE_BAN_PATTERNS = (
    r"\bcollage\b",
    r"\bcarousel\b",
    r"\bgallery\b",
    r"\bcontact[\s-]?sheet\b",
    r"\b(?:multi|multiple)[-\s]?(?:panel|photo|image|frame|picture)s?\b",
    r"\b(?:grid|mosaic)\b.{0,40}\b(?:photo|image|picture|frame)s?\b",
    r"\b(?:photo|image|picture|frame)\s+grid\b",
    r"\b9[\s-]?(?:photo|image|frame|picture)s?\b",
)

_FASTGEN_SINGLE_IMAGE_ENFORCER_SUFFIX = (
    "Final image requirement is one dominant full-frame image only. "
    "Use a single uninterrupted scene in one frame; avoid any tiled layout, segmented layout, panel layout, or multi-view composition."
)
_FASTGEN_NO_TEXT_ENFORCER_SUFFIX = (
    "Final text restriction is absolutely no visible text anywhere in the image. "
    "No captions, labels, headings, letters, numbers, readable documents, UI, logos, watermarks, "
    "presentation-style layout, or instruction-sheet appearance."
)

_HISTORICAL_HINTS = (
    "ancient rome",
    "ancient greece",
    "ancient egypt",
    "medieval",
    "middle ages",
    "dark ages",
    "byzantine",
    "biblical times",
    "biblical era",
    "bronze age",
    "iron age",
    "viking",
    "crusade",
    "crusader",
    "ottoman empire",
    "renaissance fair",
    "feudal",
    "gladiator",
    "pharaoh",
    "senate of rome",
    "roman legion",
    "premodern",
    "early modern europe",
    "древний рим",
    "древняя греция",
    "средневеков",
    "византий",
    "античн",
    "библейск",
    "доиндустри",
)


def _suppress_historical_lock_suffix(text: str) -> bool:
    low = (text or "").lower()
    if "every still must reflect contemporary" in low:
        return True
    if "contemporary life" in low or "contemporary environments" in low:
        return True
    if "modern self-help" in low:
        return True
    if "modern environments" in low and "contemporary" in low:
        return True
    if "avoid" in low and "historical" in low and ("modern" in low or "contemporary" in low):
        return True
    if "do not align" in low and "modern" in low:
        return True
    if "21st century" in low or "smartphone-era" in low or "smartphone era" in low:
        return True
    if "never default to medieval" in low or "no medieval" in low:
        return True
    return False


def _looks_historical_prompt(text: str) -> bool:
    low = (text or "").lower()
    if _suppress_historical_lock_suffix(text):
        return False
    return any(token in low for token in _HISTORICAL_HINTS)


def prepare_fastgen_prompt_for_ui(user_prompt: str) -> str:
    """Все текстовые промпты в FastGen (картинка и видео) проходят через это."""
    body = (user_prompt or "").strip()
    if body:
        for pattern in _MULTI_IMAGE_BAN_PATTERNS:
            body = re.sub(pattern, " ", body, flags=re.IGNORECASE)
        body = re.sub(r"\s+", " ", body).strip(" ,.;:-")
    if not body:
        return "\n\n".join(
            (_FASTGEN_SINGLE_IMAGE_ENFORCER_SUFFIX, _FASTGEN_NO_TEXT_ENFORCER_SUFFIX, _FASTGEN_NO_NAMES_SUFFIX)
        )
    suffixes = [_FASTGEN_SINGLE_IMAGE_ENFORCER_SUFFIX, _FASTGEN_NO_TEXT_ENFORCER_SUFFIX, _FASTGEN_NO_NAMES_SUFFIX]
    if _looks_historical_prompt(body):
        suffixes.append(_FASTGEN_HISTORICAL_LOCK_SUFFIX)
    return f"{body}\n\n" + "\n\n".join(suffixes)


def _fastgen_aspect_ratio_normalized(override: str | None = None) -> str:
    base = (
        (override.strip() if override and str(override).strip() else None)
        or getattr(settings, "fastgen_aspect_ratio", None)
        or "16:9"
    )
    raw = str(base).strip().lower().replace(" ", "")
    if raw in ("9:16", "16:9", "1:1", "4:3", "3:4"):
        return raw
    return "16:9"


def _fastgen_video_aspect_default() -> str:
    vf = (getattr(settings, "video_format", None) or "vertical").strip().lower()
    return "9:16" if vf == "vertical" else "16:9"


def _resolve_video_tab_aspect_ratio(explicit: str | None) -> str:
    if explicit and str(explicit).strip():
        return _fastgen_aspect_ratio_normalized(explicit)
    return _fastgen_video_aspect_default()


def _fastgen_aspect_select_kw_list(ratio: str) -> list[dict[str, str]]:
    opts: list[dict[str, str]] = [{"value": ratio}]
    if ratio == "16:9":
        opts.extend(
            [
                {"label": "16:9"},
                {"label": "16 : 9"},
                {"label": "Landscape"},
                {"label": "landscape"},
            ]
        )
    elif ratio == "9:16":
        opts.extend(
            [
                {"label": "9:16"},
                {"label": "9 : 16"},
                {"label": "Portrait"},
                {"label": "portrait"},
            ]
        )
    elif ratio == "1:1":
        opts.extend([{"label": "1:1"}, {"label": "Square"}, {"label": "square"}])
    else:
        spaced = ratio.replace(":", " : ")
        opts.extend([{"label": ratio}, {"label": spaced}])
    return opts
