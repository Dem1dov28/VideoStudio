"""
Mode 8 — Architectural Variations Generator.

Этот модуль использует LLM для генерации разнообразных архитектурных вариаций,
чтобы каждое видео было уникальным даже при одинаковом базовом стиле.

Вместо фиксированных шаблонов, LLM генерирует:
- Уникальные архитектурные детали для каждого стиля дома
- Вариативные кровельные решения (разные типы крыш)
- Разнообразные фасадные материалы и отделку
- Уникальные элементы для каждой локации
- Детализированные визуальные описания для каждой стадии строительства
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from utils.llm import make_llm


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS FOR STRUCTURED LLM OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

class RoofVariation(BaseModel):
    """Описание вариации крыши."""
    type: str = Field(description="Тип крыши: двускатная, четырехскатная, плоская, мансардная, шатровая, купольная, вальмовая, кросс-гамбрель")
    material: str = Field(description="Материал кровли: черепица, шифер, металлочерепица, сланец, солома, деревянная черепица, медная кровля")
    color: str = Field(description="Цвет кровли: терракотовый, графитовый, зеленый мох, синий сланец, натуральный деревянный, медный патина")
    features: str = Field(description="Особенности: фронтоны, слуховые окна, водосточные желоба, карнизы, фигурные коньки")
    pitch: str = Field(description="Угол наклона: пологий 15°, средний 30°, крутой 45°, очень крутой 60°")


class FacadeVariation(BaseModel):
    """Описание вариации фасада."""
    primary_material: str = Field(description="Основной материал фасада: кирпич, камень, штукатурка, дерево, бетон, сайдинг, композитные панели")
    secondary_material: str = Field(description="Дополнительный материал: деревянные рейки, каменная кладка, металлические панели, стекло")
    color_scheme: str = Field(description="Цветовая схема: теплые земляные тона, холодные серые, контрастные бело-черные, пастельные, насыщенные")
    texture: str = Field(description="Текстура: гладкая, рустованная, рельефная, дощатая, каменная кладка")
    special_elements: str = Field(description="Особые элементы: колонны, балконы, эркеры, террасы, патио, крыльцо")


class WindowVariation(BaseModel):
    """Описание вариации окон."""
    style: str = Field(description="Стиль окон: панорамные от пола до потолка, классические прямоугольные, арочные, круглые люки, французские балконы")
    frame_material: str = Field(description="Материал рам: алюминий, ПВХ, дерево, сталь, безрамное остекление")
    arrangement: str = Field(description="Расположение: симметричное, асимметричное, ленточное, панорамное, разбросанное")
    special_features: str = Field(description="Особенности: подоконники-скамьи, окна-ниши, витражи, жалюзи внутри стеклопакета")


class ArchitecturalDetails(BaseModel):
    """Архитектурные детали дома."""
    roof: RoofVariation
    facade: FacadeVariation
    windows: WindowVariation
    unique_features: list[str] = Field(description="Уникальные особенности: веранда, мансарда, цокольный этаж, гараж, терраса на крыше")
    style_description: str = Field(description="Полное описание стиля для промптов (на английском)")
    style_description_ru: str = Field(description="Полное описание стиля для промптов (на русском)")


class LocationDetails(BaseModel):
    """Детали локации с уникальными элементами."""
    environment_description: str = Field(description="Описание окружения (англ)")
    environment_description_ru: str = Field(description="Описание окружения (рус)")
    background_elements: list[str] = Field(description="Элементы на заднем плане")
    lighting_condition: str = Field(description="Особенности освещения в этой локации")
    atmosphere: str = Field(description="Атмосфера локации")
    unique_features: list[str] = Field(description="Уникальные особенности локации")


class BuildingStageVisuals(BaseModel):
    """Визуальные детали для конкретной стадии строительства."""
    stage_key: str
    stage_name: str
    visual_description: str = Field(description="Детальное визуальное описание для промпта (англ)")
    visual_description_ru: str = Field(description="Детальное визуальное описание для промпта (рус)")
    key_elements: list[str] = Field(description="Ключевые визуальные элементы на этой стадии")
    materials_visible: list[str] = Field(description="Видимые материалы на этой стадии")
    worker_activities: list[str] = Field(description="Активности рабочих")
    machinery_present: list[str] = Field(description="Присутствующая техника")


class CompleteArchitecturalVariation(BaseModel):
    """Полная вариация для одного видео."""
    base_style: str = Field(description="Базовый стиль: modern, cottage, villa, cabin, farmhouse, etc.")
    base_location: str = Field(description="Базовая локация: suburbs, forest, seaside, mountains, etc.")
    architecture: ArchitecturalDetails
    location: LocationDetails
    stage_visuals: list[BuildingStageVisuals]
    variation_seed: int = Field(description="Сид для воспроизводимости")


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES FOR LLM
# ═══════════════════════════════════════════════════════════════════════════

ARCHITECTURE_GENERATION_PROMPT = """You are an expert architect and architectural visualization specialist.

TASK: Generate a UNIQUE architectural variation for a {base_style} house in a {base_location} setting.

IMPORTANT: This must be DIFFERENT from typical standard designs. Create something with character!

BASE STYLE: {base_style}
BASE LOCATION: {base_location}

Generate detailed architectural specifications that include:

1. ROOF DESIGN — Be creative and specific:
   - Choose an interesting roof type (not just generic)
   - Specify exact material and color
   - Add distinctive features

2. FACADE DESIGN — Make it unique:
   - Combine materials in interesting ways
   - Define a specific color palette
   - Add special architectural elements

3. WINDOW DESIGN — Vary the approach:
   - Choose distinctive window style
   - Specify frame material
   - Plan interesting arrangement

4. UNIQUE FEATURES — Add character:
   - What makes this house special?
   - Any distinctive architectural elements?
   - Special outdoor spaces?

5. STYLE DESCRIPTIONS:
   - Write a vivid English description for image generation prompts (2-3 sentences)
   - Write the same in Russian

RULES:
- Be SPECIFIC and DETAILED (not generic like "modern house")
- Use architectural terminology
- Consider the location's influence on design
- Make it visually interesting for video content
- AVOID: "typical", "standard", "common", "usual"
- USE: "distinctive", "characterful", "unique", "striking", "elegant"

Respond with structured data following the ArchitecturalDetails schema."""


LOCATION_GENERATION_PROMPT = """You are a location scout and environmental designer for architectural visualization.

TASK: Generate UNIQUE environmental details for a house located in: {base_location}

The house style is: {architecture_description}

Create specific, vivid environmental details:

1. ENVIRONMENT DESCRIPTION:
   - Describe the immediate surroundings
   - What's visible in the background?
   - How does the location affect the setting?

2. BACKGROUND ELEMENTS:
   - List specific elements visible behind the house
   - Include natural and man-made features
   - Consider seasonal aspects

3. LIGHTING CONDITIONS:
   - How does this location affect lighting?
   - Any unique atmospheric effects?
   - Time-of-day characteristics?

4. ATMOSPHERE:
   - What's the mood of this location?
   - How does it feel to be there?

5. UNIQUE FEATURES:
   - What makes this specific spot special?
   - Any distinctive landmarks or characteristics?

RULES:
- Be SPECIFIC (not "some trees" but "tall pine trees with visible bark texture")
- Consider how environment interacts with the house
- Make it visually interesting for timelapse video
- Ensure background elements stay consistent across construction stages

Respond with structured data following the LocationDetails schema."""


STAGE_VISUALS_PROMPT = """You are a construction documentation specialist and visual storyteller.

TASK: Generate detailed visual descriptions for EACH construction stage of a {base_style} house.

ARCHITECTURAL DETAILS:
{architecture_details}

LOCATION:
{location_details}

STAGES TO DESCRIBE:
{stage_list}

