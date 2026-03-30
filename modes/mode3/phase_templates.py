"""
Mode 3 — 5 клипов для минимизации дрейфа. Reference = первый кадр каждого клипа.

КРИТИЧНО: окна и дверь НЕ МЕНЯЮТ позиции. Один дом во всех кадрах.
"""

from modes.mode3.constants import NUM_RESTORATION_CLIPS

# Первая строка КАЖДОГО промпта — заморозка дома
def _lock_line(spec: str) -> str:
    s = (spec or "").strip() or "small wooden house"
    return (
        f"HOUSE LOCK — {s}. STRUCTURE_ID repeat: {s}. "
        "FROZEN: roof shape, window count, door position — ZERO change across ALL clips. "
        "Reference = exact building. First frame = reference PIXEL-PERFECT. Same house throughout. "
    )

PHASE_TEMPLATES = [
    # 0: INTRO — развалины снаружи и внутри
    (
        "REFERENCE = ruined small house exterior. Start EXACTLY with reference. Then pan inside: ONE ruined room. Same building. END interior. No workers. "
    ),
    # 1: экстерьер — стены + кровля
    (
        "REFERENCE = ruined exterior. Workers: debris, scaffolding, walls, roof. TIME-LAPSE. WINDOWS+DOOR positions = reference. End: roof done, no windows yet. "
    ),
    # 2: экстерьер — окна + финиш; финальный кадр = ПОЛНОСТЬЮ готово
    (
        "REFERENCE = roof and walls structurally done. Workers: install windows, door, exterior paint, remove ALL scaffolding. TIME-LAPSE. "
        "FINAL FRAME MUST BE: fully finished exterior — fresh paint, all windows with glass, finished door, clean yard, ZERO scaffolding, ZERO workers, renovation 100% complete. "
    ),
    # 3: интерьер — финал = журнальный готовый зал
    (
        "REFERENCE = ruined ONE room interior. Workers: ceiling, walls, floor, paint, furniture, lighting. TIME-LAPSE. ONE room, layout frozen. "
        "FINAL FRAME MUST BE: fully finished interior — painted walls, finished floor, furniture placed, lights on, NO workers, NO debris, magazine-ready COMPLETE room. "
    ),
    # 4: финал — два референса (последние кадры clip 2 и 3) задают экстерьер и интерьер
    (
        "Use BOTH reference images: first = finished exterior, second = finished interior of SAME house. "
        "Start matching first ref (exterior), then transition inside matching second ref exactly. No workers. ONE room inside. "
    ),
]


def build_video_prompts(location_spec: str) -> list[str]:
    """
    Строит 5 промптов. Первая строка = HOUSE LOCK (окна, дверь не меняются).
    """
    spec = (location_spec or "").strip() or "small one-story house, gable roof, 2 windows, center door"
    lock = _lock_line(spec)
    prompts = []
    for i in range(NUM_RESTORATION_CLIPS):
        phase = PHASE_TEMPLATES[i]
        prompt = f"{lock}{phase}"
        prompts.append(prompt)
    return prompts
