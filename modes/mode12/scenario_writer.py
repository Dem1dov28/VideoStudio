"""
Mode 12 — сценарий таймлапса «уборка и реставрация комнаты».

5 стадий строго по порядку 1→5; длительность перехода — 8 с; затем отдельно 6-й блок — обзорное видео из последнего кадра (zoom-in).
Стадии 1–4: белые СИЗ (1 — 2–3 чел.; 2 — 3–4; 3 — 2–3; 4 — 2 чел.); стадия 5 — без бригады (опционально 1–2 фигуры хозяина/стилиста в гражданском или пустая сцена).
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel

ROOM_TYPES: dict[str, dict[str, Any]] = {
    "studio": {
        "name": "студия",
        "name_en": "studio apartment",
        "visual": "одна комната, зона сна и кухонный угол, большое окно",
        "visual_en": "one-room layout with sleep zone and small kitchenette, one large window",
    },
    "bedroom": {
        "name": "спальня",
        "name_en": "bedroom",
        "visual": "спальня, кровать, шкаф, окно, тумбочки",
        "visual_en": "bedroom with bed, wardrobe, window, side tables",
    },
    "living": {
        "name": "гостиная",
        "name_en": "living room",
        "visual": "гостиная, диван, журнальный стол, книжные полки",
        "visual_en": "living room with sofa, coffee table, bookshelves",
    },
    "kitchen": {
        "name": "кухня",
        "name_en": "kitchen",
        "visual": "кухня, столешница, шкафы, плита, обеденный угол",
        "visual_en": "kitchen with counter, cabinets, stove area, small dining nook",
    },
    "kids": {
        "name": "детская",
        "name_en": "kids room",
        "visual": "детская: кровать, игрушки, письменный стол, яркие акценты",
        "visual_en": "children's room with bed, toys, desk, bright accents",
    },
    "loft": {
        "name": "лофт",
        "name_en": "loft space",
        "visual": "лофт с кирпичом или бетоном, высокий потолок, открытые коммуникации",
        "visual_en": "loft with brick or concrete accents, tall ceiling, exposed services",
    },
}

ROOM_LIGHTING: dict[str, dict[str, Any]] = {
    "morning_soft": {
        "name": "утренний мягкий свет",
        "name_en": "soft morning light",
        "visual": "низкое солнце из окна, длинные тени, светлые стены",
        "visual_en": "low sun through the window, long shadows, light-toned walls",
    },
    "daylight_neutral": {
        "name": "дневной нейтральный",
        "name_en": "neutral daylight",
        "visual": "равномерный дневной свет из окна, естественные тени",
        "visual_en": "even daylight from the window, natural soft shadows",
    },
    "golden_hour": {
        "name": "золотой час",
        "name_en": "golden hour",
        "visual": "тёплый золотистый свет, длинные тени по полу",
        "visual_en": "warm golden light, long shadows across the floor",
    },
    "warm_lamps": {
        "name": "тёплые лампы",
        "name_en": "warm lamp light",
        "visual": "вечер, торшер и настольная лампа, уютные пятна света",
        "visual_en": "evening, floor and table lamps, cozy pools of light",
    },
    "overcast_soft": {
        "name": "пасмурно, рассеянный свет",
        "name_en": "soft overcast",
        "visual": "мягкий рассеянный свет из окна, без жёстких бликов",
        "visual_en": "soft diffused daylight from the window, no harsh glare",
    },
}

# 5 сцен — полные описания для LLM / генерации кадров (английский prompt_en; RU поля — метаданные/UI)
RESTORATION_STAGES: dict[str, dict[str, Any]] = {
    "dilapidated_room": {
        "name": "Запущенная комната",
        "name_en": "Dilapidated room — dismantling begins",
        "start_state": "полный упадок, грязь, хлам, старая мебель",
        "start_state_en": "full decline; dirt, hoarded junk, old worn furniture still in place",
        "end_state": "бригада начала разбор: первые мешки, снятие лёгкого хлама",
        "end_state_en": "crew has started clearing: first bags, early stripping amid the mess",
        "action": "Начало разбора: 2–3 человека в белых СИЗ",
        "action_en": "Dismantling begins: 2–3 people in white PPE start sorting and tearing out",
        "workers": "2–3 человека в белых защитных комбинезонах, респираторах/масках, перчатках; начинают разбор мусора и демонтаж",
        "workers_en": "2–3 workers in white protective coveralls, masks/respirators, gloves; begin clearing junk and light demolition",
        "tools": "мешки для мусора, ломик, перчатки; ручной инвентарь для первого выноса",
        "tools_en": "trash bags, small pry bar, gloves; handheld tools for first haul-out",
        "micro_actions": [
            "выцветшие обои, плесень, старая мебель в кадре как лом для выноса",
            "грязные окна, паутина, криво висит штора",
            "мешки, кучи хлама, 2–3 рабочих в белых комбинезонах начинают разбор",
        ],
        "micro_actions_en": [
            "faded wallpaper, mold, derelict old furniture in frame as removal targets",
            "dirty cobwebbed windows, crooked curtain",
            "trash bags, heavy clutter, 2-3 workers in white PPE starting dismantling",
        ],
        "build_intensity": "low",
        "time_of_day": "morning",
        "is_peak_moment": False,
        "prompt_en": """Scene 1 — Dilapidated room: dirt, junk, OLD FURNITURE, cobwebs, dull wallpaper; 2–3 workers in white PPE BEGIN dismantling
