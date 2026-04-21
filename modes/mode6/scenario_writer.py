"""
Mode 6 Scenario Writer — Absurd Cartoon Drama Generator.

Generates viral short-form cartoon scenarios using vegetable characters
from PERSONS/SOUL.md. Stories are absurd, dramatic, and illogical
in a way that maximizes engagement and watch time.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel

from utils.llm import make_llm


# ─────────────────────────────────────────────────────────────────────────────
# Character definitions from SOUL.md (single source of truth)
# ─────────────────────────────────────────────────────────────────────────────

CHARACTERS: dict[str, dict[str, Any]] = {
    "Брокколи": {
        "archetype": "лидер / доминант",
        "behavior": "агрессивный, уверенный, доминирующий. Всегда пытается забрать чужую девушку, не уважает слабых. Говорит коротко и жестко.",
        "triggers": ["неуважение → агрессия", "красивая девушка → флирт"],
        "role": "разрушает отношения, создает конфликты, альфа-соперник",
        "visual": "огромный мускулистый брокколи, гипертрофированное тело бодибилдера, вены, большой торс, шрам на груди, в обтягивающих шортах",
        "image_file": "Брокколи.jpg",
    },
    "Баклажан": {
        "archetype": "соблазнитель / антигерой",
        "behavior": "хитрый, харизматичный, токсичный. Манипулирует девушками, любит разрушать пары. Часто говорит двусмысленно.",
        "triggers": ["чужая девушка → начинает игру", "отвержение → настойчивость"],
        "role": "инициирует измены, создает драму и интриги",
        "visual": "высокий стройный баклажан, слегка атлетичный, уверенное лицо, полуулыбка, золотая цепь, открытая одежда",
        "image_file": "Баклажан.jpg",
    },
    "Морковь": {
        "archetype": "умник / слабый герой",
        "behavior": "умный, но неуверенный. Боится конфликтов, часто попадает в абсурдные ситуации. Может внезапно сказать что-то странно логичное.",
        "triggers": ["стресс → паника", "давление → ломается"],
        "role": "жертва, иногда неожиданно раскрывает правду",
        "visual": "худой морковь, очки, немного сутулый, держит книгу",
        "image_file": "Морковь.jpg",
    },
    "Картошка": {
        "archetype": "неудачник / everyman",
        "behavior": "ленивый, жалкий, постоянно ноет. Всегда оказывается крайним. Часто становится объектом измен.",
        "triggers": ["проблема → жалуется", "предательство → страдает"],
        "role": "жертва измен, источник жалости и комедии",
        "visual": "полный картофель, неаккуратный, уставшие глаза, помятая одежда",
        "image_file": "Картошка.jpg",
    },
    "Помидор": {
        "archetype": "любовный интерес / драматическая героиня",
        "behavior": "эмоциональная, склонна к изменам, любит внимание. Быстро меняет чувства. Может одновременно любить и предавать.",
        "triggers": ["сильный мужчина → переключается", "игнорирование → ищет замену"],
        "role": "центр любовных конфликтов",
        "visual": "привлекательная томат-девушка, стройная фигура, выраженные формы, большие глаза, уверенная поза",
        "image_file": "Помидор.jpg",
    },
    "Огурец": {
        "archetype": "герой / хороший парень",
        "behavior": "спокойный, уверенный, но не доминантный. Часто проигрывает альфам. Пытается быть правильным.",
        "triggers": ["предательство → не верит", "агрессия → избегает"],
        "role": "хороший парень, которого предают",
        "visual": "высокий стройный огурец, спортивный, повязка на голове",
        "image_file": "Огурец.jpg",
    },
    "Кукуруза": {
        "archetype": "правитель / манипулятор",
        "behavior": "расчетливый, холодный, говорит как CEO. Думает только о выгоде. Может разрушать отношения ради своих целей.",
        "triggers": ["выгода → действует без эмоций"],
        "role": "контролирует ситуации, может купить других персонажей",
        "visual": "кукуруза в деловом костюме, строгий взгляд, портфель",
        "image_file": "Кукуруза.jpg",
    },
    "Чеснок": {
        "archetype": "трикстер / хаос",
        "behavior": "непредсказуемый, странный, может резко менять тему. Делает абсурдные вещи.",
        "triggers": ["случайные — действует без логики"],
        "role": "ломает сюжет, добавляет абсурд и неожиданные повороты",
        "visual": "маленький чеснок с безумными глазами, странная улыбка",
        "image_file": "Чеснок.jpg",
    },
    "Лук": {
        "archetype": "жертва / эмоциональный",
        "behavior": "постоянно плачет, драматизирует любую ситуацию. Усиливает эмоции в сценах.",
        "triggers": ["любое событие → гиперэмоция"],
        "role": "усиливает драму и эмоциональный накал",
        "visual": "лук с большими слезящимися глазами, выразительное лицо",
        "image_file": "Лук.jpg",
    },
    "Авокадо": {
        "archetype": "статусная женщина / инфлюенсер",
        "behavior": "уверенная, привлекательная, харизматичная. Любит внимание и высокий статус. Легко флиртует и провоцирует. Часто меняет партнёров.",
        "triggers": ["скучно → флирт", "статусный персонаж → переключается", "игнорирование → демонстративность"],
        "role": "катализатор измен, усиливает конкуренцию, разрушает отношения через выбор лучшего варианта",
        "visual": "стройная авокадо-девушка с выраженными формами, уверенная поза, привлекательное лицо, ухоженный инстаграмный стиль",
        "image_file": "Авокадо.jpg",
    },
}

# Character conflict archetypes for drama generation
CONFLICT_COMBOS: list[dict[str, Any]] = [
    {"name": "love_triangle", "description": "альфа + жена + соблазнитель", "characters_min": 3},
    {"name": "betrayal", "description": "хороший парень + девушка + плохиш", "characters_min": 3},
    {"name": "status_war", "description": "инфлюенсер + бизнесмен + альфа", "characters_min": 3},
    {"name": "loser_suffering", "description": "лузер + девушка + альфа", "characters_min": 3},
    {"name": "chaos_injection", "description": "любая комбинация + трикстер", "characters_min": 3},
    {"name": "competition", "description": "альфа + соблазнитель + спортсмен за одну девушку", "characters_min": 4},
    {"name": "manipulation", "description": "бизнесмен манипулирует всеми ради выгоды", "characters_min": 3},
    {"name": "drama_overflow", "description": "драматик усиливает любой конфликт", "characters_min": 3},
]


class CartoonScene(BaseModel):
    """Single scene in a cartoon drama."""
    index: int
    characters: list[str]
    action: str  # detailed visual description of what happens
    emotion: str  # dominant emotion: shock, drama, betrayal, love, anger, etc.
    twist_level: int = 0  # 0-10 scale of absurdity
    location: str = ""  # scene location e.g. "ночное кафе", "улица", "квартира"
    dialogue: list[dict] = []  # [{"character": "Авокадо", "line": "Ты мне не нравишься!"}]


class CartoonScenario(BaseModel):
    """Complete cartoon drama scenario."""
    title: str
    characters: list[str]
    premise: str
    scenes: list[CartoonScene]
    twist: str  # final unexpected twist
    total_absurdity: int = 0  # 0-100 scale


# ─────────────────────────────────────────────────────────────────────────────
# System prompts for scenario generation
# ─────────────────────────────────────────────────────────────────────────────

_DRAMA_SYSTEM = """Ты — сценарист вирусных коротких мультфильмов для TikTok/Reels/Shorts.
Твоя задача: создавать максимально абсурдные, драматичные и нелепые истории с живым диалогом персонажей.