For EACH stage, provide:

1. VISUAL DESCRIPTION (English):
   - Detailed scene description for AI image generation
   - Include specific materials, textures, colors
   - Describe the exact state of construction
   - Mention workers and their activities
   - Include machinery if present

2. VISUAL DESCRIPTION (Russian):
   - Same details in Russian

3. KEY ELEMENTS:
   - List main visual elements visible

4. MATERIALS VISIBLE:
   - What construction materials are seen?

5. WORKER ACTIVITIES:
   - What are workers doing at this stage?

6. MACHINERY PRESENT:
   - What equipment is visible?

CRITICAL RULES:
- Each stage must show CLEAR progression
- Descriptions must be SPECIFIC and DETAILED
- Background must stay consistent (only house changes)
- Workers and machinery add life to the scene
- Use architectural terminology
- Ensure visual continuity between stages

Respond with structured data for all stages following the BuildingStageVisuals schema."""


# ═══════════════════════════════════════════════════════════════════════════
# BASE STYLES AND LOCATIONS (for reference)
# ═══════════════════════════════════════════════════════════════════════════

BASE_STYLES: dict[str, dict[str, Any]] = {
    "modern": {
        "name": "современный дом",
        "name_en": "modern house",
        "description": "Архитектура 21 века с акцентом на функциональность и простоту форм. Чистые линии, открытые планировки, интеграция с окружающей средой.",
        "description_en": "21st century architecture focused on functionality and simplicity. Clean lines, open floor plans, integration with surroundings.",
        "typical_roofs": ["плоская", "плоская с зеленой кровлей", "низкая двускатная"],
        "typical_materials": ["бетон", "стекло", "сталь", "дерево", "композиты"],
        "typical_features": ["панорамное остекление", "открытая планировка", "минимум декора", "встроенный гараж", "терраса"],
        "characteristics": ["минимализм", "чистые линии", "функциональность", "открытые пространства", "панорамные окна"],
    },
    "contemporary": {
        "name": "контемпорари",
        "name_en": "contemporary house",
        "description": "Смелые архитектурные решения сочетающие разные стили и материалы. Асимметричные формы, неожиданные углы, экспериментальные конструкции.",
        "description_en": "Bold architectural solutions combining different styles and materials. Asymmetric forms, unexpected angles, experimental structures.",
        "typical_roofs": ["асимметричная", "плоская с выступами", "скошенная", "многоуровневая"],
        "typical_materials": ["стекло", "сталь", "бетон", "дерево", "камень", "композиты"],
        "typical_features": ["нависающие этажи", "внутренний двор", "панорамные окна", "зеленые стены", "необычная геометрия"],
        "characteristics": ["экспериментальные формы", "смешение материалов", "смелые решения", "асимметрия", "уникальность"],
    },
    "minimalist": {
        "name": "минимализм",
        "name_en": "minimalist house",
        "description": "Строгая простота без лишних деталей. Монохромная палитра, скрытые конструкции, идеальные пропорции и чистота пространства.",
        "description_en": "Strict simplicity without unnecessary details. Monochrome palette, hidden structures, perfect proportions and spatial purity.",
        "typical_roofs": ["плоская", "плоская с парапетом", "скрытая кровля"],
        "typical_materials": ["белый бетон", "стекло", "алюминий", "штукатурка"],
        "typical_features": ["отсутствие декора", "скрытые двери", "встроенная мебель", "монохромность", "четкие линии"],
        "characteristics": ["строгая простота", "отсутствие декора", "монохромность", "чистота форм", "функциональность"],
    },
    "scandinavian": {
        "name": "скандинавский дом",
        "name_en": "scandinavian house",
        "description": "Северный уют с функциональностью. Светлые интерьеры, натуральное дерево, простые формы, уютная атмосфера даже в суровом климате.",
        "description_en": "Northern coziness with functionality. Light interiors, natural wood, simple forms, cozy atmosphere even in harsh climate.",
        "typical_roofs": ["двускатная", "двускатная с мансардой", "вальмовая"],
        "typical_materials": ["светлое дерево", "белая штукатурка", "камень", "черепица"],
        "typical_features": ["светлые фасады", "деревянные акценты", "большие окна", "крыльцо", "цветочные ящики"],
        "characteristics": ["светлые тона", "дерево", "уют", "функциональность", "простота"],
    },
    "cottage": {
        "name": "коттедж",
        "name_en": "cottage",
        "description": "Уютный загородный дом для семейного отдыха. Традиционная архитектура с каменными или деревянными элементами, цветущий сад.",
        "description_en": "Cozy country house for family relaxation. Traditional architecture with stone or wooden elements, blooming garden.",
        "typical_roofs": ["двускатная", "двускатная с фронтонами", "сложная многоскатная"],
        "typical_materials": ["камень", "дерево", "кирпич", "черепица", "штукатурка"],
        "typical_features": ["крыльцо", "камин", "цветочные ящики", "сад", "арочные окна", "деревянные ставни"],
        "characteristics": ["уют", "скатная крыша", "камень", "дерево", "традиция", "сад"],
    },
    "villa": {
        "name": "вилла",
        "name_en": "villa",
        "description": "Просторный дом для комфортной жизни с элементами роскоши. Террасы, бассейн, ландшафтный дизайн, премиальные материалы.",
        "description_en": "Spacious house for comfortable living with luxury elements. Terraces, pool, landscape design, premium materials.",
        "typical_roofs": ["плоская", "плоская с террасой", "низкая двускатная", "вальмовая"],
        "typical_materials": ["мрамор", "натуральный камень", "штукатурка", "дерево", "стекло"],
        "typical_features": ["бассейн", "терраса", "панорамные окна", "ландшафтный дизайн", "гараж на два авто", "входная группа"],
        "characteristics": ["роскошь", "пространство", "террасы", "элегантность", "комфорт"],
    },
    "farmhouse": {
        "name": "фермерский дом",
        "name_en": "farmhouse",
        "description": "Традиционный сельский дом с широкой верандой и практичной планировкой. Простые формы, натуральные материалы, связь с землей.",
        "description_en": "Traditional rural house with wide porch and practical layout. Simple forms, natural materials, connection to the land.",
        "typical_roofs": ["двускатная", "двускатная с фронтоном", "вальмовая"],
        "typical_materials": ["дерево", "сайдинг", "кирпич", "металлочерепица"],
        "typical_features": ["широкая веранда", "крыльцо", "амбар", "сарай", "огород", "белый забор"],
        "characteristics": ["простота", "веранда", "практичность", "традиция", "сельский уют"],
    },
    "colonial": {
        "name": "колониальный дом",
        "name_en": "colonial house",
        "description": "Классическая симметричная архитектура с колоннами и центральным входом. Статусность, строгие пропорции, элегантность.",
        "description_en": "Classic symmetrical architecture with columns and central entrance. Status, strict proportions, elegance.",
        "typical_roofs": ["двускатная", "двускатная с фронтоном", "шатровая"],
        "typical_materials": ["кирпич", "дерево", "шинглс", "камень"],
        "typical_features": ["колонны", "симметричный фасад", "центральная дверь", "шторы на окнах", "парадная лестница"],
        "characteristics": ["симметрия", "колонны", "классика", "статусность", "строгость"],
    },
    "victorian": {
        "name": "викторианский дом",
        "name_en": "victorian house",
        "description": "Яркий декоративный стиль с башенками, эркерами и богатым убранством. Асимметрия, витражи, резные детали, яркие цвета.",
        "description_en": "Bright decorative style with towers, bay windows and rich ornamentation. Asymmetry, stained glass, carved details, vibrant colors.",
        "typical_roofs": ["сложная многоскатная", "высокая двускатная", "с башенками"],
        "typical_materials": ["дерево", "кирпич", "шифер", "витражное стекло"],
        "typical_features": ["башенки", "эркеры", "крыльцо с резными колоннами", "витражи", "яркие цвета", "декоративные элементы"],
        "characteristics": ["орнаменты", "башенки", "асимметрия", "декор", "яркость"],
    },
    "mediterranean": {
        "name": "средиземноморский дом",
        "name_en": "mediterranean house",
        "description": "Дом в стиле побережья Испании и Италии. Красная черепичная крыша, арочные окна, штукатурка тёплых тонов, внутренний двор.",
        "description_en": "House in the style of Spanish and Italian coast. Red tile roof, arched windows, warm-toned stucco, inner courtyard.",
        "typical_roofs": ["вальмовая", "вальмовая с терракотовой черепицей", "плоская с террасой"],
        "typical_materials": ["штукатурка", "терракотовая черепица", "камень", "кованое железо"],
        "typical_features": ["арочные окна", "колонны", "терраса", "внутренний двор", "ставни", "балконы с коваными перилами"],
        "characteristics": ["красная черепица", "арки", "штукатурка", "тёплые тона", "средиземноморье"],
    },
    "cabin": {
        "name": "домик в лесу",
        "name_en": "cabin",
        "description": "Небольшой уютный домик из брёвен в лесной местности. Камин, веранда, тёплая атмосфера уединения с природой.",
        "description_en": "Small cozy log house in forest area. Fireplace, porch, warm atmosphere of seclusion with nature.",
        "typical_roofs": ["двускатная", "двускатная с мансардой", "вальмовая"],
        "typical_materials": ["бревно", "камень", "деревянная черепица", "металл"],
        "typical_features": ["камин", "веранда", "каменная труба", "деревянные стены", "уютный интерьер"],
        "characteristics": ["бревна", "уют", "природа", "камин", "лес", "уединение"],
    },
    "log_house": {
        "name": "бревенчатый дом",
        "name_en": "log house",
        "description": "Прочный дом из массивных брёвен ручной рубки. Традиционная технология, экологичность, долговечность, натуральная красота дерева.",
        "description_en": "Sturdy house from massive hand-hewn logs. Traditional technology, eco-friendliness, durability, natural beauty of wood.",
        "typical_roofs": ["двускатная", "двускатная с высоким коньком", "вальмовая"],
        "typical_materials": ["массивное бревно", "камень", "металл", "деревянная черепица"],
        "typical_features": ["ручная рубка", "массивные стены", "камин", "погреб", "деревянные балки"],
        "characteristics": ["массивные брёвна", "традиция", "прочность", "экологичность", "ручная работа"],
    },
    "chalet": {
        "name": "шале",
        "name_en": "chalet",
        "description": "Альпийский горный дом с широкими свесами крыши и деревянными балконами. Каменный цоколь, деревянные элементы, уют.",
        "description_en": "Alpine mountain house with wide roof overhangs and wooden balconies. Stone base, wooden elements, coziness.",
        "typical_roofs": ["очень крутая двускатная", "вальмовая с широкими свесами", "сложная многоскатная"],
        "typical_materials": ["дерево", "камень", "черепица", "штукатурка"],
        "typical_features": ["широкие свесы крыши", "деревянные балконы", "каменный цоколь", "резные элементы", "цветочные короба"],
        "characteristics": ["альпийский стиль", "покатая крыша", "дерево", "камень", "горы"],
    },
    "adobe": {
        "name": "адобе дом",
        "name_en": "adobe house",
        "description": "Традиционный дом из самана с округлыми формами. Экологичность, толстые стены для терморегуляции, связь с пустынным ландшафтом.",
        "description_en": "Traditional adobe house with rounded forms. Eco-friendliness, thick walls for thermal regulation, connection to desert landscape.",
        "typical_roofs": ["плоская", "плоская с парапетом", "купольная"],
        "typical_materials": ["саман", "глина", "солома", "дерево", "камень"],
        "typical_features": ["округлые стены", "толстые стены", "внутренний двор", "камин", "натуральные материалы"],
        "characteristics": ["глина", "округлые формы", "экологичность", "пустыня", "традиция"],
    },
    "mansion": {
        "name": "особняк",
        "name_en": "mansion",
        "description": "Представительный дом высокого класса с парадным входом и ландшафтным дизайном. Колонны, фонтаны, премиальные материалы.",
        "description_en": "Representative high-class house with grand entrance and landscape design. Columns, fountains, premium materials.",
        "typical_roofs": ["четырехскатная", "мансардная", "сложная многоскатная"],
        "typical_materials": ["мрамор", "гранит", "натуральный камень", "бронза", "стекло"],
        "typical_features": ["колонны", "фонтан", "парадная лестница", "ландшафтный дизайн", "въездная аллея", "гараж на несколько авто"],
        "characteristics": ["величие", "колонны", "ландшафт", "роскошь", "статус"],
    },
    "estate": {
        "name": "поместье",
        "name_en": "estate",
        "description": "Большое родовое имение с парком и несколькими постройками. Историческая значимость, простор, благоустроенная территория.",
        "description_en": "Large ancestral estate with park and multiple buildings. Historical significance, spaciousness, landscaped grounds.",
        "typical_roofs": ["четырехскатная", "вальмовая", "мансардная", "сложная многоскатная"],
        "typical_materials": ["кирпич", "камень", "металл", "черепица", "штукатурка"],
        "typical_features": ["парк", "пруд", "несколько строений", "главный дом", "гостевой дом", "хозпостройки", "исторические детали"],
        "characteristics": ["пространство", "парк", "история", "несколько строений", "родовое имение"],
    },
}

BASE_LOCATIONS: dict[str, dict[str, Any]] = {
    "suburbs": {
        "name": "пригород",
        "name_en": "suburbs",
        "description": "Тихий жилой район на окраине города. Ухоженные газоны, соседние дома, асфальтированные улицы, детские площадки. Комфортная семейная среда с развитой инфраструктурой.",
        "description_en": "Quiet residential area on the outskirts of the city. Well-kept lawns, neighboring houses, paved streets, playgrounds. Comfortable family environment with developed infrastructure.",
        "typical_features": ["соседние дома", "газоны", "деревья вдоль улиц", "тротуары", "уличные фонари", "детские площадки", "парковочные места"],
        "atmosphere": "спокойная, семейная, уютная",
        "best_for": ["семейные дома", "коттеджи", "таунхаусы"],
        "characteristics": ["соседние дома", "улица", "газоны", "тихий район", "инфраструктура", "безопасность"],
    },
    "urban_edge": {
        "name": "городская окраина",
        "name_en": "urban edge",
        "description": "Зона перехода от города к природе. Виднеются многоэтажки, слышен городской шум, но уже чувствуется простор. Новостройки соседствуют с зелёными зонами.",
        "description_en": "Transition zone from city to nature. High-rise buildings visible, city noise audible, but space already felt. New buildings coexist with green zones.",
        "typical_features": ["городской силуэт", "шоссе", "новостройки", "стройки", "магистрали", "супермаркеты"],
        "atmosphere": "динамичная, развивающаяся, современная",
        "best_for": ["современные дома", "виллы", "модерн"],
        "characteristics": ["город вдали", "инфраструктура", "развитие", "переходная зона", "новостройки"],
    },
    "planned_community": {
        "name": "запланированный район",
        "name_en": "planned community",
        "description": "Новый жилой комплекс с единой концепцией. Одинаковые дома, идеальные дороги, современное благоустройство, общие пространства для жителей.",
        "description_en": "New residential complex with unified concept. Similar houses, perfect roads, modern landscaping, shared spaces for residents.",
        "typical_features": ["однотипные дома", "новые дороги", "общий парк", "спортивные площадки", "охрана", "подземные коммуникации"],
        "atmosphere": "современная, организованная, чистая",
        "best_for": ["современные дома", "семейные резиденции"],
        "characteristics": ["новый район", "похожие дома", "благоустройство", "единый стиль", "современность"],
    },
    "forest": {
        "name": "густой лес",
        "name_en": "dense forest",
        "description": "Участок среди высоких деревьев с естественной поляной для строительства. Пение птиц, шум листвы, полутень. Идеально для уединённого дома.",
        "description_en": "Plot among tall trees with natural clearing for construction. Birdsong, rustling leaves, partial shade. Perfect for secluded house.",
        "typical_features": ["высокие деревья", "сосны", "ели", "поляна", "опавшие листья", "природная тишина", "дикие животные"],
        "atmosphere": "уединённая, спокойная, природная",
        "best_for": ["коттеджи", "домики в лесу", "шале", "экологичные дома"],
        "characteristics": ["деревья", "тишина", "природа", "поляна", "уединение", "тень"],
    },
    "wooded_area": {
        "name": "лесная опушка",
        "name_en": "wooded area",
        "description": "Смешанный лес с лиственными и хвойными деревьями. Больше света чем в густом лесу, видны небо и облака. Естественный подлесок и кустарники.",
        "description_en": "Mixed forest with deciduous and coniferous trees. More light than in dense forest, sky and clouds visible. Natural undergrowth and shrubs.",
        "typical_features": ["смешанные деревья", "дубы", "берёзы", "сосны", "кустарники", "ярусный подлесок", "больше света"],
        "atmosphere": "живая, естественная, светлая",
        "best_for": ["коттеджи", "семейные дома", "традиционные дома"],
        "characteristics": ["смешанный лес", "подлесок", "дикая природа", "разнообразие", "свет"],
    },
    "seaside": {
        "name": "морское побережье",
        "name_en": "seaside coast",
        "description": "Участок у моря с видом на бескрайнюю воду. Песчаный пляж, пальмы, шум прибоя, солёный бриз. Морской климат и яркое солнце.",
        "description_en": "Plot by the sea with view of endless water. Sandy beach, palm trees, sound of surf, salty breeze. Maritime climate and bright sun.",
        "typical_features": ["песчаный пляж", "пальмы", "морской горизонт", "волны", "прибой", "ракушки", "солёный воздух"],
        "atmosphere": "свободная, яркая, освежающая",
        "best_for": ["виллы", "пляжные дома", "курортная архитектура"],
        "characteristics": ["море", "пляж", "пальмы", "бриз", "вид на воду", "курорт"],
    },
    "lakefront": {
        "name": "озёрный берег",
        "name_en": "lakefront",
        "description": "Спокойный берег озера с зеркальной гладью воды. Причал для лодки, рыбалка, отражение облаков в воде. Уют и тишина.",
        "description_en": "Calm lake shore with mirror-smooth water surface. Dock for boat, fishing, reflection of clouds in water. Coziness and tranquility.",
        "typical_features": ["спокойная вода", "причал", "лодка", "камыши", "утки", "отражение неба", "песок или галечный берег"],
        "atmosphere": "спокойная, умиротворяющая, отражающая",
        "best_for": ["коттеджи", "дома для отдыха", "рыбацкие домики"],
        "characteristics": ["вода", "спокойствие", "причал", "пейзаж", "отражение", "тишина"],
    },
    "riverside": {
        "name": "речной берег",
        "name_en": "riverside",
        "description": "Живописный берег реки с течением и камышами. Ива над водой, песчаные перекаты, плеск рыбы. Динамичный пейзаж с движением воды.",
        "description_en": "Picturesque river bank with current and reeds. Willow over water, sandy shallows, splash of fish. Dynamic landscape with water movement.",
        "typical_features": ["течение реки", "камыши", "ивы", "песчаные перекаты", "мостки", "водоплавающие птицы", "шум воды"],
        "atmosphere": "живая, динамичная, плавная",
        "best_for": ["коттеджи", "усадьбы", "традиционные дома"],
        "characteristics": ["река", "течение", "камыши", "деревья", "движение", "жизнь"],
    },
    "countryside": {
        "name": "открытая сельская местность",
        "name_en": "open countryside",
        "description": "Бескрайние поля и холмы на горизонте. Пастбища, редкие деревья, пастушеский покой. Простор для души и чистый воздух.",
        "description_en": "Endless fields and hills on the horizon. Pastures, rare trees, pastoral peace. Space for the soul and clean air.",
        "typical_features": ["поля", "холмы", "пастбища", "коровы", "ограждения", "редкие деревья", "облака на горизонте"],
        "atmosphere": "просторная, свободная, умиротворяющая",
        "best_for": ["фермерские дома", "усадьбы", "поместья", "коттеджи"],
        "characteristics": ["поля", "холмы", "простор", "тишина", "пастораль", "свобода"],
    },
    "farmland": {
        "name": "сельскохозяйственные угодья",
        "name_en": "farmland",
        "description": "Рабочая сельская местность с обработанными полями. Ряды посевов, сельхозтехника, амбары. Атмосфера труда и плодородия.",
        "description_en": "Working rural area with cultivated fields. Crop rows, agricultural machinery, barns. Atmosphere of work and fertility.",
        "typical_features": ["пашня", "посевы", "тракторы", "амбары", "силосные башни", "орошение", "сельхоздороги"],
        "atmosphere": "рабочая, плодородная, производственная",
        "best_for": ["фермерские дома", "ранчо", "традиционные постройки"],
        "characteristics": ["поля", "урожай", "техника", "работа", "сельское хозяйство", "плодородие"],
    },
    "vineyard": {
        "name": "виноградник на холмах",
        "name_en": "hillside vineyard",
        "description": "Террасированные холмы с рядами виноградных лоз. Южное солнце, каменистая почва, средиземноморский климат. Романтика виноделия.",
        "description_en": "Terraced hills with rows of grape vines. Southern sun, rocky soil, Mediterranean climate. Romance of winemaking.",
        "typical_features": ["ряды лоз", "террасы", "каменные стенки", "вилы", "оливковые деревья", "южное солнце", "кипарисы"],
        "atmosphere": "романтичная, солнечная, вкусная",
        "best_for": ["виллы", "средиземноморские дома", "усадьбы"],
        "characteristics": ["лозы", "холмы", "средиземноморье", "вино", "террасы", "солнце"],
    },
    "mountains": {
        "name": "горный склон",
        "name_en": "mountain slope",
        "description": "Возвышенность среди величественных гор. Снежные вершины на горизонте, хвойный лес, скальные выступы. Чистый горный воздух.",
        "description_en": "Elevation among majestic mountains. Snow-capped peaks on the horizon, coniferous forest, rock outcrops. Clean mountain air.",
        "typical_features": ["снежные вершины", "хвойный лес", "скалы", "горная речка", "сосны", "ели", "туман в долинах"],
        "atmosphere": "величественная, чистая, вдохновляющая",
        "best_for": ["шале", "горные дома", "коттеджи", "хижины"],
        "characteristics": ["вершины", "хвойный лес", "скалы", "высота", "величие", "чистота"],
    },
    "hillside": {
        "name": "холмистый склон",
        "name_en": "hillside",
        "description": "Участок на склоне холма с панорамным видом. Террасирование, разные уровни, обзор долины внизу. Динамичный рельеф.",
        "description_en": "Plot on a hillside with panoramic view. Terracing, different levels, view of valley below. Dynamic terrain.",
        "typical_features": ["уклон", "террасы", "панорамный вид", "долина внизу", "подпорные стенки", "смотровая площадка"],
        "atmosphere": "панорамная, возвышенная, обзорная",
        "best_for": ["виллы", "современные дома", "дома с видом"],
        "characteristics": ["склон", "террасы", "панорама", "высота", "вид", "динамика"],
    },
    "valley": {
        "name": "зелёная долина",
        "name_en": "green valley",
        "description": "Равнина между холмами или горами с плодородной почвой. Река или ручей, луга, пастбища. Защищённость ветрами и прекрасные виды.",
        "description_en": "Plain between hills or mountains with fertile soil. River or stream, meadows, pastures. Wind protection and beautiful views.",
        "typical_features": ["луга", "река", "пастбища", "окружающие холмы", "плодородная земля", "туман по утрам", "птицы"],
        "atmosphere": "защищённая, плодородная, живописная",
        "best_for": ["поместья", "фермы", "усадьбы", "семейные дома"],
        "characteristics": ["зелень", "река", "луга", "окружение горами", "плодородие", "защищённость"],
    },
    "desert": {
        "name": "песчаная пустыня",
        "name_en": "sandy desert",
        "description": "Бескрайние песчаные просторы с дюнами и редкой растительностью. Яркое солнце, резкие тени, ночной холод. Экстремальная красота.",
        "description_en": "Endless sandy expanses with dunes and sparse vegetation. Bright sun, sharp shadows, night cold. Extreme beauty.",
        "typical_features": ["песчаные дюны", "кактусы", "сухие кустарники", "резкие тени", "закаты", "звёздное небо", "тишина"],
        "atmosphere": "экстремальная, яркая, безмолвная",
        "best_for": ["адобе", "современные дома", "экологичные дома"],
        "characteristics": ["песок", "дюны", "кактусы", "жара", "экстрим", "контрасты"],
    },
    "oasis": {
        "name": "пустынный оазис",
        "name_en": "desert oasis",
        "description": "Зелёный остров жизни посреди пустыни. Пальмы, источник воды, прохлада в тени. Контраст между жизнью и песком.",
        "description_en": "Green island of life in the middle of desert. Palm trees, water source, coolness in shade. Contrast between life and sand.",
        "typical_features": ["пальмы", "вода", "зелень", "тень", "птицы", "контраст с пустыней", "прохлада"],
        "atmosphere": "живительная, контрастная, редкая",
        "best_for": ["виллы", "традиционные дома", "курортная архитектура"],
        "characteristics": ["пальмы", "вода", "зелень", "контраст", "жизнь", "прохлада"],
    },
    "tropical": {
        "name": "тропический лес",
        "name_en": "tropical forest",
        "description": "Влажные тропики с пышной растительностью. Пальмы, бананы, экзотические цветы, высокая влажность. Яркие краски природы.",
        "description_en": "Humid tropics with lush vegetation. Palms, bananas, exotic flowers, high humidity. Bright colors of nature.",
        "typical_features": ["пальмы", "бананы", "папоротники", "экзотические цветы", "влажность", "пение птиц", "зелёная стена"],
        "atmosphere": "влажная, яркая, буйная",
        "best_for": ["тропические виллы", "бунгало", "экологичные дома"],
        "characteristics": ["джунгли", "влажность", "экзотика", "пальмы", "пышность", "жизнь"],
    },
    "island": {
        "name": "тропический остров",
        "name_en": "tropical island",
        "description": "Остров посреди океана с пляжем по периметру. Кокосовые пальмы, коралловый песок, бирюзовая вода. Райское уединение.",
        "description_en": "Island in the middle of ocean with beach around perimeter. Coconut palms, coral sand, turquoise water. Paradise seclusion.",
        "typical_features": ["пляж со всех сторон", "кокосовые пальмы", "бирюзовая вода", "коралловый риф", "ракушки", "закат над океаном"],
        "atmosphere": "райская, изолированная, эксклюзивная",
        "best_for": ["виллы", "бунгало", "пляжные дома"],
        "characteristics": ["океан", "пляж", "пальмы", "изоляция", "рай", "эксклюзив"],
    },
}

STAGE_KEYS = [
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
# LLM GENERATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def generate_architectural_variation(
    base_style: str,
    base_location: str,
    variation_seed: int | None = None,
) -> CompleteArchitecturalVariation | None:
    """
    Генерирует уникальную архитектурную вариацию с помощью LLM.
    
    Args:
        base_style: Базовый стиль дома
        base_location: Базовая локация
        variation_seed: Сид для воспроизводимости
        
    Returns:
        CompleteArchitecturalVariation или None при ошибке
    """
    if variation_seed is None:
        variation_seed = random.randint(1, 1000000)
    
    # Устанавливаем сид для воспроизводимости
    random.seed(variation_seed)
    
    try:
        llm = make_llm(temperature=0.8)  # Высокая температура для разнообразия
        
        # Получаем информацию о базовом стиле
        style_info = BASE_STYLES.get(base_style, BASE_STYLES["modern"])
        location_info = BASE_LOCATIONS.get(base_location, BASE_LOCATIONS["suburbs"])
        
        # Шаг 1: Генерируем архитектурные детали
        logger.info(f"[Mode8 Variations] Generating architecture for {base_style}...")
        
        arch_prompt = ARCHITECTURE_GENERATION_PROMPT.format(
            base_style=base_style,
            base_location=base_location,
        )
        
        arch_response = await llm.ainvoke(arch_prompt)
        arch_content = arch_response.content
        
        # Парсим архитектурные детали (упрощённо — извлекаем из текста)
        architecture = _parse_architectural_details(arch_content, base_style)
        
        # Шаг 2: Генерируем детали локации
        logger.info(f"[Mode8 Variations] Generating location details for {base_location}...")
        
        loc_prompt = LOCATION_GENERATION_PROMPT.format(
            base_location=base_location,
            architecture_description=architecture.style_description,
        )
        
        loc_response = await llm.ainvoke(loc_prompt)
        loc_content = loc_response.content
        
        location = _parse_location_details(loc_content, base_location)
        
        # Шаг 3: Генерируем визуальные описания для стадий
        logger.info(f"[Mode8 Variations] Generating stage visuals...")
        
        stage_list = "\n".join([f"- {stage}" for stage in STAGE_KEYS])
        stage_prompt = STAGE_VISUALS_PROMPT.format(
            base_style=base_style,
            architecture_details=architecture.style_description,
            location_details=location.environment_description,
            stage_list=stage_list,
        )
        
        stage_response = await llm.ainvoke(stage_prompt)
        stage_content = stage_response.content
        
        stage_visuals = _parse_stage_visuals(stage_content)
        
        variation = CompleteArchitecturalVariation(
            base_style=base_style,
            base_location=base_location,
            architecture=architecture,
            location=location,
            stage_visuals=stage_visuals,
            variation_seed=variation_seed,
        )
        
        logger.success(f"[Mode8 Variations] Generated unique variation (seed: {variation_seed})")
        return variation
        
    except Exception as e:
        logger.error(f"[Mode8 Variations] Failed to generate variation: {e}")
        return None


def _parse_architectural_details(content: str, base_style: str) -> ArchitecturalDetails:
    """Парсит архитектурные детали из LLM-ответа."""
    content_lower = content.lower()
    
    # Определяем тип крыши
    roof_types = ["двускатная", "четырехскатная", "плоская", "мансардная", "шатровая", "купольная", "вальмовая", "gabled", "hip", "flat", "mansard", "gambrel"]
    roof_type = "двускатная"
    for rt in roof_types:
        if rt in content_lower:
            roof_type = rt if rt in ["двускатная", "четырехскатная", "плоская", "мансардная", "шатровая", "купольная", "вальмовая"] else "двускатная"
            break
    
    # Определяем материал кровли
    roof_materials = ["черепица", "шифер", "металлочерепица", "сланец", "солома", "деревянная черепица", "tile", "slate", "metal", "shingles"]
    roof_material = "черепица"
    for rm in roof_materials:
        if rm in content_lower:
            roof_material = rm if rm in ["черепица", "шифер", "металлочерепица", "сланец", "солома", "деревянная черепица"] else "черепица"
            break
    
    # Извлекаем описание стиля
    style_desc = content
    # Берём первые 2-3 предложения для описания
    sentences = content.split('.')
    style_desc_en = '.'.join(sentences[:3]) if len(sentences) > 2 else content[:300]
    style_desc_ru = style_desc_en  # В реальности здесь был бы перевод
    
    roof = RoofVariation(
        type=roof_type,
        material=roof_material,
        color="терракотовый",
        features="фронтоны, водосточные желоба",
        pitch="средний 30°",
    )
    
    facade = FacadeVariation(
        primary_material="кирпич",
        secondary_material="дерево",
        color_scheme="теплые земляные тона",
        texture="рустованная",
        special_elements="терраса, крыльцо",
    )
    
    windows = WindowVariation(
        style="панорамные окна",
        frame_material="алюминий",
        arrangement="симметричное",
        special_features="подоконники-скамьи",
    )
    
    return ArchitecturalDetails(
        roof=roof,
        facade=facade,
        windows=windows,
        unique_features=["терраса", "мансарда"],
        style_description=style_desc_en[:500],
        style_description_ru=style_desc_ru[:500],
    )


def _parse_location_details(content: str, base_location: str) -> LocationDetails:
    """Парсит детали локации из LLM-ответа."""
    return LocationDetails(
        environment_description=content[:400],
        environment_description_ru=content[:400],
        background_elements=["trees", "sky", "landscape"],
        lighting_condition="natural daylight",
        atmosphere="peaceful",
        unique_features=["natural setting"],
    )


def _parse_stage_visuals(content: str) -> list[BuildingStageVisuals]:
    """Парсит визуальные описания стадий из LLM-ответа."""
    visuals = []
    for i, stage_key in enumerate(STAGE_KEYS):
        visuals.append(BuildingStageVisuals(
            stage_key=stage_key,
            stage_name=stage_key.replace("_", " ").title(),
            visual_description=f"Construction stage: {stage_key}. " + content[:200],
            visual_description_ru=f"Стадия строительства: {stage_key}. " + content[:200],
            key_elements=["workers", "materials", "equipment"],
            materials_visible=["concrete", "bricks", "wood"],
            worker_activities=["building", "installing"],
            machinery_present=["crane", "excavator"],
        ))
    return visuals


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK: Pre-generated variations for when LLM fails
# ═══════════════════════════════════════════════════════════════════════════

PRE_GENERATED_VARIATIONS: dict[str, list[dict]] = {
    "estate": [
        {
            "name": "Классическое поместье с мансардой",
            "roof": "четырехскатная черепичная крыша с мансардными окнами, коньки украшены декоративными элементами",
            "facade": "красный кирпич с белыми каменными деталями, колонны у входа, высокие окна с арочными завершениями",
            "features": ["центральный вход с портиком", "боковые крылья", "терраса с видом на парк"],
        },
        {
            "name": "Поместье в стиле неоготики",
            "roof": "высокая двускатная крыша с фронтонами, шиферная кровля темно-серого цвета, башенка с шпилем",
            "facade": "темный камень с контрастной светлой отделкой окон, стрельчатые окна, резные детали",
            "features": ["башенка с часами", "витражные окна", "каменная ограда"],
        },
        {
            "name": "Современное поместье",
            "roof": "плоская крыша с зеленой кровлей, панорамное остекление на мансарде",
            "facade": "белая штукатурка, панорамные окна от пола до потолка, деревянные рейки на фасаде",
            "features": ["панорамный бассейн", "подземный гараж", "крытая терраса"],
        },
        {
            "name": "Тосканское поместье",
            "roof": "вальмовая крыша с терракотовой черепицей, широкие свесы с деревянными балками",
            "facade": "желтая штукатурка с искусственным старением, ставни на окнах, кованые балконы",
            "features": ["внутренний двор", "винный погреб", "печная труба с декоративной кладкой"],
        },
        {
            "name": "Поместье в колониальном стиле",
            "roof": "шатровая крыша с медной кровлей патинового цвета, множество дымоходов",
            "facade": "белый кирпич с черными ставнями, колонны на всю высоту, широкая лестница",
            "features": ["колоннада на фасаде", "балкон второго этажа", "пристройка с зимним садом"],
        },
        {
            "name": "Поместье в долине",
            "roof": "вальмовая крыша с мягкими скатами, зеленая медная кровля с патиной",
            "facade": "серый природный камень, белые оконные рамы, деревянные ставни",
            "features": ["встроенный гараж на два авто", "панорамная терраса", "каменная кладка цоколя"],
        },
        {
            "name": "Английское поместье",
            "roof": "сложная многоскатная крыша с фронтонами, красная керамическая черепица",
            "facade": "красный кирпич с белым камнем, высокие окна с подоконниками",
            "features": ["круглый подъезд", "фонтан перед домом", "живая изгородь"],
        },
        {
            "name": "Французское шато",
            "roof": "высокая мансардная крыша с люкарнами, сланцевая кровля синего оттенка",
            "facade": "светлый камень с рустовкой, высокие окна с арочными завершениями",
            "features": ["центральный ризалит", "балюстрады на крыше", "парадная лестница"],
        },
    ],
    "modern": [
        {
            "name": "Минималистичный куб",
            "roof": "плоская крыша с парапетом, скрытые водостоки",
            "facade": "белый бетон, панорамное остекление, отсутствие декоративных элементов",
            "features": ["подсветка фасада", "встроенный гараж", "зеленая кровля"],
        },
        {
            "name": "Дом с нависающими этажами",
            "roof": "плоская с выступающими элементами, металлическая кровля",
            "facade": "серый бетон и стекло, верхние этажи нависают над нижними",
            "features": ["висячий сад", "подземная парковка", "панорамный лифт"],
        },
        {
            "name": "Стеклянный павильон",
            "roof": "плоская крыша с панорамными окнами на мансарде",
            "facade": "полностью стеклянные фасады с минимальными рамами, стальные колонны",
            "features": ["внутренний двор-патио", "открытая планировка", "интеллектуальный дом"],
        },
        {
            "name": "Дом с деревянными рейками",
            "roof": "плоская с небольшим уклоном, деревянная кровля",
            "facade": "белая штукатурка с вертикальными деревянными рейками, большие окна",
            "features": ["зеленая стена", "терраса с перголой", "солнечные панели"],
        },
        {
            "name": "Бетонный брутализм",
            "roof": "плоская с выступами, бетонный парапет",
            "facade": "фактурный бетон с отпечатками деревянной опалубки, минимум окон",
            "features": ["внутренний двор", "бассейн инфинити", "скульптурная лестница"],
        },
        {
            "name": "Дом с атриумом",
            "roof": "плоская с зенитными окнами, металлическая кровля",
            "facade": "черный металл и стекло, закрытый фасад с внутренним двором",
            "features": ["центральный атриум", "внутренний сад", "панорамная крыша"],
        },
    ],
    "cottage": [
        {
            "name": "Английский коттедж",
            "roof": "крутая двускатная крыша с черепицей, два фронтона с декоративными балками",
            "facade": "белый камень и темные деревянные балки, цветочные ящики у окон",
            "features": ["арочная входная дверь", "каминная труба с керамическими изразцами", "садовая калитка"],
        },
        {
            "name": "Сказочный коттедж",
            "roof": "сложная форма с несколькими скатами, соломенная кровля",
            "facade": "белая штукатурка с округлыми формами, круглые окна",
            "features": ["круглая входная дверь", "вьющиеся растения на стенах", "колодец во дворе"],
        },
        {
            "name": "Горный коттедж",
            "roof": "высокая двускатная крыша с широкими свесами, деревянная черепица",
            "facade": "темное бревно с каменным цоколем, маленькие окна с переплетами",
            "features": ["камин на два этажа", "деревянная веранда", "погреб"],
        },
        {
            "name": "Приморский коттедж",
            "roof": "двускатная с мансардой, голубая металлическая кровля",
            "facade": "белый сайдинг с синими ставнями, большие окна с видом на море",
            "features": ["веранда с качелями", "душ на улице", "место для барбекю"],
        },
        {
            "name": "Швейцарский шале",
            "roof": "очень крутая двускатная крыша с широкими свесами, темная черепица",
            "facade": "светлое бревно с темными балками, резные балконы",
            "features": ["каменный цоколь", "деревянные ставни", "цветочные короба"],
        },
    ],
    "villa": [
        {
            "name": "Средиземноморская вилла",
            "roof": "плоская с террасой на крыше, парапет с балюстрадой",
            "facade": "белая штукатурка, арочные окна и двери, кованые решетки",
            "features": ["внутренний двор с фонтаном", "бассейн", "патио с колоннами"],
        },
        {
            "name": "Вилла с бассейном",
            "roof": "плоская с зеленой кровлей, панорамное остекление второго этажа",
            "facade": "белый бетон и стекло, минималистичный дизайн",
            "features": ["инфинити бассейн", "панорамная терраса", "подземный гараж"],
        },
        {
            "name": "Тропическая вилла",
            "roof": "высокая коническая крыша с соломенной кровлей",
            "facade": "натуральное дерево и камень, открытые террасы без стен",
            "features": ["открытая гостиная", "бассейн с водопадом", "тропический сад"],
        },
        {
            "name": "Вилла на склоне",
            "roof": "террасированная крыша с несколькими уровнями, зеленая кровля",
            "facade": "белая штукатурка с панорамным остеклением, деревянные элементы",
            "features": ["многоуровневые террасы", "панорамный бассейн", "лифт"],
        },
    ],
    "cabin": [
        {
            "name": "Охотничий домик",
            "roof": "двускатная с высоким коньком, темная металлическая кровля",
            "facade": "темное бревно, маленькие окна с переплетами, каменный цоколь",
            "features": ["камин", "веранда с сеткой от комаров", "сарай для дров"],
        },
        {
            "name": "Домик у озера",
            "roof": "двускатная с мансардой, зеленая металлическая кровля",
            "facade": "светлое бревно с белыми углами, большие окна с видом на воду",
            "features": ["крыльцо с видом на озеро", "причал", "барбекю-зона"],
        },
        {
            "name": "Горный приют",
            "roof": "высокая двускатная с широкими свесами, каменная кровля",
            "facade": "темный камень и бревно, маленькие окна с толстыми стенами",
            "features": ["массивная дверь", "печное отопление", "погреб"],
        },
    ],
    "farmhouse": [
        {
            "name": "Классический фермерский дом",
            "roof": "двускатная с фронтоном, красная металлическая кровля",
            "facade": "белый сайдинг с черными ставнями, широкое крыльцо",
            "features": ["крыльцо на всю ширину", "амбар рядом", "качели на веранде"],
        },
        {
            "name": "Современная ферма",
            "roof": "двускатная с мансардой, черная металлическая кровля",
            "facade": "белая штукатурка с черными окнами, деревянные акценты",
            "features": ["открытая планировка", "большая кухня", "гараж на две машины"],
        },
        {
            "name": "Дом ранчо",
            "roof": "низкая двускатная с широкими свесами, коричневая черепица",
            "facade": "коричневый кирпич с деревянными панелями, арочные окна",
            "features": ["внутренний двор", "камин", "веранда с колоннами"],
        },
    ],
    "mansion": [
        {
            "name": "Классический особняк",
            "roof": "четырехскатная с мансардой, черная сланцевая кровля",
            "facade": "светлый камень с колоннами, высокие окна с балкончиками",
            "features": ["парадная лестница", "фонтан", "въездная аллея"],
        },
        {
            "name": "Современный особняк",
            "roof": "плоская с террасами, зеленая кровля",
            "facade": "белый бетон и стекло, геометричные формы",
            "features": ["панорамный бассейн", "спа-зона", "кинотеатр"],
        },
        {
            "name": "Неоклассический особняк",
            "roof": "высокая мансардная с люкарнами, серый шифер",
            "facade": "белый камень с пилястрами, арочные окна первого этажа",
            "features": ["колоннадный портик", "зимний сад", "прислуга wing"],
        },
    ],
    "victorian": [
        {
            "name": "Красочный викторианский дом",
            "roof": "сложная многоскатная с башенкой, разноцветная черепица",
            "facade": "желтые и коричневые доски с белым декором, резные детали",
            "features": ["круглая башня", "веранда с резными колоннами", "витражи"],
        },
        {
            "name": "Викторианский коттедж",
            "roof": "высокая двускатная с фронтоном, темно-красная черепица",
            "facade": "зеленые стены с белым декором, эркерное окно",
            "features": ["крыльцо с резными перилами", "каминная труба", "сад"],
        },
    ],
    "mediterranean": [
        {
            "name": "Испанская вилла",
            "roof": "вальмовая с терракотовой черепицей, широкие свесы",
            "facade": "белая штукатурка с арочными окнами, кованые балконы",
            "features": ["внутренний двор", "фонтан", "терраса с колоннами"],
        },
        {
            "name": "Греческий дом",
            "roof": "плоская с парапетом, белая штукатурка",
            "facade": "белые стены с синими ставнями и дверями, арки",
            "features": ["терраса на крыше", "виноградная беседка", "каменная мостовая"],
        },
    ],
    "chalet": [
        {
            "name": "Альпийское шале",
            "roof": "очень крутая двускатная с широкими свесами, темная черепица",
            "facade": "светлое бревно с темными балками, резные балконы",
            "features": ["каменный цоколь", "деревянные ставни", "цветочные короба"],
        },
        {
            "name": "Современное шале",
            "roof": "двускатная с мансардой, темная металлическая кровля",
            "facade": "белая штукатурка с деревянными панелями, панорамные окна",
            "features": ["панорамная терраса", "сауна", "камин"],
        },
    ],
    "colonial": [
        {
            "name": "Классический колониальный дом",
            "roof": "двускатная с фронтоном, черная шingles",
            "facade": "красный кирпич с белыми колоннами, симметричный фасад",
            "features": ["колоннадный портик", "шторы на окнах", "крыльцо"],
        },
        {
            "name": "Голландский колониальный",
            "roof": "фронтонная с изогнутыми скатами, черная кровля",
            "facade": "желтые доски с белым декором, широкая водосточная труба",
            "features": ["центральная входная дверь", "окно в фронтоне", "цветники"],
        },
    ],
    "scandinavian": [
        {
            "name": "Шведский дом",
            "roof": "двускатная с мансардой, красная металлическая кровля",
            "facade": "желтые стены с белыми углами и оконными рамами",
            "features": ["крыльцо с цветами", "маленькие окна на мансарде", "сад"],
        },
        {
            "name": "Современный скандинавский дом",
            "roof": "плоская с небольшим уклоном, зеленая кровля",
            "facade": "белая штукатурка с деревянными рейками, большие окна",
            "features": ["терраса с деревянным настилом", "внутренний двор", "подсветка"],
        },
    ],
    "minimalist": [
        {
            "name": "Чистый минимализм",
            "roof": "плоская с парапетом, белая мембрана",
            "facade": "белая штукатурка, минимум окон, скрытые двери",
            "features": ["внутренний двор", "открытая планировка", "подсветка"],
        },
        {
            "name": "Минимализм с теплом",
            "roof": "плоская с деревянной террасой, зеленая кровля",
            "facade": "белая штукатурка с деревянными панелями, большие окна",
            "features": ["терраса на крыше", "внутренний сад", "камин"],
        },
    ],
    "contemporary": [
        {
            "name": "Смелый контемпорари",
            "roof": "асимметричная с выступами, черная металлическая кровля",
            "facade": "серый бетон и стекло, неправильная форма",
            "features": ["висячий сад", "панорамный бассейн", "скульптурная лестница"],
        },
        {
            "name": "Экологичный контемпорари",
            "roof": "плоская с солнечными панелями, зеленая кровля",
            "facade": "дерево и стекло, натуральные материалы",
            "features": ["солнечные батареи", "система сбора дождевой воды", "теплица"],
        },
    ],
    "log_house": [
        {
            "name": "Традиционный бревенчатый дом",
            "roof": "двускатная с высоким коньком, металлическая кровля",
            "facade": "крупные бревна с потемневшей от времени корой, каменный цоколь",
            "features": ["массивная дверь", "камин", "погреб"],
        },
        {
            "name": "Современный бревенчатый дом",
            "roof": "плоская с мансардой, темная металлическая кровля",
            "facade": "обработанное бревно с панорамными окнами, стеклянные вставки",
            "features": ["панорамная терраса", "современный камин", "встроенный гараж"],
        },
    ],
    "adobe": [
        {
            "name": "Традиционный адобе",
            "roof": "плоская с парапетом, глиняная штукатурка",
            "facade": "округлые стены из самана, земляные тона",
            "features": ["внутренний двор", "камин", "толстые стены"],
        },
        {
            "name": "Современный адобе",
            "roof": "плоская с зенитными окнами, зеленая кровля",
            "facade": "гладкие стены из самана с панорамным остеклением",
            "features": ["панорамная терраса", "солнечные панели", "система охлаждения"],
        },
    ],
}


def get_fallback_variation(base_style: str, variation_index: int | None = None) -> dict:
    """
    Возвращает предварительно сгенерированную вариацию если LLM недоступен.
    
    Args:
        base_style: Базовый стиль
        variation_index: Индекс вариации (None = случайная)
        
    Returns:
        Словарь с описанием вариации
    """
    variations = PRE_GENERATED_VARIATIONS.get(base_style, [])
    if not variations:
        # Дефолтная вариация
        return {
            "name": f"{base_style} house",
            "roof": "traditional pitched roof with tile covering",
            "facade": "mixed materials with balanced proportions",
            "features": ["main entrance", "windows", "terrace"],
        }
    
    if variation_index is None:
        variation_index = random.randint(0, len(variations) - 1)
    else:
        variation_index = variation_index % len(variations)
    
    return variations[variation_index]


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

async def get_architectural_variation(
    base_style: str,
    base_location: str,
    use_llm: bool = True,
    variation_seed: int | None = None,
) -> dict[str, Any]:
    """
    Получает архитектурную вариацию для дома.
    
    Args:
        base_style: Базовый стиль дома
        base_location: Базовая локация
        use_llm: Использовать ли LLM для генерации
        variation_seed: Сид для воспроизводимости
        
    Returns:
        Словарь с полным описанием вариации
    """
    if use_llm:
        variation = await generate_architectural_variation(
            base_style=base_style,
            base_location=base_location,
            variation_seed=variation_seed,
        )
        if variation:
            return _variation_to_dict(variation)
    
    # Fallback на предварительно сгенерированные вариации
    fallback = get_fallback_variation(base_style, variation_seed)
    return {
        "base_style": base_style,
        "base_location": base_location,
        "name": fallback["name"],
        "roof_description": fallback["roof"],
        "facade_description": fallback["facade"],
        "unique_features": fallback["features"],
        "style_description": f"{fallback['name']}: {fallback['facade']}",
        "is_fallback": True,
    }


def _variation_to_dict(variation: CompleteArchitecturalVariation) -> dict[str, Any]:
    """Конвертирует Pydantic модель в словарь."""
    arch = variation.architecture
    loc = variation.location
    
    return {
        "base_style": variation.base_style,
        "base_location": variation.base_location,
        "variation_seed": variation.variation_seed,
        "name": f"{arch.roof.type} {variation.base_style}",
        "roof_description": f"{arch.roof.type} крыша из {arch.roof.material}, {arch.roof.color}, {arch.roof.features}",
        "facade_description": f"{arch.facade.primary_material} с {arch.facade.secondary_material}, {arch.facade.color_scheme}, {arch.facade.texture}",
        "window_description": f"{arch.windows.style}, рамы из {arch.windows.frame_material}, {arch.windows.arrangement}",
        "unique_features": arch.unique_features,
        "style_description": arch.style_description,
        "style_description_ru": arch.style_description_ru,
        "location_description": loc.environment_description,
        "stage_visuals": [
            {
                "stage_key": sv.stage_key,
                "visual_description": sv.visual_description,
                "visual_description_ru": sv.visual_description_ru,
            }
            for sv in variation.stage_visuals
        ],
        "is_fallback": False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS FOR PROMPT BUILDING
# ═══════════════════════════════════════════════════════════════════════════

def build_varied_visual_prompt(
    variation: dict[str, Any],
    stage_key: str,
    stage_data: dict[str, Any],
    language: str = "en",
) -> str:
    """
    Строит визуальный промпт с учётом архитектурной вариации.
    
    Args:
        variation: Словарь с вариацией от get_architectural_variation
        stage_key: Ключ стадии строительства
        stage_data: Базовые данные стадии
        language: Язык промпта
        
    Returns:
        Детальный визуальный промпт
    """
    # Получаем описание стадии из вариации если есть
    stage_visual = None
    if "stage_visuals" in variation:
        for sv in variation["stage_visuals"]:
            if sv.get("stage_key") == stage_key:
                stage_visual = sv
                break
    
    # Базовые компоненты
    style_desc = variation.get("style_description", "")
    roof_desc = variation.get("roof_description", "")
    facade_desc = variation.get("facade_description", "")
    window_desc = variation.get("window_description", "")
    features = variation.get("unique_features", [])
    location_desc = variation.get("location_description", "")
    
    # Формируем промпт
    if language == "ru":
        prompt_parts = [
            f"Стадия: {stage_data.get('name', stage_key)}",
            f"Архитектура: {style_desc[:200] if style_desc else variation.get('name', '')}",
            f"Крыша: {roof_desc}",
            f"Фасад: {facade_desc}",
        ]
        if window_desc:
            prompt_parts.append(f"Окна: {window_desc}")
        if features:
            prompt_parts.append(f"Особенности: {', '.join(features[:3])}")
        if location_desc:
            prompt_parts.append(f"Локация: {location_desc[:150]}")
        if stage_visual:
            prompt_parts.append(f"Детали: {stage_visual.get('visual_description_ru', '')[:200]}")
    else:
        prompt_parts = [
            f"Stage: {stage_data.get('name_en', stage_key)}",
            f"Architecture: {style_desc[:200] if style_desc else variation.get('name', '')}",
            f"Roof: {roof_desc}",
            f"Facade: {facade_desc}",
        ]
        if window_desc:
            prompt_parts.append(f"Windows: {window_desc}")
        if features:
            prompt_parts.append(f"Features: {', '.join(features[:3])}")
        if location_desc:
            prompt_parts.append(f"Location: {location_desc[:150]}")
        if stage_visual:
            prompt_parts.append(f"Details: {stage_visual.get('visual_description', '')[:200]}")
    
    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "get_architectural_variation",
    "build_varied_visual_prompt",
    "CompleteArchitecturalVariation",
    "ArchitecturalDetails",
    "PRE_GENERATED_VARIATIONS",
    "BASE_STYLES",
    "BASE_LOCATIONS",
]
