"""
UI fonts: prefer ``assets/fonts/Inter-Bold.ttf`` (+ Regular), else Windows system fonts.

Download Inter (OFL) from https://fonts.google.com/specimen/Inter → static TTFs
into ``assets/fonts/`` as ``Inter-Bold.ttf`` and ``Inter-Regular.ttf`` (optional).
"""

from __future__ import annotations

from pathlib import Path
import sys

from PIL import ImageFont

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_FONTS = _PROJECT_ROOT / "assets" / "fonts"
INTER_BOLD = ASSETS_FONTS / "Inter-Bold.ttf"
INTER_REGULAR = ASSETS_FONTS / "Inter-Regular.ttf"

_SYSTEM_BOLD_FALLBACK = [
    # Broad Unicode coverage first (avoids □ for curly quotes in Bible subtitles).
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "C:/Windows/Fonts/ARIALUNI.TTF",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    # Linux (common)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "arialbd.ttf",
    # Pillow bundled
    "DejaVuSans-Bold.ttf",
]

_SYSTEM_REGULAR_FALLBACK = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    # Linux (common)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # Windows
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "arial.ttf",
    # Pillow bundled
    "DejaVuSans.ttf",
]


def load_ui_font(size: int, *, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = INTER_BOLD if bold else INTER_REGULAR
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    fallback = _SYSTEM_BOLD_FALLBACK if bold else _SYSTEM_REGULAR_FALLBACK
    for name in fallback:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    # Last-resort system probing by platform-specific generic names.
    probe = []
    if sys.platform == "darwin":
        probe = (
            ["Arial Bold.ttf", "Helvetica.ttc", "Arial Unicode.ttf"]
            if bold
            else ["Arial.ttf", "Arial Unicode.ttf", "Helvetica.ttc"]
        )
    elif sys.platform.startswith("linux"):
        probe = (
            ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
            if bold
            else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
        )
    for name in probe:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