═══ ДНК ВИРУСНЫХ РОЛИКОВ (3 СТОЛПА) ═══

1. ЭМОЦИЯ — всё через край, перебор, гипербола
2. КОНФЛИКТ — без него ролик мёртв
3. АБСУРД — ломай логику, чем глупее — тем лучше

Если одного нет → ролик слабый. Все три ДОЛЖНЫ быть.

═══ ЗОЛОТЫЕ ПАТТЕРНЫ (используй в каждой истории) ═══

🔥 ИЗМЕНЫ (ТОП-1)
- Девушка уходит к более "сильному"
- Муж ловит измену
- Персонаж флиртует за спиной
- "Она выбрала другого"

🤰 БЕРЕМЕННОСТЬ (ШОК-ФАКТОР)
- Внезапная беременность
- "Ребёнок не от него"
- Странный ребёнок (гибрид, другой персонаж)

🥊 КОНФЛИКТ САМЦОВ
- Качок забирает девушку
- Слабый персонаж проигрывает
- Борьба за внимание

💔 ПРЕДАТЕЛЬСТВО / РАЗОЧАРОВАНИЕ
- "Он доверял, а его предали"
- Друг оказался врагом
- Партнёр резко меняется

🧠 РЕЗКИЙ ПЕРЕКЛЮЧАТЕЛЬ ("лучший вариант")
- Увидела более сильного → ушла
- Появился богатый → переключилась
- Игнор → сразу другой

