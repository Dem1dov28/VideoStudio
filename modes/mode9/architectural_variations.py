"""
Mode 9 — Vehicle Assembly Variations Generator.

This module generates diverse vehicle assembly variations to ensure each video
is unique even with the same base vehicle type. Instead of fixed templates,
the system generates unique visual details for each vehicle.

Key features:
- LLM-based variation generation for unique vehicle appearances
- Pre-generated fallback variations for when LLM is unavailable
- Detailed visual descriptions for each assembly stage
- Color scheme, material finish, and design variation support
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

class ColorSchemeVariation(BaseModel):
    """Color scheme variation for vehicles."""
    primary_color: str = Field(description="Primary body color: metallic silver, pearl white, racing red, midnight blue, gunmetal gray")
    secondary_color: str = Field(description="Accent color: chrome, carbon black, gold trim, contrasting stripe")
    interior_color: str = Field(description="Interior/cabin color: tan leather, black suede, cream fabric")
    finish_type: str = Field(description="Paint finish: glossy, matte, metallic, pearl, satin")


class DesignDetailsVariation(BaseModel):
    """Design details variation."""
    body_style: str = Field(description="Body style variation: aerodynamic, boxy, streamlined, muscular, elegant")
    accent_features: str = Field(description="Accent features: racing stripes, chrome trim, carbon fiber panels, LED accents")
    unique_elements: list[str] = Field(description="Unique design elements: spoiler type, grille design, headlight style")
    branding_style: str = Field(description="Branding/decal style: minimalist logo, racing numbers, vintage badges, modern emblem")


class MaterialFinishVariation(BaseModel):
    """Material and finish variation."""
    exterior_material: str = Field(description="Exterior material: polished aluminum, carbon fiber, steel panels, composite body")
    surface_finish: str = Field(description="Surface finish: brushed metal, glossy paint, matte coating, raw steel")
    detail_materials: str = Field(description="Detail materials: chrome accents, rubber seals, glass type, trim material")


class VehicleVisualDetails(BaseModel):
    """Complete visual details for a vehicle."""
    color_scheme: ColorSchemeVariation
    design_details: DesignDetailsVariation
    material_finish: MaterialFinishVariation
    visual_description: str = Field(description="Full visual description for prompts (English)")
    visual_description_ru: str = Field(description="Full visual description for prompts (Russian)")


class AssemblyStageVisuals(BaseModel):
    """Visual details for a specific assembly stage."""
    stage_key: str
    stage_name: str
    visual_description: str = Field(description="Detailed visual description for AI generation (English)")
    visual_description_ru: str = Field(description="Detailed visual description (Russian)")
    key_elements: list[str] = Field(description="Key visual elements visible at this stage")
    materials_visible: list[str] = Field(description="Materials visible at this stage")
    worker_activities: list[str] = Field(description="What workers are doing")
    machinery_present: list[str] = Field(description="Equipment/machinery visible")


class LocationEnvironmentDetails(BaseModel):
    """Environment details for the assembly location."""
    environment_description: str = Field(description="Description of surroundings (English)")
    environment_description_ru: str = Field(description="Description of surroundings (Russian)")
    background_elements: list[str] = Field(description="Elements visible in background")
    lighting_condition: str = Field(description="Lighting characteristics")
    atmosphere: str = Field(description="Atmosphere/mood of the location")
    dynamic_features: list[str] = Field(description="Dynamic/interactive elements specific to location")


class CompleteVehicleVariation(BaseModel):
    """Complete variation for one vehicle assembly video."""
    base_vehicle: str = Field(description="Base vehicle type")
    base_location: str = Field(description="Base assembly location")
    vehicle_visuals: VehicleVisualDetails
    location: LocationEnvironmentDetails
    stage_visuals: list[AssemblyStageVisuals]
    variation_seed: int = Field(description="Seed for reproducibility")


# ═══════════════════════════════════════════════════════════════════════════
# BASE VEHICLE TYPES AND LOCATIONS (for reference)
# ═══════════════════════════════════════════════════════════════════════════

BASE_VEHICLE_TYPES: dict[str, dict[str, Any]] = {
    "airplane_passenger": {
        "name": "пассажирский самолёт",
        "name_en": "passenger airplane",
        "description": "Крупное пассажирское воздушное судно для коммерческих перевозок. Многочисленные иллюминаторы, мощные реактивные двигатели, обтекаемый фюзеляж.",
        "typical_colors": ["белый с синей полосой", "серебристый", "белый с красным логотипом", "тёмно-синий"],
        "design_features": ["обтекаемый нос", "крылья с закрылками", "хвостовое оперение", "многочисленные иллюминаторы"],
    },
    "airplane_private": {
        "name": "частный джет",
        "name_en": "private jet",
        "description": "Роскошный небольшой самолёт для частных перелётов. Премиальная отделка, обтекаемые формы, статусный внешний вид.",
        "typical_colors": ["белый с золотой полосой", "серебристо-серый", "чёрный матовый", "шампанское"],
        "design_features": ["небольшие размеры", "панорамные окна", "элегантный профиль", "премиальная отделка"],
    },
    "car_modern": {
        "name": "современный автомобиль",
        "name_en": "modern car",
        "description": "Современный легковой автомобиль с аэродинамичным дизайном. Обтекаемый кузов, современные фары, легкосплавные диски.",
        "typical_colors": ["серебристый металлик", "чёрный", "белый перламутр", "тёмно-синий", "графитовый"],
        "design_features": ["обтекаемый кузов", "светодиодные фары", "легкосплавные диски", "панорамная крыша"],
    },
    "car_sport": {
        "name": "спортивный автомобиль",
        "name_en": "sports car",
        "description": "Высокопроизводительный спортивный автомобиль с агрессивным дизайном. Низкая посадка, мощный спойлер, широкие колёса.",
        "typical_colors": ["красный", "жёлтый", "чёрный матовый", "синий металлик", "оранжевый"],
        "design_features": [["низкая посадка", "спойлер", "широкие арки", "воздухозаборники", "двухдверный"]],
    },
    "car_suv": {
        "name": "внедорожник",
        "name_en": "SUV",
        "description": "Крупный внедорожник с высоким клиренсом и мощным присутствием. Массивные колёса, рейлинги, прочный кузов.",
        "typical_colors": ["чёрный", "тёмно-серый", "белый", "тёмно-синий", "зелёный"],
        "design_features": ["высокий клиренс", "массивные колёса", "рейлинги", "защита порогов"],
    },
    "car_electric": {
        "name": "электромобиль",
        "name_en": "electric vehicle",
        "description": "Футуристичный электромобиль с минималистичным дизайном. Гладкий кузов без решётки радиатора, современные технологии.",
        "typical_colors": ["белый", "серебристый", "красный", "синий", "чёрный"],
        "design_features": ["без решётки радиатора", "гладкий кузов", "аэродинамичные колпаки", "панорамная крыша"],
    },
    "tractor": {
        "name": "трактор",
        "name_en": "tractor",
        "description": "Мощный сельскохозяйственный трактор с характерными большими колёсами. Прочная конструкция, высокая проходимость.",
        "typical_colors": ["зелёный", "красный", "синий", "жёлтый", "оранжевый"],
        "design_features": ["большие задние колёса", "кабина", "фаркоп", "мощный двигатель"],
    },
    "excavator": {
        "name": "экскаватор",
        "name_en": "excavator",
        "description": "Строительный экскаватор с длинной стрелой и ковшом. Гусеничное или колёсное шасси, вращающаяся платформа.",
        "typical_colors": ["жёлтый", "оранжевый", "белый", "синий", "зелёный"],
        "design_features": ["стрела с ковшом", "гусеницы или колёса", "вращающаяся кабина", "гидравлика"],
    },
    "helicopter": {
        "name": "вертолёт",
        "name_en": "helicopter",
        "description": "Вертолёт с несущим и хвостовым винтами. Кабина пилота, шасси или полозья, компактные размеры.",
        "typical_colors": ["белый", "тёмно-синий", "чёрный", "оранжевый", "зелёный камуфляж"],
        "design_features": ["несущий винт", "хвостовой винт", "кабина", "шасси"],
    },
    "ship_cargo": {
        "name": "грузовой корабль",
        "name_en": "cargo ship",
        "description": "Крупное грузовое судно для морских перевозок. Контейнеры на палубе, массивный корпус, высокий мостик.",
        "typical_colors": ["красный корпус", "чёрный", "белый надстройки", "синий", "зелёный"],
        "design_features": ["контейнеры", "массивный корпус", "мостик", "труба"],
    },
    "truck_cargo": {
        "name": "грузовик",
        "name_en": "cargo truck",
        "description": "Большой грузовой автомобиль с кабиной и грузовым отсеком. Многоколёсное шасси, мощный двигатель.",
        "typical_colors": ["белый", "синий", "красный", "зелёный", "серебристый"],
        "design_features": ["высокая кабина", "грузовой отсек", "много колёс", "спальное место"],
    },
    "bus_city": {
        "name": "городской автобус",
        "name_en": "city bus",
        "description": "Длинный городской автобус для пассажирских перевозок. Множество окон, две-три двери, низкий пол.",
        "typical_colors": ["красный", "синий", "жёлтый", "белый", "зелёный"],
        "design_features": ["длинный корпус", "много окон", "двери", "низкий пол"],
    },
    "wind_turbine": {
        "name": "ветряная турбина",
        "name_en": "wind turbine",
        "description": "Высокая ветряная турбина для генерации электроэнергии. Три большие лопасти, высокая башня, генератор.",
        "typical_colors": ["белый", "серебристый", "светло-серый"],
        "design_features": ["три лопасти", "высокая башня", "генератор", "красные огни"],
    },
    "yacht": {
        "name": "яхта",
        "name_en": "yacht",
        "description": "Роскошная яхта с гладким корпусом и элегантными линиями. Палубы, мачты, панорамные окна салона.",
        "typical_colors": ["белый", "тёмно-синий корпус", "кремовый", "серебристый"],
        "design_features": ["гладкий корпус", "палубы", "мачты", "панорамные окна"],
    },
    "submarine": {
        "name": "подводная лодка",
        "name_en": "submarine",
        "description": "Подводная лодка с цилиндрическим корпусом и рубкой. Винты, рули глубины, обтекаемая форма.",
        "typical_colors": ["чёрный", "тёмно-серый", "зелёный камуфляж", "синий"],
        "design_features": ["цилиндрический корпус", "рубка", "винты", "перископ"],
    },
}

BASE_LOCATIONS: dict[str, dict[str, Any]] = {
    "factory": {
        "name": "завод / производственный цех",
        "name_en": "factory / production workshop",
        "description": "Современный сборочный цех с конвейерной линией, промышленными роботами и организованным рабочим пространством.",
        "atmosphere": "промышленная, организованная, технологичная",
        "dynamic_elements": ["конвейерная лента", "роботы-манипуляторы", "подъёмные краны", "освещение цеха"],
    },
    "hangar": {
        "name": "авиационный ангар",
        "name_en": "aviation hangar",
        "description": "Большой промышленный ангар с высоким потолком, металлическими фермами и специализированным оборудованием для авиации.",
        "atmosphere": "просторная, промышленная, специализированная",
        "dynamic_elements": ["подъёмные краны", "освещение через окна", "вентиляция", "взлётная полоса видна"],
    },
    "shipyard": {
        "name": "верфь",
        "name_en": "shipyard",
        "description": "Судостроительная верфь с сухими доками, стапелями и подъёмными кранами. Морская вода, промышленная атмосфера.",
        "atmosphere": "морская, промышленная, масштабная",
        "dynamic_elements": ["краны", "вода в доке", "другие суда", "причал"],
    },
    "construction_site": {
        "name": "строительная площадка",
        "name_en": "construction site",
        "description": "Открытая строительная площадка с кранами, строительными материалами и техникой. Городской пейзаж на заднем плане.",
        "atmosphere": "динамичная, открытая, строительная",
        "dynamic_elements": ["башенные краны", "строительная техника", "материалы", "рабочие"],
    },
    "empty_field": {
        "name": "пустое поле",
        "name_en": "empty field",
        "description": "Открытое поле с зелёной травой и чистым небом. Простор, естественное освещение, горизонт.",
        "atmosphere": "открытая, естественная, просторная",
        "dynamic_elements": ["трава", "небо", "деревья на горизонте", "ветер"],
    },
    "ocean_coast": {
        "name": "побережье океана",
        "name_en": "ocean coast",
        "description": "Берег океана с волнами, пляжем и скалами. Морской горизонт, чайки, свежий бриз.",
        "atmosphere": "свободная, морская, живописная",
        "dynamic_elements": ["волны", "прибой", "пляж", "скалы", "чайки"],
    },
    "desert": {
        "name": "пустыня",
        "name_en": "desert",
        "description": "Песчаная пустыня с дюнами и ярким солнцем. Резкие тени, экстремальные условия, минимум растительности.",
        "atmosphere": "экстремальная, яркая, безмолвная",
        "dynamic_elements": ["песчаные дюны", "резкие тени", "кактусы", "жара"],
    },
    "mountain_valley": {
        "name": "горная долина",
        "name_en": "mountain valley",
        "description": "Долина между горами со скалистыми вершинами и рекой. Чистый воздух, величественные пейзажи.",
        "atmosphere": "величественная, чистая, вдохновляющая",
        "dynamic_elements": ["горные пики", "река", "хвойный лес", "облака"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES FOR LLM
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_VARIATION_PROMPT = """You are an expert vehicle designer and industrial visualization specialist.

