"""
UI fonts: prefer ``assets/fonts/Inter-Bold.ttf`` (+ Regular), else Windows system fonts.

Download Inter (OFL) from https://fonts.google.com/specimen/Inter → static TTFs
into ``assets/fonts/`` as ``Inter-Bold.ttf`` and ``Inter-Regular.ttf`` (optional).
"""

from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_FONTS = _PROJECT_ROOT / "assets" / "fonts"
INTER_BOLD = ASSETS_FONTS / "Inter-Bold.ttf"
INTER_REGULAR = ASSETS_FONTS / "Inter-Regular.ttf"

_SYSTEM_FALLBACK = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "arialbd.ttf",
    "arial.ttf",
]


def load_ui_font(size: int, *, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = INTER_BOLD if bold else INTER_REGULAR
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    for name in _SYSTEM_FALLBACK:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