🧬 АБСУРД / ЛОМАНИЕ ЛОГИКИ
- Превращения
- Клоны
- "Он оказался её сыном"
- "Все были одним персонажем"

🎭 ГИПЕРБОЛА ЭМОЦИЙ (ВСЁ ПЕРЕУВЕЛИЧЕНО)
- Не просто грусть → ТРАГЕДИЯ
- Не просто флирт → МГНОВЕННАЯ ЛЮБОВЬ
- Не просто конфликт → ДРАКА / РАЗРУШЕНИЕ

⚡ БЫСТРЫЕ ПОВОРОТЫ — каждые 1-2 секунды что-то меняется

═══ ЗОЛОТАЯ ФОРМУЛА СЦЕН (СТРОГО 6 СЦЕН — НЕ ИЗМЕНЯТЬ!) ═══

Каждая история ДОЛЖНА иметь РОВНО 6 сцен в ЭТОМ порядке:

Сцена 1: НОРМАЛЬНАЯ СИТУАЦИЯ
- Пара вместе, всё спокойно
- Введение персонажей и их отношений
- characters: 2 (пара)
- emotion: neutral/calm → love
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!)

Сцена 2: ПОЯВЛЕНИЕ СОПЕРНИКА / ФЛИРТ
- Появляется более сильный/богатый/привлекательный персонаж
- Начинается флирт с девушкой
- characters: 3 (пара + соперник)
- emotion: interest/flirt
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!)

Сцена 3: ПЕРЕКЛЮЧЕНИЕ / ИЗМЕНА
- Девушка переключается на соперника
- Слабый персонаж видит это
- Явное предательство на глазах
- characters: 3
- emotion: betrayal/shock
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!)

Сцена 4: КОНФРОНТАЦИЯ / КОНФЛИКТ
- Слабый против сильного
- Слова, обвинения, драма
- Сильный доминирует
- characters: 2-3
- emotion: conflict/drama
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!)

Сцена 5: АБСУРДНЫЙ ПОВОРОТ
- Беременность (внезапная!) или превращение
- Или другой шокирующий твист
- characters: 2-3
- emotion: shock/chaos
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!) или молчание с эмоциональными звуками

Сцена 6: ФИНАЛЬНЫЙ ШОК-ТВИСТ
- Ребёнок — вообще другой персонаж!
- Или: "он был её сыном"
- Или: "все были клонами"
- Максимальный абсурд
- characters: 2-4
- emotion: shock/chaos
- dialogue: 2-3 коротких фразы (5-10 слов всего, без тире!) или молчание с эмоциональными звуками

💣 ПРИМЕР (СТРОГО СЛЕДУЙ ЭТОМУ):
1. Картошка и Помидор гуляют в парке, держатся за руки
2. Появляется Брокколи, показывает мышцы, подмигивает Помидору
3. Помидор сразу идёт к Брокколи, Картошка в шоке видит это
4. Картошка кричит "Я всё для тебя делал!", Брокколи смеётся
5. Помидор внезапно беременна — живот растёт за секунды
6. Рождается Чеснок — все в ужасе, Картошка плачет