State: Heavy neglect — hoarding-scale junk — NOT lightly messy. 2–3 workers in WHITE coveralls, masks/respirators, gloves are ON SITE starting clearance: lifting bags, pulling debris, beginning tear-down amid trash. Active poses — not standing idle.

Walls: Faded dull wallpaper; peeling; mold; cracks; cobwebs at ceiling corners.

Floor: Trash heaps, torn bags, bottles, cardboard, fabric; OLD worn furniture (per room type) still in frame as items to remove; narrow paths.

Stuff: Extreme clutter + derelict furniture; crew hands-on with junk and surfaces.

Windows: Dirty, cobwebs; crooked curtain; WINDOW FRAME geometry LOCKED for the whole series.

Lighting: Dim bare bulb; dusty air; deep shadows.

Details: Wiring stains, ceiling flakes. Generic non-identifiable faces. No children or crowd bystanders. Animals are usually absent here; if one appears, allow only a brief peripheral pass-by of one cat OR one small dog near the doorway.
Key feeling: Shocking “before”; renovation has JUST started with a small crew.""",
    },
    "clearance_prep": {
        "name": "Освобождение и подготовка",
        "name_en": "Clearance and renovation prep",
        "start_state": "голые стены после сноса отделки, пустая комната",
        "start_state_en": "bare walls after stripping finishes; room emptied for renovation",
        "end_state": "подготовлено к черновой отделке, мешки у входа",
        "end_state_en": "ready for rough finishing; debris bags by the door; materials staged",
        "action": "Демонтаж и вынос: 3–4 человека в белой форме",
        "action_en": "Demolition and haul-out; 3–4 workers in white protective suits",
        "workers": "3–4 человека в белых комбинезонах и СИЗ: выносят мешки, сдирают покрытия, метут, работают у стен и потолка",
        "workers_en": "3–4 workers in white PPE: hauling bags, stripping finishes, sweeping, working at walls and ceiling line",
        "tools": "мешки со строительным мусором у входа, рулоны материалов у стен",
        "tools_en": "construction debris bags at doorway, rolls of materials along walls",
        "micro_actions": [
            "обои сняты, шпаклёвка и следы клея на стенах",
            "черновая стяжка или бетон пола, подметено",
            "временная яркая лампа на проводе",
            "иногда у дверного проёма на заднем плане мимо проходит кот или небольшая собака",
        ],
        "micro_actions_en": [
            "stripped walls, filler and glue residue",
            "exposed screed or concrete floor, swept",
            "bright temporary work light on cord",
            "occasionally one cat or one small dog passes in the background near the doorway",
        ],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "prompt_en": """Scene 2 — Clearance and preparation.