TASK: Generate a UNIQUE visual variation for a {base_vehicle} being assembled at {base_location}.

IMPORTANT: This must be DIFFERENT from standard factory designs. Create something with visual character!

BASE VEHICLE: {base_vehicle}
ASSEMBLY LOCATION: {base_location}

Generate detailed visual specifications that include:

1. COLOR SCHEME — Be creative and specific:
   - Primary body color (metallic, pearl, matte options)
   - Secondary/accent color (chrome, carbon, trim color)
   - Interior/cabin color
   - Paint finish type (glossy, matte, metallic, pearl)

2. DESIGN DETAILS — Make it unique:
   - Body style variation (aerodynamic, muscular, elegant, etc.)
   - Accent features (stripes, trim, carbon fiber, LED accents)
   - Unique design elements (spoiler type, grille, headlights)
   - Branding/decal style

3. MATERIAL & FINISH:
   - Exterior material (aluminum, carbon fiber, steel, composite)
   - Surface finish (brushed, glossy, matte, raw)
   - Detail materials (chrome, rubber, glass type)

4. VISUAL DESCRIPTIONS:
   - Write a vivid English description for image generation (2-3 sentences)
   - Write the same in Russian

RULES:
- Be SPECIFIC and DETAILED (not generic like "red car")
- Use automotive/industrial terminology
- Consider the assembly location's influence
- Make it visually interesting for video content
- AVOID: "typical", "standard", "common", "usual"
- USE: "distinctive", "characterful", "unique", "striking", "elegant"