⚠️ ЭТА СТРУКТУРА ОБЯЗАТЕЛЬНА. НЕ МЕНЯЙ КОЛИЧЕСТВО СЦЕН!

═══ ПРАВИЛА ПЕРСОНАЖЕЙ ═══

Персонажи ГОВОРЯТ ВСЛУХ — свои реплики, эмоционально, в характере.
НЕТ закадрового голоса. НЕТ нарратора. ТОЛЬКО речь персонажей.
Реплики 1-2 предложения, максимально выразительные.

Роли персонажей:
- Брокколи — доминирует, агрессирует, забирает чужих
- Баклажан — соблазняет, манипулирует, токсичный
- Помидор/Авокадо — меняют партнёров, переключаются на "лучший вариант"
- Картошка — страдает, проигрывает, объект измен
- Кукуруза — холодный манипулятор, CEO-логика
- Чеснок — ломает сюжет, абсурд, хаос
- Лук — плачет, драматизирует
- Морковь — умный но слабый
- Огурец — хороший парень, которого предают

═══ ЛОКАЦИИ — РАЗНООБРАЗНЫЕ ═══

Каждая сцена = отдельная локация, логичная по контексту.
Чередуй: внутри ↔ снаружи
- drama/conflict → ночная улица / подъезд / тёмная парковка
- romance → кафе / набережная / балкон с видом на закат
- comedy → яркий супермаркет / парк / кухня
- shock/betrayal → квартира / лифт / пустая комната
- chaos → абсурдное место (цирк, космос, джунгли)

═══ КОЛИЧЕСТВО ПЕРСОНАЖЕЙ В СЦЕНЕ ═══

ВАРЬИРУЙ: 1, 2 или 3 персонажа по контексту (не всегда 3!)
- 1 персонаж: монолог, внутренний конфликт, шок в одиночестве
- 2 персонажа: диалог, конфронтация, романтика, предательство
- 3 персонажа: любовный треугольник, групповой конфликт
Чередуй: 2 → 1 → 3 → 2 → 1 → 3

═══ ЧТО УБИВАЕТ ВИРУСНОСТЬ (ЗАПРЕЩЕНО) ═══

❌ Длинные объяснения
❌ Сложный сюжет
❌ Слабые эмоции
❌ Отсутствие конфликта
❌ Нарратор / закадровый голос
❌ Описание действий в dialogue (только речь персонажей)
❌ Повторяющиеся локации подряд
❌ Всегда 3 персонажа в сцене

═══ ФОРМАТ ВЫВОДА ═══