State: Stripped shell forming. 3–4 workers in white PPE — continuous hauling, stripping, sweeping; debris in BAGS; exposed walls, demolished/stripped floor.
Walls: Wallpaper fully removed; bare walls with filler and glue traces; large cracks patched.
Floor: Old flooring stripped; exposed rough screed (or concrete slab), swept clean.
Furniture: All old furniture removed; room empty.
Windows: Frames washed, glass clean, curtains taken down.
Lighting: Temporary work lamp on a cord; bright practical light.
Details: Bagged construction debris by the door; rolls of new materials along walls. OPTIONAL: one cat or one small dog may pass near the doorway or along the far wall, peripheral only.
Key feeling: Clean after demolition; ready for rough finishing.""",
    },
    "rough_finish": {
        "name": "Черновая отделка",
        "name_en": "Rough construction finish",
        "start_state": "серое безликое помещение после стяжки и шпаклёвки",
        "start_state_en": "gray faceless shell after screed and plaster passes",
        "end_state": "ровные загрунтованные стены, новые окна, проводка под свет",
        "end_state_en": "flat primed walls, new windows, wiring roughed in for lighting",
        "action": "Черновая отделка: 2–3 человека с правилами, вёдрами, инструментом",
        "action_en": "Rough finishing: plaster, screed, new windows, wires — 2–3 workers with straightedges, buckets, tools",
        "workers": "2–3 человека в белых комбинезонах и СИЗ: штукатурка, стяжка, монтаж окон, проводка",
        "workers_en": "2–3 workers in white PPE: plastering, screed passes, window install, electrical rough-in",
        "tools": "правила, вёдра, миксеры, шпатели; стремянка при необходимости",
        "tools_en": "straightedges, buckets, mixers, trowels; stepladder as needed",
        "micro_actions": [
            "стены выровнены и загрунтованы",
            "новая ровная стяжка или черновой пол",
            "новые стеклопакеты, оштукатуренные откосы",
            "торчат провода для светильников",
            "редко по краю кадра может пройти кот или небольшая собака",
        ],
        "micro_actions_en": [
            "walls leveled and primed",
            "new flat screed or subfloor",
            "new double-glazed windows, plastered reveals",
            "wires sticking out for future fixtures",
            "rarely a cat or a small dog may pass by at the edge of frame",
        ],
        "build_intensity": "high",
        "time_of_day": "afternoon",
        "is_peak_moment": True,
        "prompt_en": """Scene 3 — Rough finish (2–3 crew with tools: rules, buckets)
State: Base construction; gray shell ready for finishes — visible plaster/screed work, NEW windows roughed in, wires for lighting.

Walls: Leveled with plaster, primed; ready for paint or wallpaper.

Floor: New screed poured (or rough subfloor laid), perfectly flat.

Furniture: None; built-in elements may exist (e.g. drywall box for curtains).

Windows: New double-glazed units; jambs plastered.

Lighting: New wiring run; wires sticking out for fixtures.

Details: Rollers, buckets, scaffolding removed; room clean but gray and faceless. OPTIONAL: one cat or one small dog may cross the edge of frame, staying secondary to the renovation work.
Key feeling: Clean, flat surfaces; no color or decor yet.""",
    },
    "finish_furniture": {
        "name": "Финиш и основная мебель",
        "name_en": "Final finishes and main furniture",
        "start_state": "серое помещение без мебели",
        "start_state_en": "gray unfurnished shell",
        "end_state": "светлые стены/обои, финишный пол, ключевая мебель без декора",
        "end_state_en": "light walls or wallpaper, finished floor, key furniture without decor",
        "action": "Финиш и мебель: 2 монтажника в белой защитной форме",
        "action_en": "Finishes and furniture: 2 installers in white protective suits",
        "workers": "2 человека в белых комбинезонах: расстановка дивана, шкафа, покраска/обои, ламинат, навеска светильников",
        "workers_en": "2 workers in white suits: place sofa, wardrobe, paint/wallpaper, laminate floor, install ceiling lights",
        "tools": None,
        "tools_en": None,
        "micro_actions": [
            "светлые нейтральные стены или новые обои",
            "ламинат, паркет или ковролин",
            "основные светильники смонтированы",
            "нет картин, растений, лишнего декора",
            "иногда кот или небольшая собака спокойно проходит у стены или возле двери",
        ],
        "micro_actions_en": [
            "light neutral paint or new wallpaper",
            "laminate, wood floor, or carpet",
            "main ceiling lights installed",
            "no art, plants, or accessories yet",
            "occasionally a cat or a small dog calmly walks along the wall or near the doorway",
        ],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "prompt_en": """Scene 4 — Final finishes and main furniture (2 workers)
State: Two workers in white PPE finishing paint/wallpaper, laminate, placing sofa and wardrobe, mounting lights.