Respond with structured data following the VehicleVisualDetails schema."""


LOCATION_ENVIRONMENT_PROMPT = """You are an environmental designer for industrial visualization.

TASK: Generate UNIQUE environmental details for vehicle assembly at: {base_location}

The vehicle being assembled is: {vehicle_description}

Create specific, vivid environmental details:

1. ENVIRONMENT DESCRIPTION:
   - Describe the immediate surroundings
   - What's visible in the background?
   - How does the location affect the assembly setting?

2. BACKGROUND ELEMENTS:
   - List specific elements visible behind the assembly area
   - Include industrial and natural features
   - Consider scale and perspective

3. LIGHTING CONDITIONS:
   - How does this location affect lighting?
   - Any unique atmospheric effects?
   - Time-of-day characteristics for assembly?

4. ATMOSPHERE:
   - What's the mood of this assembly location?
   - How does it feel to work there?

5. DYNAMIC FEATURES:
   - What makes this specific location special?
   - Any interactive or moving elements?

RULES:
- Be SPECIFIC (not "some equipment" but "overhead gantry crane with yellow paint")
- Consider how environment interacts with vehicle assembly
- Make it visually interesting for timelapse video
- Ensure background elements stay consistent across assembly stages

Respond with structured data following the LocationEnvironmentDetails schema."""


STAGE_VISUALS_PROMPT = """You are a vehicle assembly documentation specialist and visual storyteller.

