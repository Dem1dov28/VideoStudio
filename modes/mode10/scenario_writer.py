"""
Mode 10 Scenario Writer — Beach cleanup timelapse.

Последовательные стадии: грязный пляж → сбор мусора → грабли/просев → вывоз → чистый пляж.
Та же структура сцен, что у mode8 (дом), но процесс — уборка, а не стройка.
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════════════
# ТИП ПЛЯЖА (аналог стиля дома)
# ═══════════════════════════════════════════════════════════════════════════

BEACH_TYPES: dict[str, dict[str, Any]] = {
    "tropical": {
        "name": "тропический пляж",
        "name_en": "tropical beach",
        "visual": "белый коралловый песок, пальмы по краю, бирюзовая вода",
        "debris": "пластиковые бутылки, одноразовая посуда, верёвки, пенопласт",
    },
    "urban": {
        "name": "городской пляж",
        "name_en": "urban city beach",
        "visual": "песок у набережной, городской силуэт вдали, пирс или волнорез",
        "debris": "упаковки, жестяные банки, окурки, пакеты, обломки",
    },
    "rocky_cove": {
        "name": "скалистая бухта",
        "name_en": "rocky cove",
        "visual": "песок и галька, валуны по краям, низкие скалы, ламинария",
        "debris": "рыбацкие сети, пластик среди камней, бутылки в расщелинах",
    },
    "resort": {
        "name": "курортный пляж",
        "name_en": "resort beach",
        "visual": "ровный песок, зонтики вдали, дорожки из досок, лежаки",
        "debris": "полотенца, одноразовые стаканы, надувные игрушки, упаковки",
    },
    "wild": {
        "name": "дикий пляж",
        "name_en": "wild natural beach",
        "visual": "естественный берег, дюны с травой, без застройки",
        "debris": "морской мусор, бутылки, большие пластиковые объекты, верёвки",
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# ОБСТАНОВКА БЕРЕГА (аналог локации дома)
# ═══════════════════════════════════════════════════════════════════════════

COAST_SETTINGS: dict[str, dict[str, Any]] = {
    "morning_calm": {
        "name": "утренний штиль",
        "name_en": "calm morning",
        "visual": "мягкий утренний свет, ровное море, длинные тени",
        "background": "спокойный горизонт, бледное небо, редкие облака",
    },
    "midday_bright": {
        "name": "яркий полдень",
        "name_en": "bright midday",
        "visual": "яркое солнце, короткие тени, насыщенное голубое небо",
        "background": "блики на воде, чёткий горизонт",
    },
    "golden_hour": {
        "name": "золотой час",
        "name_en": "golden hour",
        "visual": "тёплый золотистый свет, длинные тени по песку",
        "background": "закатные оттенки на воде, мягкое небо",
    },
    "overcast_soft": {
        "name": "пасмурно, мягкий свет",
        "name_en": "overcast soft light",
        "visual": "равномерный диффузный свет без жёстких теней",
        "background": "серовато-голубое небо, спокойное море",
    },
    "breezy": {
        "name": "ветреный день",
        "name_en": "breezy day",
        "visual": "лёгкие волны, кромка пены, движение травы на дюнах",
        "background": "белые барашки на воде, динамичное небо",
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# СТАДИИ УБОРКИ
# ═══════════════════════════════════════════════════════════════════════════

CLEANUP_STAGES: dict[str, dict[str, Any]] = {
    "heavily_littered": {
        "name": "сильно загрязнённый пляж",
        "name_en": "heavily littered beach",
        "visual": "песок усеян пластиком, пакетами, бутылками; мусор по всей полосе прибоя",
        "start_state": "пляж завален бытовым и морским мусором",
        "end_state": "мусор всё ещё много, но зоны сбора намечены",
        "action": "объём мусора виден целиком, волонтёры готовятся",
        "workers": "несколько человек в жилетах расставляют мешки и маркеры зон",
        "workers_en": "volunteers in vests placing bags and zone markers",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["мешок раскладывают на песке", "указывают на кучу пластика"],
        "micro_actions_en": ["bag laid on sand", "pointing at plastic pile"],
        "build_intensity": "low",
        "time_of_day": "morning",
        "is_peak_moment": False,
        "next": "volunteers_collecting",
    },
    "volunteers_collecting": {
        "name": "сбор в мешки",
        "name_en": "picking up into bags",
        "visual": "люди нагибаются, наполняют чёрные мешки, тачки с мусором",
        "start_state": "мусор разбросан",
        "end_state": "ряды заполненных мешков, заметно меньше мелочи на песке",
        "action": "ручной сбор крупного и среднего мусора",
        "workers": "волонтёры с хватками и перчатками, дети с родителями в отдалении",
        "workers_en": "volunteers with grabbers and gloves filling trash bags",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["бутылка в мешок", "тачка отъезжает с полной загрузкой"],
        "micro_actions_en": ["bottle into bag", "wheelbarrow rolls away full"],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "raking_sifting",
    },
    "raking_sifting": {
        "name": "грабли и просев песка",
        "name_en": "raking and sifting sand",
        "visual": "грабли собирают мелочь, сито отсеивает песок, остаётся микропластик",
        "start_state": "крупный мусор убран, осталась мелочь",
        "end_state": "песок заметно чище, кучи отсеянного мусора сбоку",
        "action": "просев и грабли по полосам пляжа",
        "workers": "волонтёры в ряд двигаются граблями, кто-то с ситом на штативе",
        "workers_en": "volunteers in a line raking, one sifting through mesh",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["грабли чертят параллельные линии", "сито трясут"],
        "micro_actions_en": ["rakes draw parallel lines", "sieve shaken"],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "machinery_pass",
    },
    "sorting_piles": {
        "name": "временная сортировка",
        "name_en": "sorting area",
        "visual": "ряды мешков по категориям, волонтёры перекладывают пластик и стекло отдельно",
        "start_state": "мешки свалены вместе",
        "end_state": "организованные кучи по типам отходов",
        "action": "сортировка собранного перед вывозом",
        "workers": "люди переносят мешки, маркируют зоны",
        "workers_en": "volunteers moving bags, labeling zones",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["мешок перетаскивают на другую стопку"],
        "micro_actions_en": ["bag dragged to another pile"],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "machinery_pass",
    },
    "machinery_pass": {
        "name": "техника убирает кучи",
        "name_en": "machinery clearing piles",
        "visual": "мини-погрузчик или трактор с ковшом вывозит скопления мешков с пляжа",
        "start_state": "мешки и кучи у дорожки",
        "end_state": "пляжная полоса без крупных куч, техника уезжает",
        "action": "механизированный вывоз собранного мусора",
        "workers": "водитель в кабине, сигнальщик жестами",
        "workers_en": "driver in cab, spotter guiding",
        "machinery": "мини-погрузчик поднимает паллету с мешками, грузовик на пирсе",
        "machinery_en": "compact loader lifting pallet of bags, truck near access path",
        "micro_actions": ["ковш поднимает мешки", "пыль от колёс на мокром песке"],
        "micro_actions_en": ["bucket lifts bags", "tire dust on wet sand"],
        "build_intensity": "high",
        "time_of_day": "afternoon",
        "is_peak_moment": True,
        "next": "waterline_cleanup",
    },
    "waterline_cleanup": {
        "name": "линия прибоя",
        "name_en": "waterline cleanup",
        "visual": "узкая полоса у кромки волны — собирают пену, мелкий пластик, палочки",
        "start_state": "у воды осталась мелочь",
        "end_state": "полоса прибоя визуально чистая",
        "action": "уборка вдоль кромки волны",
        "workers": "люди с корзинами вдоль береговой линии",
        "workers_en": "people with baskets along the shoreline",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["волна откатывает, человек подбирает предмет"],
        "micro_actions_en": ["wave recedes, person picks item"],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "final_sweep",
    },
    "final_sweep": {
        "name": "финальный проход",
        "name_en": "final sweep",
        "visual": "последний проход с граблями и ручными корзинами, почти чистая полоса",
        "start_state": "редкий мусор, следы колёс",
        "end_state": "ровный чистый песок, без заметного мусора",
        "action": "детальная доводка перед «идеалом»",
        "workers": "2–3 человека с корзинами и граблями",
        "workers_en": "small team with baskets and rakes",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["последний пакет в корзину", "грабли сглаживают полосу"],
        "micro_actions_en": ["last bag in basket", "rakes smooth strip"],
        "build_intensity": "low",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "pristine_beach",
    },
    "pristine_beach": {
        "name": "чистый пляж",
        "name_en": "pristine clean beach",
        "visual": "ровный золотистый песок без мусора, чистая кромка прибоя, приглашающий вид",
        "start_state": "почти чисто",
        "end_state": "идеально для купания и отдыха",
        "action": "финальный кадр — результат уборки",
        "workers": "далёкие силуэты уходят с пляжа, пляж пуст",
        "workers_en": "distant figures leaving, beach empty",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": ["волны накатывают на чистый песок"],
        "micro_actions_en": ["waves washing clean sand"],
        "build_intensity": "low",
        "time_of_day": "golden_hour",
        "is_peak_moment": False,
        "next": None,
    },
}

DEFAULT_STAGE_SEQUENCE = [
    "heavily_littered",
    "volunteers_collecting",
    "raking_sifting",
    "machinery_pass",
    "pristine_beach",
]

EXTENDED_STAGE_SEQUENCE = [
    "heavily_littered",
    "volunteers_collecting",
    "raking_sifting",
    "machinery_pass",
    "final_sweep",
    "pristine_beach",
]

FULL_STAGE_SEQUENCE = [
    "heavily_littered",
    "volunteers_collecting",
    "raking_sifting",
    "sorting_piles",
    "machinery_pass",
    "waterline_cleanup",
    "final_sweep",
    "pristine_beach",
]


class CleanupStage(BaseModel):
    index: int
    stage_key: str
    name: str
    name_en: str
    start_state: str
    end_state: str
    visual_prompt: str
    action: str
    duration: int = 6
    workers: str | None = None
    workers_en: str | None = None
    machinery: str | None = None
    machinery_en: str | None = None
    micro_actions: list[str] = []
    micro_actions_en: list[str] = []
    build_intensity: str = "medium"
    time_of_day: str = "midday"
    is_peak_moment: bool = False


class CleanupScenario(BaseModel):
    title: str
    title_en: str
    beach_type: str
    beach_type_name: str
    location: str
    location_name: str
    stages: list[CleanupStage]
    total_duration: int = 0


def select_beach_type(preferred: str | None = None) -> str:
    if preferred and preferred in BEACH_TYPES:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(BEACH_TYPES.keys()))
    return "tropical"


def select_coast_setting(preferred: str | None = None) -> str:
    if preferred and preferred in COAST_SETTINGS:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(COAST_SETTINGS.keys()))
    return "morning_calm"


def get_stage_sequence(num_stages: int) -> list[str]:
    num_stages = max(5, min(8, num_stages))
    if num_stages <= 5:
        return DEFAULT_STAGE_SEQUENCE[:num_stages]
    if num_stages == 6:
        return EXTENDED_STAGE_SEQUENCE[:num_stages]
    return FULL_STAGE_SEQUENCE[:num_stages]


def build_visual_prompt(
    stage_key: str,
    beach_type: str,
    coast: str,
    language: str = "ru",
) -> str:
    stage = CLEANUP_STAGES.get(stage_key)
    bt = BEACH_TYPES.get(beach_type, BEACH_TYPES["tropical"])
    cs = COAST_SETTINGS.get(coast, COAST_SETTINGS["morning_calm"])
    if not stage:
        return ""

    workers = stage.get("workers")
    workers_en = stage.get("workers_en")
    machinery = stage.get("machinery")
    machinery_en = stage.get("machinery_en")

    if language == "en":
        parts = [
            f"{stage['name_en'].capitalize()} stage. {stage['visual']}.",
            f"Beach type: {bt['name_en']} — {bt['visual']}. Typical debris: {bt['debris']}.",
            f"Coast mood: {cs['name_en']} — {cs['visual']}. Background: {cs['background']}.",
        ]
        if workers_en:
            parts.append(f"People: {workers_en}.")
        if machinery_en:
            parts.append(f"Equipment: {machinery_en}.")
        return " ".join(parts)

    parts = [
        f"Стадия: {stage['name']}. {stage['visual']}.",
        f"Тип пляжа: {bt['name']} — {bt['visual']}. Характерный мусор: {bt['debris']}.",
        f"Освещение и атмосфера: {cs['name']} — {cs['visual']}. Фон: {cs['background']}.",
    ]
    if workers:
        parts.append(f"Люди: {workers}.")
    if machinery:
        parts.append(f"Техника: {machinery}.")
    return " ".join(parts)


def generate_cleanup_scenario(
    beach_type: str | None = None,
    coast_setting: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
) -> CleanupScenario:
    bt_key = select_beach_type(beach_type)
    cs_key = select_coast_setting(coast_setting)
    bt = BEACH_TYPES[bt_key]
    cs = COAST_SETTINGS[cs_key]
    num_stages = max(5, min(8, num_stages))
    stage_keys = get_stage_sequence(num_stages)

    stages: list[CleanupStage] = []
    total_duration = 0
    for i, sk in enumerate(stage_keys):
        sd = CLEANUP_STAGES[sk]
        vp = build_visual_prompt(sk, bt_key, cs_key, language)
        stages.append(
            CleanupStage(
                index=i,
                stage_key=sk,
                name=sd["name"],
                name_en=sd["name_en"],
                start_state=sd["start_state"],
                end_state=sd["end_state"],
                visual_prompt=vp,
                action=sd["action"],
                duration=6,
                workers=sd.get("workers"),
                workers_en=sd.get("workers_en"),
                machinery=sd.get("machinery"),
                machinery_en=sd.get("machinery_en"),
                micro_actions=sd.get("micro_actions", []),
                micro_actions_en=sd.get("micro_actions_en", []),
                build_intensity=sd.get("build_intensity", "medium"),
                time_of_day=sd.get("time_of_day", "midday"),
                is_peak_moment=sd.get("is_peak_moment", False),
            )
        )
        total_duration += 6

    if language == "en":
        title = f"Timelapse: Cleaning a {bt['name_en']}"
        title_en = title
    else:
        title = f"Таймлапс: Уборка {bt['name']}"
        title_en = f"Timelapse: Cleaning a {bt['name_en']}"

    scenario = CleanupScenario(
        title=title,
        title_en=title_en,
        beach_type=bt_key,
        beach_type_name=bt["name"],
        location=cs_key,
        location_name=cs["name"],
        stages=stages,
        total_duration=total_duration,
    )
    logger.success(
        f"[Mode10 Scenario] {title} | {len(stages)} стадий | {bt['name']} | {cs['name']}"
    )
    return scenario


async def run_mode10_scenario_writer(
    beach_type: str | None = None,
    coast_setting: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint

    await checkpoint(control)
    scenario = generate_cleanup_scenario(
        beach_type=beach_type,
        coast_setting=coast_setting,
        num_stages=num_stages,
        language=language,
    )
    return {
        "title": scenario.title,
        "title_en": scenario.title_en,
        "beach_type": scenario.beach_type,
        "beach_type_name": scenario.beach_type_name,
        "location": scenario.location,
        "location_name": scenario.location_name,
        "scenes": [
            {
                "index": s.index,
                "stage_key": s.stage_key,
                "name": s.name,
                "name_en": s.name_en,
                "start_state": s.start_state,
                "end_state": s.end_state,
                "visual_prompt": s.visual_prompt,
                "action": s.action,
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
