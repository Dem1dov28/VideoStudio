"""Mode 3 constants."""

NUM_RESTORATION_CLIPS = 5


def mode3_blueprint_lock(blueprint: str) -> str:
    """
    Одна и та же строка структуры во все промпты картинок/видео.
    Модель всё равно может дрейфовать — это максимум без ControlNet/API с strength.
    """
    b = (blueprint or "").strip() or (
        "small one-story house, gable roof, 2 windows left of door, 1 window right, centered door, timber walls"
    )
    return (
        f"STRUCTURE_ID (must match in EVERY output, do not invent a different building): {b}. "
        f"Repeat check: {b}. "
    )


# Общий префикс для img2img (доп. к пошаговым промптам ниже)
IMG2IMG_REF_PREFIX = (
    "CRITICAL: REFERENCE = uploaded image. SAME building — roof outline, window count and positions, door, footprint, camera angle. "
    "Change ONLY restoration level. Do NOT output a different house. "
)

# ── Экстерьер: фото разрушенного → чуть лучше → идеал (два шага img2img в FastGen) ──
EXTERIOR_IMG2IMG_STEP1_SLIGHT = (
    "TASK: img2img from the ONE uploaded photo of a RUINED house. "
    "The output MUST be the SAME building — same silhouette, roof shape, every window and the door in the same places, same wall texture, same yard/trees/sky, same viewpoint. "
    "FORBIDDEN: a different house, new design, moving or resizing windows or door, extra floors, different land. "
    "ALLOWED ONLY: small visible improvements — less trash in yard, slightly tidier walls, slightly smaller holes in roof, maybe early repairs — still mostly ruined (~65–75% destroyed), unmistakably the same structure. "
    "Photorealistic, 9:16. "
)

EXTERIOR_IMG2IMG_STEP2_PERFECT = (
    "TASK: img2img from the ONE uploaded photo (slightly improved same house). "
    "Output the IDENTICAL house fully restored — same footprint, same window and door positions, same roof geometry, same surroundings. "
    "NOW: perfect new roof, fresh paint or siding, all windows glazed, finished door, clean landscaped yard, no debris, no scaffolding. "
    "FORBIDDEN: replacing with a new building. Photorealistic magazine exterior, 9:16. "
)

# ── Интерьер: то же для комнаты (цепочка stills от ext_ruined → int) ──
INTERIOR_IMG2IMG_STEP1_HALF = (
    "TASK: img2img from the ONE uploaded interior photo. "
    "Output the SAME room — same walls, same window and door openings, ceiling height, floor area, camera angle, debris layout. "
    "FORBIDDEN: different room, different window count, new layout. "
    "ALLOWED: restore about HALF — clearer floor, partial ceiling/wall repair, materials visible, still mid-job, some mess OK. "
    "Photorealistic, 9:16, one room studio. "
)

INTERIOR_IMG2IMG_STEP2_PERFECT = (
    "TASK: img2img from the ONE uploaded photo (half-restored room). "
    "Same room — same openings and proportions. "
    "NOW: fully finished — painted walls, finished floor, furniture, lighting, no workers, no debris, magazine interior. "
    "Photorealistic, 9:16. "
)

# ── Интерьер от скриншота первого видеофрагмента (два шага img2img) ──
INTERIOR_INTRO_VIDEO_STEP1_HALF = (
    "REFERENCE = SCREENSHOT from our video (end of clip 1) — this EXACT ruin interior, same geometry and perspective. "
    "Img2img ONLY: output the SAME room — same walls, window and door openings, ceiling, floor area, camera. "
    "FORBIDDEN: different room or layout. ALLOWED: restore about HALF — partial repairs, cleaner, still mid-renovation. "
    "Photorealistic, 9:16, one room. "
)

INTERIOR_INTRO_VIDEO_STEP2_PERFECT = (
    "REFERENCE = previous image: half-restored SAME room from the video screenshot. Img2img: complete to FULL finish — "
    "same openings and proportions, painted walls, floor done, furniture, lighting, no workers, no debris, magazine-ready. "
    "Photorealistic, 9:16. "
)
