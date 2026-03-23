"""
Mode 3 — 5 клипов для минимизации дрейфа. Reference = первый кадр каждого клипа.

КРИТИЧНО: окна и дверь НЕ МЕНЯЮТ позиции. Один дом во всех кадрах.
"""

from modes.mode3.constants import NUM_RESTORATION_CLIPS

# Первая строка КАЖДОГО промпта — заморозка дома
def _lock_line(spec: str) -> str:
    s = (spec or "").strip() or "small wooden house"
    return (
        f"HOUSE LOCK — {s}. WINDOWS AND DOOR: positions NEVER change. "
        "Same house in ALL clips. Reference = exact building. Copy reference. "
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
    # 2: экстерьер — окна + финиш → скриншот для clip 4
    (
        "REFERENCE = roof done, walls done. Workers: windows, door, paint, remove scaffolding. TIME-LAPSE. End: exterior restored. Screenshot this frame. "
    ),
    # 3: интерьер
    (
        "REFERENCE = ruined ONE room interior. Workers: debris, ceiling, walls, floor, paint, furniture. TIME-LAPSE. ONE room. End: completed interior. "
    ),
    # 4: финальный показ — ref = скриншот clip 2
    (
        "REFERENCE = restored exterior (screenshot clip 2). THIS EXACT house. First frame = reference. No workers. Pan inside — interior of THIS house. ONE room. "
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