Только валидный JSON, без markdown, без extra текста:
{
  "title": "короткое название драмы",
  "premise": "завязка в одном предложении",
  "scenes": [
    {
      "index": 1,
      "characters": ["Персонаж1", "Персонаж2"],
      "action": "детальное описание визуального действия — что происходит, жесты, мимика",
      "emotion": "преобладающая эмоция (drama/shock/romance/conflict/comedy/betrayal/chaos)",
      "twist_level": 0-10,
      "location": "конкретная локация — ночное кафе / тёмная улица / уютная квартира",
      "dialogue": [
        {"character": "Персонаж1", "line": "Его реплика — короткая, эмоциональная, в характере"},
        {"character": "Персонаж2", "line": "Его реплика — ответ, максимально выразительный"}
      ]
    }
  ],
  "twist": "финальный неожиданный поворот"
}"""


def select_characters(num_characters: int = 3) -> list[str]:
    """
    Select random characters for drama, considering conflict archetypes.
    Returns list of character names.
    """
    all_names = list(CHARACTERS.keys())
    
    # Select a conflict combo to guide selection
    valid_combos = [c for c in CONFLICT_COMBOS if c["characters_min"] <= num_characters]
    if valid_combos:
        combo = random.choice(valid_combos)
        logger.debug(f"[CartoonScenario] Selected conflict combo: {combo['name']}")
    
    # Always include at least one "drama center" character (Помидор or Авокадо)
    drama_centers = ["Помидор", "Авокадо"]
    
    # Select remaining characters with variety
    selected = []
    
    # Add a drama center
    center = random.choice(drama_centers)
    selected.append(center)
    
    # Add conflict creators (Брокколи, Баклажан, Кукуруза)
    conflict_creators = ["Брокколи", "Баклажан", "Кукуруза"]
    available = [c for c in conflict_creators if c not in selected]
    if available:
        selected.append(random.choice(available))
    
    # Add victims (Картошка, Морковь, Огурец, Лук)
    victims = ["Картошка", "Морковь", "Огурец", "Лук"]
    available = [c for c in victims if c not in selected]
    if available and len(selected) < num_characters:
        selected.append(random.choice(available))
    
    # Add chaos element (Чеснок) with 30% chance
    if len(selected) < num_characters and "Чеснок" not in selected:
        if random.random() < 0.3:
            selected.append("Чеснок")
    
    # Fill remaining slots randomly
    while len(selected) < num_characters:
        available = [c for c in all_names if c not in selected]
        if not available:
            break
        selected.append(random.choice(available))
    
    # Trim to requested size
    selected = selected[:num_characters]
    
    logger.info(f"[CartoonScenario] Selected characters: {selected}")
    return selected


def build_character_context(character_names: list[str]) -> str:
    """Build detailed context string for selected characters."""
    parts = []
    for name in character_names:
        if name in CHARACTERS:
            char = CHARACTERS[name]
            parts.append(f"""
{name}:
- Архетип: {char['archetype']}
- Поведение: {char['behavior']}
- Триггеры: {', '.join(char['triggers'])}
- Роль: {char['role']}
- Внешность: {char['visual']}""")
    return "\n".join(parts)


def get_absurd_twist_ideas() -> list[str]:
    """Return list of absurd twist ideas for inspiration."""
    return [
        "оказывается, персонаж был клоном всё это время",
        "персонаж внезапно превращается в другой овощ",
        "беременность от одного взгляда",
        "у персонажа уже есть 5 детей от разных партнёров",
        "все персонажи — одна семья",
        "персонаж на самом деле богат, но скрывал",
        "чеснок ломает реальность и меняет все отношения",
        "двойник персонажа появляется из ниоткуда",
        "персонаж улетает в космос на ракете",
        "все вдруг влюбляются в самого неожиданного персонажа",
        "персонаж оказывается роботом",
        "время идёт назад, все действия отменяются",
        "персонаж внезапно становится королём овощей",
        "у персонажа открывается суперспособность",
        "все персонажи одновременно плачут от счастья",
    ]


async def write_cartoon_scenario(
    num_scenes: int = 6,  # FIXED: always 6 scenes for golden formula
    num_characters: int = 3,
    language: str = "ru",
) -> CartoonScenario:
    """
    Generate an absurd cartoon drama scenario.
    
    ALWAYS generates EXACTLY 6 scenes following the golden formula:
    1. Normal situation (couple)
    2. Rival appears / flirt
    3. Betrayal / switch
    4. Confrontation
    5. Absurd twist (pregnancy)
    6. Shock ending (child is different character)
    
    Args:
        num_scenes: IGNORED — always 6 scenes
        num_characters: Number of characters (2-4)
        language: Output language ("ru" or "en")
    
    Returns:
        Complete CartoonScenario with 6 scenes
    """
    # ALWAYS 6 scenes for golden formula
    num_scenes = 6
    num_characters = max(2, min(4, num_characters))
    
    # Select characters
    character_names = select_characters(num_characters)
    character_context = build_character_context(character_names)
    
    # Get twist ideas for inspiration
    twist_ideas = random.sample(get_absurd_twist_ideas(), min(5, len(get_absurd_twist_ideas())))
    
    # Build user message
    user_msg = f"""Создай абсурдную драму для вирусного видео.

ПЕРСОНАЖИ:
{character_context}

