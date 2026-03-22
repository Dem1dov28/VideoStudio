"""
Shared visual tokens for Shorts-style overlays (typography, colour, radii).

Used by subtitles, title/outro cards, hook banner, counter, watermark.
"""

from __future__ import annotations

# Brand (violet) — Tailwind violet-600 family
ACCENT_RGB: tuple[int, int, int] = (124, 58, 237)
ACCENT_SOFT_RGB: tuple[int, int, int] = (167, 139, 250)
ACCENT_RGBA: tuple[int, int, int, int] = (124, 58, 237, 255)

# Surfaces
SURFACE_DARK_RGBA: tuple[int, int, int, int] = (12, 10, 22, 235)
SURFACE_CARD_RGBA: tuple[int, int, int, int] = (18, 14, 32, 220)
HOOK_BAR_RGBA: tuple[int, int, int, int] = (14, 8, 28, 228)

# Text
TEXT_PRIMARY: tuple[int, int, int] = (255, 255, 255)
TEXT_MUTED: tuple[int, int, int] = (210, 205, 225)
TEXT_HOOK_SECONDARY: tuple[int, int, int] = (220, 200, 255)

# Subtitle highlights (karaoke + numbers)
SUB_GOLD: tuple[int, int, int, int] = (255, 214, 90, 255)
SUB_PURPLE: tuple[int, int, int, int] = (196, 181, 255, 255)
SUB_WHITE: tuple[int, int, int, int] = (255, 255, 255, 255)
SUB_DIM: tuple[int, int, int, int] = (200, 198, 210, 200)  # inactive words

# Layout
RADIUS_PILL: int = 28
RADIUS_HOOK: int = 20
RADIUS_BADGE: int = 12
RADIUS_WATERMARK: int = 10

# Позиция субтитров: 0.75 = центр в середине нижней половины экрана
SUBTITLE_VERTICAL_CENTER_FRAC: float = 0.75
SUBTITLE_PAD_X: int = 36
SUBTITLE_PAD_Y: int = 22
SUBTITLE_MAX_WIDTH_FRAC: float = 0.88

# Title / outro strokes
STROKE_TITLE: tuple[int, int, int] = (45, 25, 95)
STROKE_HOOK: tuple[int, int, int] = (25, 12, 60)
