"""
Mode 8 Scenario Writer — House Building Timelapse.

Generates sequential building stages for timelapse video.
Each stage represents a transformation from state A to state B.
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════════════
# HOUSE STYLES
# ═══════════════════════════════════════════════════════════════════════════

HOUSE_STYLES: dict[str, dict[str, Any]] = {
    # 🏙️ СОВРЕМЕННЫЕ
    "modern": {
        "name": "современный дом",
        "name_en": "modern house",
        "visual": "современный минималистичный дом, плоская крыша, большие окна, геометрические формы, бетон и стекло",
        "materials": "бетон, стекло, металл, дерево",
    },
    "contemporary": {
        "name": "контемпорари",
        "name_en": "contemporary",
        "visual": "ультрасовременный дом, панорамные окна, смешанные материалы, асимметричная форма",
        "materials": "сталь, стекло, бетон, композиты",
    },
    "minimalist": {
        "name": "минимализм",
        "name_en": "minimalist",
        "visual": "дом в стиле минимализм, чистые линии, монохромная палитра, скрытые элементы",
        "materials": "бетон, стекло, алюминий",
    },
    "scandinavian": {
        "name": "скандинавский дом",
        "name_en": "scandinavian house",
        "visual": "скандинавский дом, светлые фасады, деревянные акценты, большие окна",
        "materials": "дерево, камень, стекло",
    },
    # 🏡 ТРАДИЦИОННЫЕ
    "cottage": {
        "name": "коттедж",
        "name_en": "cottage",
        "visual": "уютный загородный коттедж, скатная крыша, каменный фасад, деревянные элементы",
        "materials": "кирпич, камень, дерево, черепица",
    },
    "villa": {
        "name": "вилла",
        "name_en": "villa",
        "visual": "роскошная вилла, несколько этажей, террасы, бассейн, элегантная архитектура",
        "materials": "мрамор, штукатурка, стекло, натуральный камень",
    },
    "farmhouse": {
        "name": "фермерский дом",
        "name_en": "farmhouse",
        "visual": "классический фермерский дом, широкая веранда, белый забор, амбар рядом",
        "materials": "дерево, сайдинг, металл",
    },
    "colonial": {
        "name": "колониальный дом",
        "name_en": "colonial house",
        "visual": "колониальный дом, симметричный фасад, колонны, центральная дверь",
        "materials": "кирпич, дерево, черепица",
    },
    "victorian": {
        "name": "викторианский дом",
        "name_en": "victorian house",
        "visual": "викторианский дом, башенки, эркеры, декоративные элементы, яркая окраска",
        "materials": "дерево, кирпич, шифер",
    },
    "mediterranean": {
        "name": "средиземноморский дом",
        "name_en": "mediterranean house",
        "visual": "средиземноморская вилла, красная черепичная крыша, арочные окна, штукатурка",
        "materials": "штукатурка, черепица, камень",
    },
    # 🌲 НАТУРАЛЬНЫЕ
    "cabin": {
        "name": "домик в лесу",
        "name_en": "cabin",
        "visual": "деревянный домик в лесу, бревенчатые стены, уютная веранда, каминная труба",
        "materials": "бревно, дерево, камень",
    },
    "log_house": {
        "name": "бревенчатый дом",
        "name_en": "log house",
        "visual": "большой бревенчатый дом, массивные брёвна, традиционная архитектура",
        "materials": "бревно, камень, металл",
    },
    "chalet": {
        "name": "шале",
        "name_en": "chalet",
        "visual": "альпийское шале, покатая крыша, деревянные балконы, каменный фундамент",
        "materials": "дерево, камень, черепица",
    },
    "adobe": {
        "name": "адобе дом",
        "name_en": "adobe house",
        "visual": "дом из самана, округлые формы, земляные тона, традиционный стиль",
        "materials": "саман, глина, солома",
    },
    # 🏛️ ЭЛИТНЫЕ
    "mansion": {
        "name": "особняк",
        "name_en": "mansion",
        "visual": "огромный особняк, колонны, фонтаны, ландшафтный дизайн",
        "materials": "мрамор, гранит, бронза, стекло",
    },
    "estate": {
        "name": "поместье",
        "name_en": "estate",
        "visual": "родовое поместье, несколько строений, парк, пруд",
        "materials": "кирпич, камень, металл",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LOCATIONS
# ═══════════════════════════════════════════════════════════════════════════

LOCATIONS: dict[str, dict[str, Any]] = {
    # 🏙️ ПРИГОРОДНЫЕ
    "suburbs": {
        "name": "пригород",
        "name_en": "suburbs",
        "visual": "тихий пригородный район, соседние дома видны, асфальтированная улица, деревья",
        "background": "другие дома на заднем плане, заборы, газоны",
    },
    "urban_edge": {
        "name": "городская окраина",
        "name_en": "urban edge",
        "visual": "окраина города, современные здания вдали, шоссе, инфраструктура",
        "background": "городской силуэт, дороги, фонари",
    },
    "planned_community": {
        "name": "запланированный район",
        "name_en": "planned community",
        "visual": "новый жилой район, одинаковые дома, ухоженные газоны, детские площадки",
        "background": "похожие дома, тротуары, уличные фонари",
    },
    # 🌲 ПРИРОДНЫЕ
    "forest": {
        "name": "лес",
        "name_en": "forest",
        "visual": "густой лес, сосны и ели вокруг, поляна перед домом, природный ландшафт",
        "background": "деревья со всех сторон, природная тишина",
    },
    "wooded_area": {
        "name": "лесная зона",
        "name_en": "wooded area",
        "visual": "смешанный лес, лиственные и хвойные деревья, подлесок",
        "background": "разнообразные деревья, кустарники",
    },
    "seaside": {
        "name": "побережье",
        "name_en": "seaside",
        "visual": "побережье моря, песчаный пляж рядом, пальмы, океанский бриз",
        "background": "море на горизонте, пальмы, пляж",
    },
    "lakefront": {
        "name": "озёрный берег",
        "name_en": "lakefront",
        "visual": "берег озера, спокойная вода, причал, лодка",
        "background": "озеро, противоположный берег",
    },
    "riverside": {
        "name": "речной берег",
        "name_en": "riverside",
        "visual": "берег реки, течение воды, камыши, деревья вдоль реки",
        "background": "река, прибрежная растительность",
    },
    "countryside": {
        "name": "сельская местность",
        "name_en": "countryside",
        "visual": "открытое поле, холмы на горизонте, пастбище, трактор вдали",
        "background": "поля, холмы, редкие деревья",
    },
    "farmland": {
        "name": "сельхозугодья",
        "name_en": "farmland",
        "visual": "обработанные поля, ряды культур, сельскохозяйственная техника",
        "background": "поля, фермерские постройки",
    },
    "vineyard": {
        "name": "виноградник",
        "name_en": "vineyard",
        "visual": "ряды виноградных лоз, холмы, средиземноморский климат",
        "background": "виноградники, сельская местность",
    },
    "mountains": {
        "name": "горы",
        "name_en": "mountains",
        "visual": "горный склон, хвойный лес, снежные вершины на горизонте, скалы",
        "background": "горы, хвойный лес, скалы",
    },
    "hillside": {
        "name": "холмистая местность",
        "name_en": "hillside",
        "visual": "склон холма, террасированный участок, панорамный вид",
        "background": "холмы, долины внизу",
    },
    "valley": {
        "name": "долина",
        "name_en": "valley",
        "visual": "зелёная долина, река протекает, деревья, луга",
        "background": "долина, окружённая горами",
    },
    # 🏜️ ЭКЗОТИЧЕСКИЕ
    "desert": {
        "name": "пустыня",
        "name_en": "desert",
        "visual": "песчаная пустыня, дюны, кактусы, яркое солнце",
        "background": "песчаные холмы, редкая растительность",
    },
    "oasis": {
        "name": "оазис",
        "name_en": "oasis",
        "visual": "пустынный оазис, пальмы, источник воды, зелень",
        "background": "пустыня с зелёной зоной",
    },
    "tropical": {
        "name": "тропики",
        "name_en": "tropical",
        "visual": "тропический лес, экзотические растения, влажный климат",
        "background": "джунгли, пальмы",
    },
    "island": {
        "name": "остров",
        "name_en": "island",
        "visual": "небольшой остров, пляж со всех сторон, кокосовые пальмы",
        "background": "океан, другие острова",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# BUILDING STAGES (Sequential Transformations)
# ═══════════════════════════════════════════════════════════════════════════

BUILDING_STAGES: dict[str, dict[str, Any]] = {
    "empty_land": {
        "name": "пустой участок",
        "name_en": "empty land",
        "visual": "пустой земельный участок с травой, деревья на заднем плане, солнечный день",
        "start_state": "нетронутый земельный участок",
        "start_state_en": "untouched land plot",
        "end_state": "пустой участок, готовый к строительству",
        "end_state_en": "empty plot ready for construction",
        "action": "вид участка до начала работ",
        "action_en": "view of the site before start",
        "workers": None,
        "workers_en": None,
        "micro_actions": [],
        "build_intensity": "low",  # low | medium | high
        "time_of_day": "morning",  # morning | midday | afternoon | golden_hour
        "is_peak_moment": False,  # Visually impactful moment
        "next": "land_preparation",
    },
    "land_preparation": {
        "name": "подготовка земли",
        "name_en": "land preparation",
        "visual": "разметка участка, вырытые траншеи, выровненная земля, столбики разметки",
        "start_state": "пустой участок",
        "start_state_en": "empty land plot",
        "end_state": "подготовленная площадка с разметкой",
        "end_state_en": "prepared site with markings",
        "action": "земляные работы и разметка",
        "action_en": "earthworks and site marking",
        "workers": "землекопы копают траншеи, разметчики устанавливают колышки, рабочие ровняют грунт",
        "workers_en": "diggers excavating trenches, surveyors placing stakes, workers leveling ground",
        "machinery": "экскаватор копает, бульдозер выравнивает, грузовик вывозит грунт",
        "machinery_en": "excavator digging, bulldozer leveling, truck hauling soil away",
        "micro_actions": [
            "экскаватор зачерпывает грунт ковшом",
            "рабочий забивает колышек разметки",
            "бульдозер разравнивает землю",
            "грузовик отъезжает с грунтом",
        ],
        "micro_actions_en": [
            "excavator scooping soil with bucket",
            "worker hammering stake into ground",
            "bulldozer spreading earth",
            "truck driving away with soil",
        ],
        "build_intensity": "low",
        "time_of_day": "morning",
        "is_peak_moment": False,
        "next": "foundation",
    },
    "foundation": {
        "name": "фундамент",
        "name_en": "foundation",
        "visual": "залитый бетонный фундамент, арматура торчит, опалубка, серый бетон",
        "start_state": "подготовленная площадка",
        "start_state_en": "prepared site",
        "end_state": "готовый бетонный фундамент",
        "end_state_en": "completed concrete foundation",
        "action": "заливка фундамента бетоном",
        "action_en": "pouring concrete foundation",
        "workers": "бетонщики заливают смесь, арматурщики связывают прутья, рабочие вибрируют бетон",
        "workers_en": "concrete workers pouring mix, rebar fitters tying rods, workers vibrating concrete",
        "machinery": "бетономешалка крутится, бетононасос подаёт смесь, вибратор уплотняет",
        "machinery_en": "concrete mixer rotating, pump delivering mix, vibrator compacting",
        "micro_actions": [
            "бетономешалка выгружает смесь",
            "рабочий направляет лоток",
            "арматурщик вяжет проволоку",
            "вибратор погружается в бетон",
            "опалубка удерживает форму",
        ],
        "micro_actions_en": [
            "mixer pouring concrete",
            "worker guiding the chute",
            "rebar fitter tying wire",
            "vibrator going into wet concrete",
            "formwork holding the shape",
        ],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "walls",
    },
    "walls": {
        "name": "стены",
        "name_en": "walls",
        "visual": "возведённые стены из кирпича или блоков, оконные проёмы без стёкол, крыши нет",
        "start_state": "фундамент",
        "start_state_en": "foundation",
        "end_state": "стены возведены, оконные проёмы",
        "end_state_en": "walls erected with window openings",
        "action": "кладка стен из кирпича/блоков",
        "action_en": "laying brick or block walls",
        "workers": "каменщики кладут кирпич, помощники подносят раствор, крановщик управляет подачей",
        "workers_en": "masons laying bricks, helpers carrying mortar, crane operator controlling delivery",
        "machinery": "кран поднимает поддон с блоками, подъёмник везёт раствор",
        "machinery_en": "crane lifting pallet with blocks, hoist carrying mortar",
        "micro_actions": [
            "каменщик кладёт кирпич на раствор",
            "кран опускает поддон с блоками",
            "помощник разгружает раствор",
            "уровень проверяет вертикаль",
            "строительные леса вдоль стен",
        ],
        "micro_actions_en": [
            "mason placing brick on mortar",
            "crane lowering pallet with blocks",
            "helper unloading mortar",
            "level checking vertical alignment",
            "scaffolding along the walls",
        ],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "roof",
    },
    "roof": {
        "name": "крыша",
        "name_en": "roof",
        "visual": "установленная крыша, стропильная система, черепица или шифер, без отделки фасада",
        "start_state": "стены без крыши",
        "start_state_en": "walls without roof",
        "end_state": "крыша установлена",
        "end_state_en": "roof installed",
        "action": "монтаж крыши и кровли",
        "action_en": "roofing and framework installation",
        "workers": "кровельщики укладывают черепицу, плотники ставят стропила, рабочие на лесах",
        "workers_en": "roofers laying tiles, carpenters installing rafters, workers on scaffolding",
        "machinery": "кран поднимает балки, подъёмник доставляет материалы на крышу",
        "machinery_en": "crane lifting beams, hoist delivering materials to roof",
        "micro_actions": [
            "кран поднимает балку",
            "кровельщик прибивает черепицу",
            "плотник закрепляет стропило",
            "рабочий передаёт материалы",
            "леса вокруг верхнего этажа",
        ],
        "micro_actions_en": [
            "crane lifting beam",
            "roofer nailing tile",
            "carpenter securing rafter",
            "worker passing materials",
            "scaffolding around top floor",
        ],
        "build_intensity": "high",  # PEAK MOMENT - dramatic crane operations
        "time_of_day": "afternoon",
        "is_peak_moment": True,  # This is the visual WOW moment
        "next": "windows_doors",
    },
    "windows_doors": {
        "name": "окна и двери",
        "name_en": "windows and doors",
        "visual": "установленные окна и входная дверь, стёкла блестят, рамы видны",
        "start_state": "стены с проёмами",
        "start_state_en": "walls with openings",
        "end_state": "окна и двери установлены",
        "end_state_en": "windows and doors installed",
        "action": "установка окон и дверей",
        "action_en": "installing windows and doors",
        "workers": "стекольщики вставляют окна, плотники вешают дверь, рабочие герметизируют швы",
        "workers_en": "glaziers installing windows, carpenters hanging door, workers sealing joints",
        "machinery": None,
        "machinery_en": None,
        "micro_actions": [
            "стекольщик вставляет раму в проём",
            "уровень проверяет установку",
            "плотник навешивает дверь",
            "пена заполняет щели",
            "рабочий протирает стёкла",
        ],
        "micro_actions_en": [
            "glazier placing frame in opening",
            "level checking installation",
            "carpenter hanging door",
            "foam filling gaps",
            "worker wiping glass",
        ],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "finishing",
    },
    "finishing": {
        "name": "отделка фасада",
        "name_en": "facade finishing",
        "visual": "отделанный фасад, штукатурка или облицовка, покрашенные стены",
        "start_state": "стены с окнами",
        "start_state_en": "walls with windows",
        "end_state": "фасад полностью отделан",
        "end_state_en": "facade fully finished",
        "action": "внешняя отделка и покраска",
        "action_en": "exterior finishing and painting",
        "workers": "штукатуры наносят слой, маляры красят фасад, облицовщики крепят панели",
        "workers_en": "plasterers applying coat, painters painting facade, cladding installers fixing panels",
        "machinery": "подъёмник поднимает материалы, компрессор распыляет краску",
        "machinery_en": "hoist lifting materials, compressor spraying paint",
        "micro_actions": [
            "штукатур намазывает стену",
            "маляр красит фасад",
            "облицовщик крепит панель",
            "подъёмник поднимает вёдра",
            "леса вдоль всего дома",
        ],
        "micro_actions_en": [
            "plasterer troweling wall",
            "painter coating facade",
            "installer fixing panel",
            "hoist lifting buckets",
            "scaffolding around house",
        ],
        "build_intensity": "high",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "landscaping",
    },
    "landscaping": {
        "name": "благоустройство",
        "name_en": "landscaping",
        "visual": "готовый дом с газоном, дорожки, посаженные кусты и цветы, забор",
        "start_state": "дом с отделкой",
        "start_state_en": "finished house",
        "end_state": "полностью готовый дом с участком",
        "end_state_en": "complete house with landscaped garden",
        "action": "ландшафтный дизайн и благоустройство",
        "action_en": "landscaping and site improvement",
        "workers": "озеленители сажают кусты, дорожники укладывают плитку, рабочие ставят забор",
        "workers_en": "landscapers planting shrubs, pavers laying tiles, workers installing fence",
        "machinery": "газонокосилка стрижёт траву, тачка возит землю",
        "machinery_en": "lawnmower cutting grass, wheelbarrow moving soil",
        "micro_actions": [
            "рабочий сажает куст в яму",
            "дорожник укладывает плитку",
            "тачка везёт грунт",
            "газонокосилка едет по траве",
            "забор устанавливается",
        ],
        "micro_actions_en": [
            "worker planting shrub in hole",
            "paver placing tile",
            "wheelbarrow carrying soil",
            "lawnmower going across grass",
            "fence being installed",
        ],
        "build_intensity": "medium",
        "time_of_day": "golden_hour",  # Beautiful final shot
        "is_peak_moment": False,
        "next": None,
    },
}

# Default stage sequence for 5 stages
DEFAULT_STAGE_SEQUENCE = ["empty_land", "foundation", "walls", "roof", "landscaping"]

# Extended stage sequence for 6 stages
EXTENDED_STAGE_SEQUENCE = ["empty_land", "land_preparation", "foundation", "walls", "roof", "landscaping"]

# Full stage sequence for 8 stages
FULL_STAGE_SEQUENCE = [
    "empty_land",
    "land_preparation",
    "foundation",
    "walls",
    "roof",
    "windows_doors",
    "finishing",
    "landscaping",
]


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class BuildingStage(BaseModel):
    """Single building stage (transformation)."""
    index: int
    stage_key: str
    name: str
    name_en: str
    start_state: str
    start_state_en: str
    end_state: str
    end_state_en: str
    visual_prompt: str
    action: str
    action_en: str
    duration: int = 6
    workers: str | None = None
    workers_en: str | None = None
    machinery: str | None = None
    machinery_en: str | None = None
    micro_actions: list[str] = []
    micro_actions_en: list[str] = []
    build_intensity: str = "medium"  # low | medium | high
    time_of_day: str = "midday"     # morning | midday | afternoon | golden_hour
    is_peak_moment: bool = False     # Visually impactful WOW moment


class BuildingScenario(BaseModel):
    """Complete house building timelapse scenario."""
    title: str
    title_en: str
    house_style: str
    house_style_name: str
    location: str
    location_name: str
    stages: list[BuildingStage]
    total_duration: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def select_house_style(preferred: str | None = None) -> str:
    """Select a house style."""
    if preferred and preferred in HOUSE_STYLES:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(HOUSE_STYLES.keys()))
    return "modern"


def select_location(preferred: str | None = None) -> str:
    """Select a location."""
    if preferred and preferred in LOCATIONS:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(LOCATIONS.keys()))
    return "suburbs"


def get_stage_sequence(num_stages: int) -> list[str]:
    """Get appropriate stage sequence based on number of stages."""
    if num_stages <= 5:
        return DEFAULT_STAGE_SEQUENCE[:num_stages]
    elif num_stages == 6:
        return EXTENDED_STAGE_SEQUENCE[:num_stages]
    else:
        return FULL_STAGE_SEQUENCE[:num_stages]


def build_visual_prompt(
    stage_key: str,
    house_style: str,
    location: str,
) -> str:
    """Build detailed visual prompt for a building stage (ALWAYS in English)."""
    stage = BUILDING_STAGES.get(stage_key)
    style = HOUSE_STYLES.get(house_style, HOUSE_STYLES["modern"])
    loc = LOCATIONS.get(location, LOCATIONS["suburbs"])

    # Get workers and machinery info (always English)
    workers_en = stage.get("workers_en") if stage else None
    machinery_en = stage.get("machinery_en") if stage else None

    result = f"""{stage['name_en'].capitalize()} stage. {stage['visual']}.