Walls: Painted a light neutral (e.g. beige or light gray) or new wallpaper.

Floor: Finished flooring — laminate, parquet, or carpet.

Furniture: Key pieces installed — sofa, bed, wardrobe, or table (per room type). All new, no decor layer.

Windows: New curtains (blinds or classic), clean sill.

Lighting: Main fixtures installed (ceiling, possibly recessed).

Details: No accessories, art, or plants; functional but still sterile. OPTIONAL: one cat or one small dog can calmly pass through the background near the wall or doorway.
Key feeling: Color and furniture, but no personal touch yet.""",
    },
    "full_restoration_cozy": {
        "name": "Полная реставрация: уют и стиль",
        "name_en": "Full restoration: cozy styled room",
        "start_state": "функциональная стерильная комната",
        "start_state_en": "functional but still sterile room",
        "end_state": "гармония, стиль, идеальная чистота и уют",
        "end_state_en": "harmony, style, immaculate cleanliness and coziness",
        "action": "Финальный уют и декор; ремонтной бригады в кадре нет",
        "action_en": "Final cozy decor and styling; no PPE crew in frame",
        "workers": None,
        "workers_en": None,
        "tools": None,
        "tools_en": None,
        "micro_actions": [
            "картины, зеркала, акценты на стенах",
            "ковёр, пуфы, подушки, пледы",
            "бра, торшер, LED-подсветка",
            "растения в горшках, вазы, свечи",
            "иногда по краю кадра спокойно проходит кот или небольшая собака",
        ],
        "micro_actions_en": [
            "art, mirrors, wall accents",
            "rug, soft seating, throws and pillows",
            "wall sconces, floor lamp, LED accent lighting",
            "potted plants, vases, candles",
            "occasionally a cat or a small dog calmly passes at the edge of frame",
        ],
        "build_intensity": "low",
        "time_of_day": "golden_hour",
        "is_peak_moment": False,
        "prompt_en": """Scene 5 — Full restoration: coziness and style — NO PPE crew
State: Fully styled: rugs, CURTAINS, pillows, framed art, plants, floor lamps, layered light. NO workers in coveralls.

People: Prefer VACANT hero shot. OPTIONAL: at most one or two generic figures (homeowner or stylist in casual clothes), non-identifiable — OR zero people.

Walls: Art, mirrors, accents.

Floor: Rugs, poufs, soft layers.

Furniture: Styling complete — coffee table, textiles.

Windows: Curtains or shades fully dressed.

Lighting: Sconces, floor lamp, LED accents.

