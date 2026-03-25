"""
Mode 7 Scenario Writer — ASMR Animal Keyboard Video Generator.

Generates ASMR videos featuring animals interacting with different
"keyboard" surfaces in a single video. Focus on high-quality ASMR sounds.

NO VOICE! NO SUBTITLES! ONLY ASMR SOUNDS!
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════════════
# ANIMAL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

ANIMALS: dict[str, dict[str, Any]] = {
    "cat": {
        "name": "кот",
        "name_en": "cat",
        "visual": "реалистичный пушистый кот, мягкая шерсть, выразительные глаза, детализированные лапы с розовыми подушечками",
        "paw_action": "мягко нажимает подушечками лап",
    },
    "dog": {
        "name": "собака",
        "name_en": "dog",
        "visual": "реалистичная собака, шерсть средней длины, дружелюбная морда, детализированные лапы",
        "paw_action": "энергично давит лапами",
    },
    "kitten": {
        "name": "котёнок",
        "name_en": "kitten",
        "visual": "маленький пушистый котёнок, большие глаза, крошечные лапки с маленькими подушечками",
        "paw_action": "игриво тыкает маленькими лапками",
    },
    "puppy": {
        "name": "щенок",
        "name_en": "puppy",
        "visual": "маленький щенок, пушистая шерсть, большие неуклюжие лапы",
        "paw_action": "неуклюже топает большими лапами",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# KEYBOARD / SURFACE DEFINITIONS — EACH IS A "KEY" TYPE
# ═══════════════════════════════════════════════════════════════════════════

KEYBOARDS: dict[str, dict[str, Any]] = {
    # Sticky surfaces
    "honey": {
        "name": "медовая клавиатура",
        "category": "sticky",
        "visual": "золотистая медовая поверхность с повторяющимися выпуклостями-клавишами, тянется нитями, блестит",
        "key_shape": "круглые выпуклые клавиши из густого мёда",
        "press_reaction": "медленно продавливается, тянется за лапой, образует золотистые нити",
        "release_reaction": "медленно возвращается, оставляя липкий след",
        "asmr_sound": "тягучий липкий звук: глухой 'чмок' при нажатии, тягучее 'мммяу' при отпускании, сладкий и густой",
        "key_count": "8-12 клавиш",
    },
    "caramel": {
        "name": "карамельная клавиатура",
        "category": "sticky",
        "visual": "янтарная карамельная поверхность с квадратными клавишами, глянцевая, полупрозрачная",
        "key_shape": "квадратные упругие клавиши из карамели",
        "press_reaction": "продавливается и тянется, оставляет глубокие вмятины",
        "release_reaction": "медленно поднимается, клейкая поверхность",
        "asmr_sound": "липкий карамельный звук: упругое 'клац' при нажатии, тягучее 'ппрумм' при отпускании",
        "key_count": "9 клавиш (3x3)",
    },
    # Soft surfaces
    "jelly": {
        "name": "желейная клавиатура",
        "category": "soft",
        "visual": "полупрозрачная желейная клавиатура с дрожащими клавишами, разноцветная, колышется",
        "key_shape": "дрожащие полупрозрачные клавиши, светятся изнутри",
        "press_reaction": "дрожит и продавливается, волны расходятся по поверхности",
        "release_reaction": "упруго поднимается с лёгкой вибрацией",
        "asmr_sound": "хлюпающий звук: мягкое 'бульк' при нажатии, упругое 'прыынг' при отпускании, влажный",
        "key_count": "12 клавиш (4x3)",
    },
    "slime": {
        "name": "слизевая клавиатура",
        "category": "soft",
        "visual": "неоновая слизь с выпуклыми клавишами, тянется, пульсирует",
        "key_shape": "круглые выпуклые клавиши из слизи, светятся",
        "press_reaction": "глубоко проваливается, слизь обволакивает лапу",
        "release_reaction": "медленно восстанавливается, оставляя след",
        "asmr_sound": "хлюпающий вязкий звук: глубокое 'хлёп' при нажатии, тягучее 'чвууп' при отпускании, влажный",
        "key_count": "8 клавиш (2x4)",
    },
    "marshmallow": {
        "name": "маршмеллоу клавиатура",
        "category": "soft",
        "visual": "белые пушистые квадратные клавиши-маршмеллоу, мягкие, воздушные",
        "key_shape": "квадратные белые клавиши, пористые и мягкие",
        "press_reaction": "плавно продавливается, очень мягкая",
        "release_reaction": "медленно поднимается, пружинит",
        "asmr_sound": "воздушный мягкий звук: глухое 'пуфф' при нажатии, тихое 'ффууп' при отпускании, губчатый",
        "key_count": "9 клавиш (3x3)",
    },
    # Crunchy surfaces
    "ice": {
        "name": "ледяная клавиатура",
        "category": "crunchy",
        "visual": "прозрачная ледяная клавиатура с трещинами, холодная, зеркальная",
        "key_shape": "кристаллические клавиши из льда с трещинками",
        "press_reaction": "трескается, осколки разлетаются, образуются трещины",
        "release_reaction": "частично осыпается, остаются сколы",
        "asmr_sound": "хрустящий ледяной звук: звонкое 'кракх' при нажатии, хрустящее 'кррр' при отпускании, звонкий",
        "key_count": "6 крупных клавиш",
    },
    "chocolate": {
        "name": "шоколадная клавиатура",
        "category": "crunchy",
        "visual": "тёмная шоколадная клавиатура, матовая, с рельефными клавишами",
        "key_shape": "квадратные плитки шоколада с насечками",
        "press_reaction": "ломается с хрустом, кусочки откалываются",
        "release_reaction": "остаётся вмятина, крошки",
        "asmr_sound": "хрустящий шоколадный звук: сухое 'крак' при нажатии, крошащийся 'хрр' при отпускании",
        "key_count": "12 плиток (4x3)",
    },
    # Edible surfaces
    "cheese": {
        "name": "сырная клавиатура",
        "category": "edible",
        "visual": "жёлтая сырная клавиатура с дырочками, мягкая, пористая",
        "key_shape": "круглые клавиши из сыра с дырочками",
        "press_reaction": "продавливается, остаются следы от лап",
        "release_reaction": "медленно поднимается, отпечаток остаётся",
        "asmr_sound": "мягкий сырный звук: глухое 'ммф' при нажатии, мягкое 'ппу' при отпускании, пористый",
        "key_count": "9 клавиш (3x3)",
    },
    "cake": {
        "name": "тортовая клавиатура",
        "category": "edible",
        "visual": "яркий торт-клавиатура с кремом, воздушный, разноцветный",
        "key_shape": "квадратные кусочки торта с кремом сверху",
        "press_reaction": "проваливается в мякиш, крем размазывается",
        "release_reaction": "остаётся глубокий след, крем на лапе",
        "asmr_sound": "влажный губчатый звук: мягкое 'фвумп' при нажатии, кремовое 'чмок' при отпускании",
        "key_count": "6 крупных кусочков",
    },
    # Fantasy surfaces
    "liquid_metal": {
        "name": "металлическая клавиатура",
        "category": "fantasy",
        "visual": "серебристая жидкометаллическая клавиатура, зеркальная, футуристичная",
        "key_shape": "каплевидные клавиши из жидкого металла, отражают свет",
        "press_reaction": "растекается под лапой, образует волны",
        "release_reaction": "мгновенно восстанавливает форму, зеркальная",
        "asmr_sound": "металлический звук: звонкое 'дзинг' при нажатии, жидкое 'вшшш' при отпускании, футуристичный",
        "key_count": "8 клавиш",
    },
    "glowing_goo": {
        "name": "светящаяся клавиатура",
        "category": "fantasy",
        "visual": "неоновая светящаяся клавиатура, пульсирует, флуоресцентная",
        "key_shape": "светящиеся клавиши, пульсируют при нажатии",
        "press_reaction": "вспыхивает ярче при касании, волны света",
        "release_reaction": "медленно затухает до прежней яркости",
        "asmr_sound": "электрический звук: электрическое 'зззт' при нажатии, затухающее 'ввумм' при отпускании, неоновый",
        "key_count": "8 клавиш",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# SCENE STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class KeyboardSegment(BaseModel):
    """Single keyboard segment in the video."""
    index: int
    keyboard: str  # keyboard type key
    press_count: int  # number of key presses (2-4)
    description: str  # visual description of action
    asmr_description: str  # ASMR sound description


class AnimalASMRScenario(BaseModel):
    """Complete ASMR animal keyboard video scenario."""
    title: str
    animal: str
    keyboards: list[str]  # list of keyboard types
    segments: list[KeyboardSegment]
    total_duration: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def select_animal(preferred: str | None = None) -> str:
    """Select an animal type."""
    if preferred and preferred in ANIMALS:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(ANIMALS.keys()))
    return "cat"


def validate_keyboards(keyboards: list[str]) -> list[str]:
    """Validate and return keyboards list."""
    valid = []
    for kb in keyboards:
        if kb in KEYBOARDS:
            valid.append(kb)
    if not valid:
        # Default keyboards if none valid
        valid = random.sample(list(KEYBOARDS.keys()), min(3, len(KEYBOARDS)))
    return valid


def build_segment_description(
    animal_key: str,
    keyboard_key: str,
    press_count: int,
) -> str:
    """Build visual description for a segment."""
    animal = ANIMALS.get(animal_key, ANIMALS["cat"])
    keyboard = KEYBOARDS.get(keyboard_key, KEYBOARDS["honey"])
    
    return f"""{animal['visual']} {animal['paw_action']} по {keyboard['key_shape']}.