House style: {style['name_en']} — {style['visual']}.
Location: {loc['name_en']} — {loc['visual']}.
Materials: {style['materials']}.
Background: {loc['background']}."""
    if workers_en:
        result += f"\nWorkers: {workers_en}."
    if machinery_en:
        result += f"\nMachinery: {machinery_en}."
    return result


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCENARIO GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_building_scenario(
    house_style: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
) -> BuildingScenario:
    """
    Generate a house building timelapse scenario.

    Args:
        house_style: House style key (modern, cottage, villa, cabin, farmhouse)
        location: Location key (suburbs, forest, seaside, countryside, mountains)
        num_stages: Number of stages (5-8)
        language: Output language

    Returns:
        Complete BuildingScenario
    """
    # Select style and location
    style_key = select_house_style(house_style)
    loc_key = select_location(location)

    style = HOUSE_STYLES[style_key]
    loc = LOCATIONS[loc_key]

    # Get stage sequence
    num_stages = max(5, min(8, num_stages))
    stage_keys = get_stage_sequence(num_stages)

    # Build stages
    stages = []
    total_duration = 0

    for i, stage_key in enumerate(stage_keys):
        stage_data = BUILDING_STAGES[stage_key]

        visual_prompt = build_visual_prompt(
            stage_key,
            style_key,
            loc_key,
        )

        stage = BuildingStage(
            index=i,
            stage_key=stage_key,
            name=stage_data["name"],
            name_en=stage_data["name_en"],
            start_state=stage_data["start_state"],
            start_state_en=stage_data["start_state_en"],
            end_state=stage_data["end_state"],
            end_state_en=stage_data["end_state_en"],
            visual_prompt=visual_prompt,
            action=stage_data["action"],
            action_en=stage_data["action_en"],
            duration=6,
            workers=stage_data.get("workers"),
            workers_en=stage_data.get("workers_en"),
            machinery=stage_data.get("machinery"),
            machinery_en=stage_data.get("machinery_en"),
            micro_actions=stage_data.get("micro_actions", []),
            micro_actions_en=stage_data.get("micro_actions_en", []),
            build_intensity=stage_data.get("build_intensity", "medium"),
            time_of_day=stage_data.get("time_of_day", "midday"),
            is_peak_moment=stage_data.get("is_peak_moment", False),
        )
        stages.append(stage)
        total_duration += stage.duration

    # Build title
    if language == "en":
        title = f"Timelapse: Building a {style['name_en']}"
        title_en = title
    else:
        title = f"Timelapse: Строительство {style['name']}"
        title_en = f"Timelapse: Building a {style['name_en']}"

    scenario = BuildingScenario(
        title=title,
        title_en=title_en,
        house_style=style_key,
        house_style_name=style["name"],
        location=loc_key,
        location_name=loc["name"],
        stages=stages,
        total_duration=total_duration,
    )

    logger.success(
        f"[Mode8 Scenario] Generated: {title} | "
        f"{len(stages)} stages | {style['name']} | {loc['name']}"
    )

    return scenario


async def run_mode8_scenario_writer(
    house_style: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Main entry point for Mode 8 scenario generation.

    Args:
        house_style: House style preference
        location: Location preference
        num_stages: Number of building stages (5-8)
        language: Output language
        control: Pipeline control dict

    Returns:
        dict compatible with pipeline
    """
    from pipeline_control import checkpoint

    await checkpoint(control)

    scenario = generate_building_scenario(
        house_style=house_style,
        location=location,
        num_stages=num_stages,
        language=language,
    )

    # Convert to dict for pipeline compatibility
    return {
        "title": scenario.title,
        "title_en": scenario.title_en,
        "house_style": scenario.house_style,
        "house_style_name": scenario.house_style_name,
        "location": scenario.location,
        "location_name": scenario.location_name,
        "scenes": [
            {
                "index": s.index,
                "stage_key": s.stage_key,
                "name": s.name,
                "name_en": s.name_en,
                "start_state": s.start_state,
                "start_state_en": s.start_state_en,
                "end_state": s.end_state,
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