Details: Plants, vases, candles. NO white PPE, NO construction crew. OPTIONAL: one calm cat or one small dog may pass by along the edge of frame or near the doorway.
Key feeling: Warm finished interior; showcase.""",
    },
}

STAGE_ORDER = [
    "dilapidated_room",
    "clearance_prep",
    "rough_finish",
    "finish_furniture",
    "full_restoration_cozy",
]


class RoomStage(BaseModel):
    index: int
    stage_key: str
    name: str
    name_en: str
    start_state: str
    end_state: str
    start_state_en: str
    end_state_en: str
    visual_prompt: str
    action: str
    action_en: str
    duration: int = 8
    workers: str | None = None
    workers_en: str | None = None
    machinery: str | None = None
    machinery_en: str | None = None
    micro_actions: list[str] = []
    micro_actions_en: list[str] = []
    build_intensity: str = "medium"
    time_of_day: str = "midday"
    is_peak_moment: bool = False


class RoomScenario(BaseModel):
    title: str
    title_en: str
    room_type: str
    room_type_name: str
    room_lighting: str
    room_lighting_name: str
    stages: list[RoomStage]
    total_duration: int = 0


def select_room_type(preferred: str | None) -> str:
    if preferred and preferred in ROOM_TYPES:
        return preferred
    if preferred in (None, "random"):
        return random.choice(list(ROOM_TYPES.keys()))
    return "studio"


def select_room_lighting(preferred: str | None) -> str:
    if preferred and preferred in ROOM_LIGHTING:
        return preferred
    if preferred in (None, "random"):
        return random.choice(list(ROOM_LIGHTING.keys()))
    return "morning_soft"


def build_visual_prompt(
    stage_key: str,
    room_type: str,
    lighting: str,
) -> str:
    """Full English scene text for the image model + room type + window daylight mood."""
    st = RESTORATION_STAGES.get(stage_key)
    rt = ROOM_TYPES.get(room_type, ROOM_TYPES["studio"])
    lg = ROOM_LIGHTING.get(lighting, ROOM_LIGHTING["morning_soft"])
    if not st:
        return ""

    base = st["prompt_en"]
    workers_en = st.get("workers_en")
    tools_en = st.get("tools_en")

    lines: list[str] = []
    if workers_en:
        lines.append(f"People (generic, no identifiable faces): {workers_en}.")
    if tools_en:
        lines.append(f"Props: {tools_en}.")
    lines.append(
        f"Room program (keep furniture choices consistent across stages 4–5): "
        f"{rt['name_en']} — {rt['visual_en']}."
    )
    lines.append(
        f"If daylight enters through the window, you may blend this outdoor mood: "
        f"{lg['name_en']} — {lg['visual_en']}."
    )
    return base + "\n\n" + "\n".join(lines)


def generate_room_scenario(
    room_type: str | None = None,
    room_lighting: str | None = None,
) -> RoomScenario:
    rt_key = select_room_type(room_type)
    lg_key = select_room_lighting(room_lighting)
    rt = ROOM_TYPES[rt_key]
    lg = ROOM_LIGHTING[lg_key]

    stages: list[RoomStage] = []
    total_duration = 0
    for i, sk in enumerate(STAGE_ORDER):
        sd = RESTORATION_STAGES[sk]
        vp = build_visual_prompt(sk, rt_key, lg_key)
        stages.append(
            RoomStage(
                index=i,
                stage_key=sk,
                name=sd["name"],
                name_en=sd["name_en"],
                start_state=sd["start_state"],
                end_state=sd["end_state"],
                start_state_en=sd["start_state_en"],
                end_state_en=sd["end_state_en"],
                visual_prompt=vp,
                action=sd["action"],
                action_en=sd["action_en"],
                duration=8,
                workers=sd.get("workers"),
                workers_en=sd.get("workers_en"),
                machinery=sd.get("tools"),
                machinery_en=sd.get("tools_en"),
                micro_actions=sd.get("micro_actions", []),
                micro_actions_en=sd.get("micro_actions_en", []),
                build_intensity=sd.get("build_intensity", "medium"),
                time_of_day=sd.get("time_of_day", "midday"),
                is_peak_moment=sd.get("is_peak_moment", False),
            )
        )
        total_duration += 8

    title = f"Timelapse: Restoring a {rt['name_en']}"
    title_en = title

    scenario = RoomScenario(
        title=title,
        title_en=title_en,
        room_type=rt_key,
        room_type_name=rt["name"],
        room_lighting=lg_key,
        room_lighting_name=lg["name"],
        stages=stages,
        total_duration=total_duration,
    )
    logger.success(
        f"[Mode12 Scenario] {title} | 5 стадий | {rt['name']} | {lg['name']}"
    )
    return scenario


async def run_mode12_scenario_writer(
    room_type: str | None = None,
    room_lighting: str | None = None,
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint

    await checkpoint(control)
    scenario = generate_room_scenario(
        room_type=room_type,
        room_lighting=room_lighting,
    )
    return {
        "title": scenario.title,
        "title_en": scenario.title_en,
        "room_type": scenario.room_type,
        "room_type_name": scenario.room_type_name,
        "room_lighting": scenario.room_lighting,
        "room_lighting_name": scenario.room_lighting_name,
        "scenes": [
            {
                "index": s.index,
                "stage_key": s.stage_key,
                "name": s.name,
                "name_en": s.name_en,
                "start_state": s.start_state,
                "end_state": s.end_state,
                "start_state_en": s.start_state_en,
                "end_state_en": s.end_state_en,
                "visual_prompt": s.visual_prompt,
                "action": s.action,
                "action_en": s.action_en,
                "duration": s.duration,
                "workers": s.workers,
                "workers_en": s.workers_en,
                "machinery": s.machinery,
                "machinery_en": s.machinery_en,
                "micro_actions": s.micro_actions,
                "micro_actions_en": s.micro_actions_en,
                "build_intensity": s.build_intensity,
                "time_of_day": s.time_of_day,
                "is_peak_moment": s.is_peak_moment,
            }
            for s in scenario.stages
        ],
        "total_duration": scenario.total_duration,
    }