Поверхность: {keyboard['visual']}.
Животное нажимает {press_count} клавиши подряд.
При нажатии: {keyboard['press_reaction']}.
При отпускании: {keyboard['release_reaction']}."""


def build_asmr_description(keyboard_key: str, press_count: int) -> str:
    """Build ASMR sound description for a segment."""
    keyboard = KEYBOARDS.get(keyboard_key, KEYBOARDS["honey"])
    
    sounds = []
    for i in range(press_count):
        sounds.append(f"Нажатие {i+1}: {keyboard['asmr_sound']}")
    
    return "\n".join(sounds)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCENARIO GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_asmr_scenario(
    keyboards: list[str],
    animal_type: str | None = None,
) -> AnimalASMRScenario:
    """
    Generate an ASMR animal keyboard video scenario.
    
    Args:
        keyboards: List of keyboard types to include (3-4)
        animal_type: Animal type or "random"
    
    Returns:
        Complete AnimalASMRScenario
    """
    # Validate keyboards
    keyboards = validate_keyboards(keyboards)
    keyboards = keyboards[:4]  # Max 4 keyboards
    
    # Select animal
    animal_key = select_animal(animal_type)
    
    # Build segments
    segments = []
    total_duration = 0
    
    for i, kb_key in enumerate(keyboards):
        press_count = random.randint(2, 4)  # 2-4 presses per keyboard
        
        segment = KeyboardSegment(
            index=i + 1,
            keyboard=kb_key,
            press_count=press_count,
            description=build_segment_description(animal_key, kb_key, press_count),
            asmr_description=build_asmr_description(kb_key, press_count),
        )
        segments.append(segment)
        
        # Duration: ~6-10 seconds per segment
        duration = 6 + press_count * 2
        total_duration += duration
    
    animal = ANIMALS[animal_key]
    keyboard_names = [KEYBOARDS[kb]["name"] for kb in keyboards]
    
    title = f"ASMR: {animal['name'].capitalize()} на {', '.join(keyboard_names)}"
    
    scenario = AnimalASMRScenario(
        title=title,
        animal=animal_key,
        keyboards=keyboards,
        segments=segments,
        total_duration=total_duration,
    )
    
    logger.success(
        f"[ASMR Scenario] Generated: {title} | "
        f"{len(segments)} keyboards | {total_duration}s"
    )
    
    return scenario


async def run_mode7_scenario_writer(
    keyboards: list[str] | None = None,
    animal_type: str | None = None,
    num_keyboards: int = 3,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Main entry point for Mode 7 scenario generation.
    
    Args:
        keyboards: List of keyboard types (if None, random selection)
        animal_type: Animal preference
        num_keyboards: Number of keyboards if random selection
        language: Output language (not used, kept for compatibility)
        control: Pipeline control dict
    
    Returns:
        dict compatible with pipeline
    """
    from pipeline_control import checkpoint
    
    await checkpoint(control)
    
    # If no keyboards provided, select random ones
    if not keyboards:
        keyboards = random.sample(list(KEYBOARDS.keys()), min(num_keyboards, len(KEYBOARDS)))
    
    scenario = generate_asmr_scenario(
        keyboards=keyboards,
        animal_type=animal_type,
    )
    
    # Convert to dict for pipeline compatibility
    return {
        "title": scenario.title,
        "animal": scenario.animal,
        "keyboards": scenario.keyboards,
        "scenes": [
            {
                "index": s.index,
                "keyboard": s.keyboard,
                "press_count": s.press_count,
                "description": s.description,
                "asmr_description": s.asmr_description,
                "duration": 6 + s.press_count * 2,
            }
            for s in scenario.segments
        ],
        "total_duration": scenario.total_duration,
    }