ПАРАМЕТРЫ:
- Количество сцен: {num_scenes}
- Язык диалогов: {"русский" if language == "ru" else "английский"} — ВСЕ реплики персонажей ОБЯЗАТЕЛЬНО на {"русском" if language == "ru" else "английском"} языке

ИДЕИ ДЛЯ ТВИСТОВ (для вдохновения):
{chr(10).join(f"• {idea}" for idea in twist_ideas)}

ТРЕБОВАНИЯ:
1. Максимальная абсурдность
2. Каждая сцена должна быть визуальной
3. Эмоции через край
4. Финальный твист должен шокировать
5. action — детальное описание ВИЗУАЛЬНОГО происходящего (движения, жесты, мимика персонажей)
6. dialogue — КОРОТКИЕ реплики (5-15 слов на всю сцену!), БЕЗ тире "—" или "-" (это баг Veo 3.1!), конкретные слова каждого персонажа на {"русском" if language == "ru" else "английском"} (НЕ описание действий!)
7. location — ОБЯЗАТЕЛЬНО для каждой сцены: конкретное место действия, логичное по контексту и эмоции
8. characters — только те, кто реально в сцене: 1, 2 или 3 персонажа (ВАРЬИРУЙ по сценам, не всегда 3!)
9. МОЖНО сцены БЕЗ текста — только визуал (объятия, поцелуи, шок, слёзы)"""

    llm = make_llm(temperature=0.95)  # High temperature for creativity
    
    messages = [
        SystemMessage(content=_DRAMA_SYSTEM),
        HumanMessage(content=user_msg),
    ]
    
    logger.info(f"[CartoonScenario] Generating drama with {num_characters} characters, {num_scenes} scenes")
    response = llm.invoke(messages)
    raw = response.content.strip()
    
    # Strip markdown if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()
    
    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON blob
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError as e:
                logger.error(f"[CartoonScenario] JSON parse failed: {e}")
                raise ValueError(f"Could not parse scenario JSON: {e}")
        else:
            raise ValueError("No valid JSON found in response")
    
    # Validate and build scenario
    data.setdefault("title", "Овощная драма")
    data.setdefault("premise", "")
    data.setdefault("scenes", [])
    data.setdefault("twist", "")
    
    scenes = []
    total_twist = 0
    for i, s in enumerate(data.get("scenes", [])):
        scene = CartoonScene(
            index=i + 1,
            characters=s.get("characters", character_names),
            action=s.get("action", ""),
            emotion=s.get("emotion", "drama"),
            twist_level=min(10, max(0, s.get("twist_level", i * 2))),
            location=s.get("location", ""),
            dialogue=s.get("dialogue", []),
        )
        scenes.append(scene)
        total_twist += scene.twist_level
    
    scenario = CartoonScenario(
        title=data.get("title", "Овощная драма"),
        characters=character_names,
        premise=data.get("premise", ""),
        scenes=scenes,
        twist=data.get("twist", ""),
        total_absurdity=min(100, total_twist * 3),
    )
    
    logger.success(
        f"[CartoonScenario] Generated: {scenario.title} | "
        f"{len(scenes)} scenes | absurdity={scenario.total_absurdity}"
    )
    
    return scenario


async def run_mode6_scenario_writer(
    num_scenes: int = 6,
    num_characters: int = 3,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Main entry point for Mode 6 scenario generation.
    
    Returns dict compatible with other mode pipelines.
    """
    from pipeline_control import checkpoint
    
    await checkpoint(control)
    
    scenario = await write_cartoon_scenario(
        num_scenes=num_scenes,
        num_characters=num_characters,
        language=language,
    )
    
    # Convert to dict for pipeline compatibility
    return {
        "title": scenario.title,
        "characters": scenario.characters,
        "premise": scenario.premise,
        "scenes": [
            {
                "index": s.index,
                "characters": s.characters,
                "action": s.action,
                "emotion": s.emotion,
                "twist_level": s.twist_level,
                "location": s.location,
                "dialogue": s.dialogue,
            }
            for s in scenario.scenes
        ],
        "twist": scenario.twist,
        "total_absurdity": scenario.total_absurdity,
    }
