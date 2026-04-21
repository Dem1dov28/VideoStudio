"""Mode 7 — два клипа, два still (до = text2img, после = img2img от «до»)."""

NUM_TWO_CLIP_CLIPS = 2

# Img2img второго кадра: универсально для пляжа, улицы, стройки, дома, интерьера (не только «дом Mode 3»).
MODE7_REF_PREFIX = (
    "CRITICAL: REFERENCE = the generated BEFORE image. "
    "Same camera, horizon, perspective, spatial layout, and identity of place/room — do NOT relocate or redesign. "
)

MODE7_IMG2IMG_TO_AFTER_EXTERIOR = (
    "TASK: img2img from that BEFORE photo. "
    "Output the SAME outdoor scene — same shoreline/street/plot/building shell, same viewpoint. "
    "FORBIDDEN: a different location, moved camera, different building footprint. "
    "ALLOWED: transform toward the AFTER description — cleanliness, construction stage, restoration, etc. "
    "Photorealistic, vertical 9:16. "
)

MODE7_IMG2IMG_TO_AFTER_INTERIOR = (
    "TASK: img2img from that BEFORE interior photo. "
    "Output the SAME room — same walls, window and door openings, ceiling height, floor area, camera angle. "
    "FORBIDDEN: different room or layout. "
    "ALLOWED: transform toward the AFTER description — renovation progress, finished design, etc. "
    "Photorealistic, vertical 9:16. "
)

# id → короткий заголовок для UI и истории
PRESET_LABELS: dict[str, str] = {
    "beach_cleanup": "Уборка пляжа",
    "street_cleanup": "Уборка улицы",
    "house_build_zero": "Строительство дома с нуля",
    "house_restoration": "Восстановление дома",
    "interior_restoration": "Восстановление интерьера",
    "interior_from_scratch": "Интерьер с нуля",
}

VALID_PRESET_IDS = frozenset(PRESET_LABELS.keys())

# Пресеты — интерьер одной комнаты (второй кадр: img2img с интерьерными ограничениями)
INTERIOR_PRESETS = frozenset({"interior_restoration", "interior_from_scratch"})

# Жёсткий английский хвост к промпту видео: таймлапс + люди в движении (дополняет ответ LLM).
VIDEO_TIMELAPSE_SUFFIX_BY_PRESET: dict[str, str] = {
    "beach_cleanup": (
        " HYPERLAPSE / TIME-LAPSE: dozens of volunteers in high-vis vests constantly moving—running, crouching, "
        "stuffing plastic and bottles into big bags, dragging full sacks, raking sand, wheelbarrows; "
        "trash visibly vanishes over compressed time; same beach angle; busy human energy, motion blur acceptable."
    ),
    "street_cleanup": (
        " HYPERLAPSE: sanitation crews with brooms and blowers, sweeping in fast motion, garbage bags lining the curb, "
        "small utility vehicle or cart, workers crossing frame repeatedly; leaves and litter cleared over time; same street view."
    ),
    "house_build_zero": (
        " CONSTRUCTION TIME-LAPSE: workers and machinery in sped-up motion—excavation, foundation pour, framing walls rising, "
        "roof trusses, siding; cranes and ladders; same building plot and camera; visible structure growing across the clip."
    ),
    "house_restoration": (
        " RENOVATION HYPERLAPSE: scaffolding, roofers, masons, painters on ladders, debris hauled away, new windows and facade "
        "appearing in accelerated time; many trades moving; same house shell and viewpoint."
    ),
    "interior_restoration": (
        " INTERIOR TIME-LAPSE: renovation crew in fast motion—demolition blur, drywall, mudding, paint rollers, floor layers, "
        "electricians; furniture and fixtures appearing; same room layout and camera; no empty magic morph."
    ),
    "interior_from_scratch": (
        " FIT-OUT HYPERLAPSE: workers installing plasterboard, flooring, lighting, kitchen units, doors, then styling; "
        "compressed time, people constantly working; same fixed camera in one room."
    ),
}

VIDEO_TIMELAPSE_FALLBACK = (
    " TIME-LAPSE: many workers in accelerated motion transforming the scene; visible labor and progress; same fixed viewpoint."
)

# Общее для всех клипов Mode 7/8: модель часто делает «статичный кадр А → резкий морф/диссолв на кадр B» — это запрещаем.
VIDEO_NO_AB_SLIDESHOW = (
    " CRITICAL — NOT A TWO-IMAGE SLIDESHOW: do NOT show a long static shot matching ref1 then only at the end crossfade/morph/jump to ref2. "
    "FORBIDDEN: dissolve-only transition, Ken Burns between two stills, or empty scene with no bodies moving. "
    "REQUIRED: hyperlapse pacing—visible work and motion from the first seconds through the clip: people, tools, vehicles, "
    "materials appearing/disappearing in compressed time; the place must physically change step-by-step on screen. "
    "Final seconds may approach ref2; middle of clip must already look clearly in-progress, not identical to ref1. "
)

# Единый базовый стиль видео (импортируется Mode 7 generator и Mode 8 pipeline).
VIDEO_STYLE_HYPERLAPSE_BASE = (
    " Cinematic photorealistic 4K vertical 9:16, locked tripod camera. "
    "MANDATORY: HYPERLAPSE / TIME-LAPSE—compressed elapsed time, motion blur OK, crowds or crews constantly moving, "
    "carrying tools and debris, scaffolding going up, paint strokes, bags filling—humans and machines drive every change. "
)