TASK: Generate detailed visual descriptions for EACH assembly stage of a {base_vehicle}.

VEHICLE DETAILS:
{vehicle_details}

LOCATION:
{location_details}

STAGES TO DESCRIBE:
{stage_list}

For EACH stage, provide:

1. VISUAL DESCRIPTION (English):
   - Detailed scene description for AI video generation
   - Include specific materials, colors, textures
   - Describe the exact state of assembly
   - Mention workers and their activities
   - Include machinery if present

2. VISUAL DESCRIPTION (Russian):
   - Same details in Russian

3. KEY ELEMENTS:
   - List main visual elements visible

4. MATERIALS VISIBLE:
   - What assembly materials are seen?

5. WORKER ACTIVITIES:
   - What are workers doing at this stage?

6. MACHINERY PRESENT:
   - What equipment is visible?

CRITICAL RULES:
- Each stage must show CLEAR progression
- Descriptions must be SPECIFIC and DETAILED
- Background must stay consistent (only vehicle changes)
- Workers and machinery add life to the scene
- Use industrial terminology
- Ensure visual continuity between stages

Respond with structured data for all stages following the AssemblyStageVisuals schema."""


# ═══════════════════════════════════════════════════════════════════════════
# LLM GENERATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def generate_vehicle_variation(
    base_vehicle: str,
    base_location: str,
    variation_seed: int | None = None,
) -> CompleteVehicleVariation | None:
    """
    Generate unique vehicle variation using LLM.
    
    Args:
        base_vehicle: Base vehicle type
        base_location: Base assembly location
        variation_seed: Seed for reproducibility
        
    Returns:
        CompleteVehicleVariation or None on error
    """
    if variation_seed is None:
        variation_seed = random.randint(1, 1000000)
    
    random.seed(variation_seed)
    
    try:
        llm = make_llm(temperature=0.8)
        
        vehicle_info = BASE_VEHICLE_TYPES.get(base_vehicle, BASE_VEHICLE_TYPES["car_modern"])
        location_info = BASE_LOCATIONS.get(base_location, BASE_LOCATIONS["factory"])
        
        # Step 1: Generate vehicle visual details
        logger.info(f"[Mode9 Variations] Generating visuals for {base_vehicle}...")
        
        vehicle_prompt = VEHICLE_VARIATION_PROMPT.format(
            base_vehicle=base_vehicle,
            base_location=base_location,
        )
        
        vehicle_response = await llm.ainvoke(vehicle_prompt)
        vehicle_visuals = _parse_vehicle_visuals(vehicle_response.content, base_vehicle)
        
        # Step 2: Generate location details
        logger.info(f"[Mode9 Variations] Generating location details for {base_location}...")
        
        loc_prompt = LOCATION_ENVIRONMENT_PROMPT.format(
            base_location=base_location,
            vehicle_description=vehicle_visuals.visual_description,
        )
        
        loc_response = await llm.ainvoke(loc_prompt)
        location = _parse_location_details(loc_response.content, base_location)
        
        # Step 3: Generate stage visuals
        logger.info(f"[Mode9 Variations] Generating assembly stage visuals...")
        
        stage_keys = ["empty_space", "frame_chassis", "engine", "body_panels", "wheels", "interior", "paint_finish"]
        stage_list = "\n".join([f"- {stage}" for stage in stage_keys])
        
        stage_prompt = STAGE_VISUALS_PROMPT.format(
            base_vehicle=base_vehicle,
            vehicle_details=vehicle_visuals.visual_description,
            location_details=location.environment_description,
            stage_list=stage_list,
        )
        
        stage_response = await llm.ainvoke(stage_prompt)
        stage_visuals = _parse_stage_visuals(stage_response.content, stage_keys)
        
        variation = CompleteVehicleVariation(
            base_vehicle=base_vehicle,
            base_location=base_location,
            vehicle_visuals=vehicle_visuals,
            location=location,
            stage_visuals=stage_visuals,
            variation_seed=variation_seed,
        )
        
        logger.success(f"[Mode9 Variations] Generated unique variation (seed: {variation_seed})")
        return variation
        
    except Exception as e:
        logger.error(f"[Mode9 Variations] Failed to generate variation: {e}")
        return None


def _parse_vehicle_visuals(content: str, base_vehicle: str) -> VehicleVisualDetails:
    """Parse vehicle visual details from LLM response."""
    content_lower = content.lower()
    
    # Extract color information
    colors = ["red", "blue", "green", "black", "white", "silver", "yellow", "orange", "gray", "металлик", "красный", "синий", "чёрный", "белый"]
    primary_color = "metallic silver"
    for c in colors:
        if c in content_lower:
            primary_color = c
            break
    
    # Extract finish type
    finishes = ["glossy", "matte", "metallic", "pearl", "satin", "глянцевый", "матовый", "металлик"]
    finish_type = "glossy"
    for f in finishes:
        if f in content_lower:
            finish_type = f if f in ["glossy", "matte", "metallic", "pearl", "satin"] else "glossy"
            break
    
    color_scheme = ColorSchemeVariation(
        primary_color=primary_color,
        secondary_color="chrome accents",
        interior_color="black leather",
        finish_type=finish_type,
    )
    
    design_details = DesignDetailsVariation(
        body_style="aerodynamic",
        accent_features="racing stripes",
        unique_elements=["spoiler", "custom grille"],
        branding_style="minimalist logo",
    )
    
    material_finish = MaterialFinishVariation(
        exterior_material="polished aluminum",
        surface_finish="glossy paint",
        detail_materials="chrome trim, rubber seals",
    )
    
    # Extract description from content
    sentences = content.split('.')
    visual_desc = '.'.join(sentences[:3]) if len(sentences) > 2 else content[:300]
    
    return VehicleVisualDetails(
        color_scheme=color_scheme,
        design_details=design_details,
        material_finish=material_finish,
        visual_description=visual_desc[:500],
        visual_description_ru=visual_desc[:500],
    )


def _parse_location_details(content: str, base_location: str) -> LocationEnvironmentDetails:
    """Parse location details from LLM response."""
    return LocationEnvironmentDetails(
        environment_description=content[:400],
        environment_description_ru=content[:400],
        background_elements=["industrial equipment", "workers", "machinery"],
        lighting_condition="natural daylight with industrial lighting",
        atmosphere="productive industrial environment",
        dynamic_features=["moving cranes", "workers walking", "conveyor movement"],
    )


def _parse_stage_visuals(content: str, stage_keys: list[str]) -> list[AssemblyStageVisuals]:
    """Parse stage visuals from LLM response."""
    visuals = []
    for stage_key in stage_keys:
        visuals.append(AssemblyStageVisuals(
            stage_key=stage_key,
            stage_name=stage_key.replace("_", " ").title(),
            visual_description=f"Assembly stage: {stage_key}. " + content[:200],
            visual_description_ru=f"Стадия сборки: {stage_key}. " + content[:200],
            key_elements=["workers", "parts", "equipment"],
            materials_visible=["metal", "components", "tools"],
            worker_activities=["assembling", "installing"],
            machinery_present=["crane", "lift"],
        ))
    return visuals


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK: Pre-generated variations
# ═══════════════════════════════════════════════════════════════════════════

PRE_GENERATED_VARIATIONS: dict[str, list[dict]] = {
    "airplane_passenger": [
        {
            "name": "Классический пассажирский лайнер",
            "primary_color": "белый с синей полосой",
            "finish": "глянцевый металлик",
            "accent_features": ["синяя полоса вдоль фюзеляжа", "логотип на хвосте", "хромированные иллюминаторы"],
            "unique_elements": ["двухэтажная конфигурация", "широкофюзеляжный", "четыре двигателя"],
        },
        {
            "name": "Современный узкофюзеляжный",
            "primary_color": "серебристо-белый",
            "finish": "перламутровый металлик",
            "accent_features": ["красная полоса на хвосте", "тёмные иллюминаторы", "глянцевый нос"],
            "unique_elements": ["загнутые законцовки крыльев", "два мощных двигателя", "панорамные окна кабины"],
        },
        {
            "name": "Премиальный дальнемагистральный",
            "primary_color": "тёмно-синий",
            "finish": "глубокий металлик",
            "accent_features": ["золотая окантовка", "хромированные детали", "матовые панели"],
            "unique_elements": ["увеличенный топливный бак", "три двигателя", "улучшенная аэродинамика"],
        },
    ],
    "car_modern": [
        {
            "name": "Элегантный седан бизнес-класса",
            "primary_color": "тёмно-синий металлик",
            "finish": "глубокий глянец",
            "accent_features": ["хромированная решётка", "светодиодные полосы", "легкосплавные диски"],
            "unique_elements": ["панорамная крыша", "двойная выхлопная система", "спортивный обвес"],
        },
        {
            "name": "Современный городской автомобиль",
            "primary_color": "серебристый",
            "finish": "металлик",
            "accent_features": ["чёрная крыша", "красные суппорты", "тонированные стёкла"],
            "unique_elements": ["компактные размеры", "большие колёса", "аэродинамический спойлер"],
        },
        {
            "name": "Премиальный представительский",
            "primary_color": "чёрный оникс",
            "finish": "керамическое покрытие",
            "accent_features": ["матовые элементы", "хромированные молдинги", "LED-оптика"],
            "unique_elements": ["удлинённая колёсная база", "задний спойлер", "пневмоподвеска"],
        },
    ],
    "car_sport": [
        {
            "name": "Агрессивный суперкар",
            "primary_color": "ярко-красный",
            "finish": "глянцевый",
            "accent_features": ["чёрные полосы", "карбоновые элементы", "красные суппорты"],
            "unique_elements": ["низкая посадка", "большой задний спойлер", "воздухозаборники на крыше"],
        },
        {
            "name": "Трековый монстр",
            "primary_color": "матовый чёрный",
            "finish": "матовый сатин",
            "accent_features": ["неоновые акценты", "графика номера", "карбоновый спойлер"],
            "unique_elements": ["широкий кузов", "гоночный обвес", "выпускная система сбоку"],
        },
        {
            "name": "Элегантное купе",
            "primary_color": "жёлтый",
            "finish": "перламутровый",
            "accent_features": ["чёрная крыша", "хромированные зеркала", "тонированные фары"],
            "unique_elements": ["длинный капот", "плавная линия крыши", "двухдверный кузов"],
        },
    ],
    "car_suv": [
        {
            "name": "Мощный премиум внедорожник",
            "primary_color": "чёрный",
            "finish": "глубокий глянец",
            "accent_features": ["хромированные элементы", "панорамная крыша", "большие диски"],
            "unique_elements": ["высокий клиренс", "массивная решётка", "защита порогов"],
        },
        {
            "name": "Спортивный кроссовер",
            "primary_color": "белый",
            "finish": "перламутровый",
            "accent_features": ["чёрный глянцевый пакет", "красные суппорты", "спойлер на крыше"],
            "unique_elements": ["купеобразная крыша", "спортивные бамперы", "двойной выхлоп"],
        },
        {
            "name": "Приключенческий внедорожник",
            "primary_color": "зелёный хаки",
            "finish": "матовый",
            "accent_features": ["чёрные накладки", "резиновые брызговики", "багажник на крыше"],
            "unique_elements": ["внедорожные шины", "лебёдка", "дополнительный свет"],
        },
    ],
    "tractor": [
        {
            "name": "Классический фермерский",
            "primary_color": "зелёный",
            "finish": "глянцевый",
            "accent_features": ["жёлтые диски", "хромированная выхлопная", "белые полосы"],
            "unique_elements": ["огромные задние колёса", "открытая кабина", "фаркоп"],
        },
        {
            "name": "Современный агро-трактор",
            "primary_color": "красный",
            "finish": "металлик",
            "accent_features": ["тонированные стёкла", "LED-фары", "хромированные элементы"],
            "unique_elements": ["закрытая кабина с кондиционером", "гусеничный ход", "навесное оборудование"],
        },
        {
            "name": "Мощный промышленный",
            "primary_color": "синий",
            "finish": "прочное покрытие",
            "accent_features": ["жёлтые предупреждающие полосы", "светофоры", "защитные дуги"],
            "unique_elements": ["гусеничное шасси", "гидравлическая система", "подъёмное оборудование"],
        },
    ],
    "excavator": [
        {
            "name": "Стандартный строительный",
            "primary_color": "жёлтый",
            "finish": "промышленная краска",
            "accent_features": ["чёрные полосы", "предупреждающие наклейки", "светофоры"],
            "unique_elements": ["гусеничное шасси", "длинная стрела", "ковш", "вращающаяся платформа"],
        },
        {
            "name": "Тяжёлый карьерный",
            "primary_color": "оранжевый",
            "finish": "износостойкое покрытие",
            "accent_features": ["усиленные элементы", "защитные решётки", "яркие опознавательные знаки"],
            "unique_elements": ["массивный ковш", "усиленная стрела", "гигантские гусеницы"],
        },
        {
            "name": "Компактный городской",
            "primary_color": "белый",
            "finish": "глянцевый",
            "accent_features": ["оранжевые акценты", "компактные размеры", "резиновые гусеницы"],
            "unique_elements": ["маленький ковш", "поворотная стрела", "низкий центр тяжести"],
        },
    ],
    "helicopter": [
        {
            "name": "Медицинский вертолёт",
            "primary_color": "белый с оранжевыми полосами",
            "finish": "глянцевый",
            "accent_features": ["красный крест", "светофоры", "отражающие полосы"],
            "unique_elements": ["большой несущий винт", "хвостовой винт", "панорамные окна"],
        },
        {
            "name": "Транспортный вертолёт",
            "primary_color": "тёмно-зелёный камуфляж",
            "finish": "матовый",
            "accent_features": ["тактические маркировки", "антенны", "защитное стекло"],
            "unique_elements": ["двойной несущий винт", "грузовой отсек", "шасси с колёсами"],
        },
        {
            "name": "Гражданский VIP",
            "primary_color": "тёмно-синий",
            "finish": "перламутровый",
            "accent_features": ["золотые полосы", "тонированные стёкла", "хромированные детали"],
            "unique_elements": ["обтекаемый кузов", "малошумный винт", "премиальный салон"],
        },
    ],
    "ship_cargo": [
        {
            "name": "Контейнеровоз",
            "primary_color": "красный корпус, белая надстройка",
            "finish": "морская краска",
            "accent_features": ["чёрная труба", "имя на корме", "навигационные огни"],
            "unique_elements": ["ряды контейнеров", "высокий мостик", "якорное устройство"],
        },
        {
            "name": "Балкер",
            "primary_color": "тёмно-синий",
            "finish": "антиобрастающее покрытие",
            "accent_features": ["оранжевая труба", "предупреждающие знаки", "судовой кран"],
            "unique_elements": ["открытые трюмы", "массивный корпус", "грузовые люки"],
        },
        {
            "name": "Танкер",
            "primary_color": "серый",
            "finish": "специальное покрытие",
            "accent_features": ["жёлтые полосы", "предупреждающие знаки", "пожарное оборудование"],
            "unique_elements": ["гладкая палуба", "трубопроводы", "насосная станция"],
        },
    ],
    "truck_cargo": [
        {
            "name": "Дальнобойный фура",
            "primary_color": "белый",
            "finish": "глянцевый",
            "accent_features": ["синие полосы", "хромированная решётка", "тюнингованные выхлопы"],
            "unique_elements": ["высокая кабина", "спальное место", "рефрижераторный прицеп"],
        },
        {
            "name": "Самосвал",
            "primary_color": "жёлтый",
            "finish": "прочное покрытие",
            "accent_features": ["чёрные полосы", "предупреждающие знаки", "усиленный бампер"],
            "unique_elements": ["гидравлический кузов", "высокая грузоподъёмность", "внедорожные шины"],
        },
        {
            "name": "Бортовой грузовик",
            "primary_color": "синий",
            "finish": "металлик",
            "accent_features": ["хром", "тюнинг фар", "литые диски"],
            "unique_elements": ["открытая платформа", "тент", "гидроборт"],
        },
    ],
    "bus_city": [
        {
            "name": "Классический городской",
            "primary_color": "красный",
            "finish": "глянцевый",
            "accent_features": ["белая полоса", "большие окна", "реклама на борту"],
            "unique_elements": ["три двери", "низкий пол", "много сидений"],
        },
        {
            "name": "Современный низкопольный",
            "primary_color": "синий металлик",
            "finish": "перламутровый",
            "accent_features": ["панорамное остекление", "LED-освещение", "электронное табло"],
            "unique_elements": ["полностью низкий пол", "две двери", "места для инвалидных колясок"],
        },
        {
            "name": "Артикулированный",
            "primary_color": "жёлтый",
            "finish": "яркий",
            "accent_features": ["чёрные элементы", "сочленение", "длинный корпус"],
            "unique_elements": ["гармошка посередине", "четыре двери", "очень вместительный"],
        },
    ],
    "wind_turbine": [
        {
            "name": "Классическая белая",
            "primary_color": "белый",
            "finish": "глянцевый",
            "accent_features": ["красные огни на вершине", "логотип производителя", "три лопасти"],
            "unique_elements": ["высокая башня", "большой ротор", "генератор в гондоле"],
        },
        {
            "name": "Прибрежная морская",
            "primary_color": "серый",
            "finish": "морское покрытие",
            "accent_features": ["усиленная конструкция", "платформа на сваях", "освещение"],
            "unique_elements": ["огромные лопасти", "высота 150+ метров", "офшорная установка"],
        },
        {
            "name": "Компактная сельская",
            "primary_color": "белый с зелёной полосой",
            "finish": "матовый",
            "accent_features": ["меньшие размеры", "три лопасти", "красные мигалки"],
            "unique_elements": ["невысокая башня", "тихий ход", "для частного использования"],
        },
    ],
    "yacht": [
        {
            "name": "Моторная супер-яхта",
            "primary_color": "белый",
            "finish": "глянцевый гелькоут",
            "accent_features": ["хромированные поручни", "панорамные окна", "деревянная палуба"],
            "unique_elements": ["несколько палуб", "бассейн на верхней палубе", "вертолётная площадка"],
        },
        {
            "name": "Парусная мега-яхта",
            "primary_color": "тёмно-синий корпус",
            "finish": "матовый",
            "accent_features": ["высокие мачты", "белые паруса", "золотые детали"],
            "unique_elements": ["три мачты", "гигантские паруса", "элегантные линии"],
        },
        {
            "name": "Спортивный катер",
            "primary_color": "чёрный",
            "finish": "карбоновый",
            "accent_features": ["красные акценты", "обтекаемый корпус", "тюнингованные двигатели"],
            "unique_elements": ["открытая палуба", "двойной корпус", "высокая скорость"],
        },
    ],
    "submarine": [
        {
            "name": "Атомная подлодка",
            "primary_color": "чёрный",
            "finish": "антигидроакустическое покрытие",
            "accent_features": ["антенны", "перископ", "гидролокатор"],
            "unique_elements": ["цилиндрический корпус", "рубка", "винты", "ядерный реактор"],
        },
        {
            "name": "Дизель-электрическая",
            "primary_color": "тёмно-серый",
            "finish": "матовый",
            "accent_features": ["выхлопные отверстия", "антенны", "спасательная камера"],
            "unique_elements": ["компактный корпус", "дизель-генераторы", "батареи"],
        },
        {
            "name": "Глубоководный аппарат",
            "primary_color": "белый",
            "finish": "специальное покрытие",
            "accent_features": ["сферический корпус", "иллюминаторы", "манипуляторы"],
            "unique_elements": ["сферическая кабина", "научное оборудование", "глубоководные исследования"],
        },
    ],
}


def get_fallback_variation(base_vehicle: str, variation_index: int | None = None) -> dict:
    """
    Return pre-generated variation if LLM is unavailable.
    
    Args:
        base_vehicle: Base vehicle type
        variation_index: Variation index (None = random)
        
    Returns:
        Dictionary with variation description
    """
    variations = PRE_GENERATED_VARIATIONS.get(base_vehicle, [])
    if not variations:
        # Default variation
        return {
            "name": f"{base_vehicle} assembly",
            "primary_color": "metallic silver",
            "finish": "glossy",
            "accent_features": ["chrome trim", "standard badges"],
            "unique_elements": ["standard configuration"],
        }
    
    if variation_index is None:
        variation_index = random.randint(0, len(variations) - 1)
    else:
        variation_index = variation_index % len(variations)
    
    return variations[variation_index]


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

async def get_vehicle_variation(
    base_vehicle: str,
    base_location: str,
    use_llm: bool = True,
    variation_seed: int | None = None,
) -> dict[str, Any]:
    """
    Get vehicle variation for assembly.
    
    Args:
        base_vehicle: Base vehicle type
        base_location: Base assembly location
        use_llm: Whether to use LLM for generation
        variation_seed: Seed for reproducibility
        
    Returns:
        Dictionary with complete variation description
    """
    if use_llm:
        variation = await generate_vehicle_variation(
            base_vehicle=base_vehicle,
            base_location=base_location,
            variation_seed=variation_seed,
        )
        if variation:
            return _variation_to_dict(variation)
    
    # Fallback to pre-generated variations
    fallback = get_fallback_variation(base_vehicle, variation_seed)
    return {
        "base_vehicle": base_vehicle,
        "base_location": base_location,
        "name": fallback["name"],
        "primary_color": fallback["primary_color"],
        "finish": fallback["finish"],
        "accent_features": fallback["accent_features"],
        "unique_elements": fallback["unique_elements"],
        "visual_description": f"{fallback['name']}: {fallback['primary_color']} with {', '.join(fallback['accent_features'][:2])}",
        "is_fallback": True,
    }


def _variation_to_dict(variation: CompleteVehicleVariation) -> dict[str, Any]:
    """Convert Pydantic model to dictionary."""
    v = variation.vehicle_visuals
    loc = variation.location
    
    return {
        "base_vehicle": variation.base_vehicle,
        "base_location": variation.base_location,
        "variation_seed": variation.variation_seed,
        "name": f"{v.color_scheme.primary_color} {variation.base_vehicle}",
        "primary_color": v.color_scheme.primary_color,
        "secondary_color": v.color_scheme.secondary_color,
        "interior_color": v.color_scheme.interior_color,
        "finish": v.color_scheme.finish_type,
        "body_style": v.design_details.body_style,
        "accent_features": v.design_details.accent_features,
        "unique_elements": v.design_details.unique_elements,
        "exterior_material": v.material_finish.exterior_material,
        "surface_finish": v.material_finish.surface_finish,
        "visual_description": v.visual_description,
        "visual_description_ru": v.visual_description_ru,
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


def build_varied_visual_prompt(
    variation: dict[str, Any],
    stage_key: str,
    stage_data: dict[str, Any],
    language: str = "en",
) -> str:
    """
    Build visual prompt with vehicle variation.
    
    Args:
        variation: Variation dictionary from get_vehicle_variation
        stage_key: Assembly stage key
        stage_data: Base stage data
        language: Prompt language
        
    Returns:
        Detailed visual prompt
    """
    # Get stage description from variation if available
    stage_visual = None
    if "stage_visuals" in variation:
        for sv in variation["stage_visuals"]:
            if sv.get("stage_key") == stage_key:
                stage_visual = sv
                break
    
    # Base components
    visual_desc = variation.get("visual_description", "")
    primary_color = variation.get("primary_color", "")
    finish = variation.get("finish", "")
    accent_features = variation.get("accent_features", [])
    unique_elements = variation.get("unique_elements", [])
    location_desc = variation.get("location_description", "")
    
    # Form prompt
    if language == "ru":
        prompt_parts = [
            f"Стадия: {stage_data.get('name', stage_key)}",
            f"Транспорт: {variation.get('name', '')}",
            f"Цвет: {primary_color} ({finish})",
        ]
        if accent_features:
            prompt_parts.append(f"Акценты: {', '.join(accent_features[:3])}")
        if unique_elements:
            prompt_parts.append(f"Особенности: {', '.join(unique_elements[:3])}")
        if location_desc:
            prompt_parts.append(f"Локация: {location_desc[:150]}")
        if stage_visual:
            prompt_parts.append(f"Детали: {stage_visual.get('visual_description_ru', '')[:200]}")
    else:
        prompt_parts = [
            f"Stage: {stage_data.get('name_en', stage_key)}",
            f"Vehicle: {variation.get('name', '')}",
            f"Color: {primary_color} ({finish})",
        ]
        if accent_features:
            prompt_parts.append(f"Accents: {', '.join(accent_features[:3])}")
        if unique_elements:
            prompt_parts.append(f"Features: {', '.join(unique_elements[:3])}")
        if location_desc:
            prompt_parts.append(f"Location: {location_desc[:150]}")
        if stage_visual:
            prompt_parts.append(f"Details: {stage_visual.get('visual_description', '')[:200]}")
    
    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "get_vehicle_variation",
    "build_varied_visual_prompt",
    "CompleteVehicleVariation",
    "VehicleVisualDetails",
    "PRE_GENERATED_VARIATIONS",
    "BASE_VEHICLE_TYPES",
    "BASE_LOCATIONS",
]
