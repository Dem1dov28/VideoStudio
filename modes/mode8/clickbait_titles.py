"""
Clickbait Title Generator for Mode8, Mode9, and Mode12 (room restoration).

Generates viral, attention-grabbing titles with real video duration.

Examples from user requirements:
- Я ПОСТРОИЛ ДОМ С НУЛЯ ЗА 20 СЕКУНД 🏗️
- Я ПОСТРОИЛ ВИЛЛУ В ПУСТЫНЕ ЗА 30 СЕКУНД 🌵
- Я ПОСТРОИЛ ДОМ В ЛЕСУ ЗА 15 СЕКУНД 🌲
- Я ПОСТРОИЛ ОСОБНЯК С НУЛЯ… СМОТРИ 👀
- Я ПОСТРОИЛ ДОМ НА СКАЛЕ ЗА 25 СЕКУНД 🪨
- Я ПОСТРОИЛ ДОМ У ОКЕАНА ЗА 20 СЕКУНД 🌊
- Я ПОСТРОИЛ ДОМ В СНЕГУ ЗА 20 СЕКУНД ❄️
"""

import random
from typing import Literal


# ═══════════════════════════════════════════════════════════════════════════
# TITLE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

# House building templates (Mode 8)
HOUSE_TEMPLATES = [
    "Я ПОСТРОИЛ ДОМ {style_variant} С НУЛЯ ЗА {duration} СЕКУНД {emoji}",
    "Я ПОСТРОИЛ {house_type} {location_variant} ЗА {duration} СЕКУНД {emoji}",
    "Я ПОСТРОИЛ {house_type} С НУЛЯ… СМОТРИ 👀",
    "ПОСТРОИЛ {house_type} {location_variant} ЗА {duration} СЕКУНД {emoji}",
    "{house_type} ЗА {duration} СЕКУНД — ЭТО РЕАЛЬНО? {emoji}",
]

# English house building templates (Mode 8)
HOUSE_TEMPLATES_EN = [
    "I BUILT A {house_type} FROM SCRATCH IN {duration} SECONDS {emoji}",
    "BUILT {house_type} IN {duration} SECONDS {emoji}",
    "I BUILT A {house_type} FROM NOTHING... WATCH 👀",
    "{house_type} IN {duration} SECONDS — IS THIS REAL? {emoji}",
    "FROM EMPTY LAND TO {house_type} IN {duration} SECONDS {emoji}",
]

# Vehicle assembly templates (Mode 9)
VEHICLE_TEMPLATES = [
    "Я СОБРАЛ {vehicle_type} {location_variant} ЗА {duration} СЕКУНД {emoji}",
    "Я СОБРАЛ {vehicle_type} С НУЛЯ ЗА {duration} СЕКУНД {emoji}",
    "СОБРАЛ {vehicle_type} ЗА {duration} СЕКУНД 🔧",
    "{vehicle_type} ЗА {duration} СЕКУНД — ШОК! {emoji}",
    "Я СОБРАЛ {vehicle_type}… РЕЗУЛЬТАТ В КОНЦЕ 👀",
]

# English vehicle assembly templates (Mode 9)
VEHICLE_TEMPLATES_EN = [
    "I ASSEMBLED A {vehicle_type} IN {duration} SECONDS {emoji}",
    "ASSEMBLED {vehicle_type} IN {duration} SECONDS {emoji}",
    "I BUILT A {vehicle_type} FROM SCRATCH IN {duration} SECONDS 🔧",
    "{vehicle_type} IN {duration} SECONDS — MIND BLOWN! {emoji}",
    "FROM PARTS TO {vehicle_type} IN {duration} SECONDS {emoji}",
]

# Room restoration / makeover (legacy room timelapse metadata) — style_or_type = room_type key, location = lighting key
ROOM_TEMPLATES = [
    "Я ПРИВЁЛ В ПОРЯДОК {house_type} {location_variant} ЗА {duration} СЕКУНД {emoji}",
    "РЕСТАВРАЦИЯ КОМНАТЫ: {house_type} ЗА {duration} СЕК {emoji}",
    "ИЗ БЕСПОРЯДКА В УЮТ — {house_type} ЗА {duration} СЕК {emoji}",
    "{house_type} ДО И ПОСЛЕ ЗА {duration} СЕК {emoji}",
    "УБОРКА И РЕМОНТ {house_type}… СМОТРИ 👀",
]

ROOM_TEMPLATES_EN = [
    "I TRANSFORMED MY {house_type} {location_variant} IN {duration} SECONDS {emoji}",
    "ROOM MAKEOVER: {house_type} IN {duration} SEC {emoji}",
    "FROM MESS TO COZY — {house_type} IN {duration} SEC {emoji}",
    "{house_type} BEFORE AND AFTER IN {duration} SEC {emoji}",
    "ROOM RESTORATION {house_type}... WATCH 👀",
]

# House type mappings
HOUSE_TYPES = {
    "modern": ("СОВРЕМЕННЫЙ ДОМ", "MODERN HOUSE", "🏠"),
    "contemporary": ("УЛЬТРА-СОВРЕМЕННЫЙ ДОМ", "ULTRA-MODERN HOUSE", "🏠"),
    "minimalist": ("МИНИМАЛИСТИЧНЫЙ ДОМ", "MINIMALIST HOUSE", "🏚️"),
    "scandinavian": ("СКАНДИНАВСКИЙ ДОМ", "SCANDINAVIAN HOUSE", "🏡"),
    "cottage": ("УЮТНЫЙ КОТТЕДЖ", "COZY COTTAGE", "🏘️"),
    "villa": ("РОСКОШНУЮ ВИЛЛУ", "LUXURY VILLA", "🏰"),
    "farmhouse": ("ФЕРМЕРСКИЙ ДОМ", "FARMHOUSE", "🚜"),
    "colonial": ("КОЛОНИАЛЬНЫЙ ОСОБНЯК", "COLONIAL MANSION", "🏛️"),
    "victorian": ("ВИКТОРИАНСКИЙ ДОМ", "VICTORIAN HOUSE", "🏯"),
    "mediterranean": ("СРЕДИЗЕМНОМОРСКУЮ ВИЛЛУ", "MEDITERRANEAN VILLA", "🌴"),
    "cabin": ("ХИЖИНУ В ЛЕСУ", "FOREST CABIN", "🌲"),
    "log_house": ("БОЛЬШОЙ ДЕРЕВЯННЫЙ ДОМ", "LOG HOUSE", "🪵"),
    "chalet": ("АЛЬПИЙСКОЕ ШАЛЕ", "ALPINE CHALET", "🏔️"),
    "adobe": ("ДОМ ИЗ САМАНА", "ADOBE HOUSE", "🏜️"),
    "mansion": ("ОГРОМНЫЙ ОСОБНЯК", "HUGE MANSION", "💎"),
    "estate": ("СЕМЕЙНОЕ ПОМЕСТЬЕ", "FAMILY ESTATE", "🌳"),
}

# Location mappings for houses
HOUSE_LOCATIONS = {
    "suburbs": ("В ПРИГОРОДЕ", "🏙️"),
    "urban_edge": ("НА ОКРАИНЕ ГОРОДА", "🌆"),
    "planned_community": ("В НОВОМ РАЙОНЕ", "🏗️"),
    "forest": ("В ЛЕСУ", "🌲"),
    "wooded_area": ("СРЕДИ ДЕРЕВЬЕВ", "🌳"),
    "seaside": ("У МОРЯ", "🌊"),
    "lakefront": ("НА БЕРЕГУ ОЗЕРА", "🏞️"),
    "riverside": ("НА БЕРЕГУ РЕКИ", "🏖️"),
    "countryside": ("В ДЕРЕВНЕ", "🌾"),
    "farmland": ("СРЕДИ ПОЛЕЙ", "🌻"),
    "vineyard": ("ВИНОГРАДНИКЕ", "🍇"),
    "mountains": ("В ГОРАХ", "⛰️"),
    "hillside": ("НА СКЛОНЕ ГОРЫ", "🪨"),
    "valley": ("В ДОЛИНЕ", "🏕️"),
    "desert": ("В ПУСТЫНЕ", "🌵"),
    "oasis": ("В ОАЗИСЕ", "🌴"),
    "tropical": ("В ТРОПИКАХ", "🌺"),
    "island": ("НА ОСТРОВЕ", "🏝️"),
}

# Vehicle type mappings
VEHICLE_TYPES = {
    "airplane_passenger": ("ПАССАЖИРСКИЙ САМОЛЕТ", "✈️"),
    "airplane_private": ("ЧАСТНЫЙ САМОЛЕТ", "🛩️"),
    "airplane_fighter": ("ИСТРЕБИТЕЛЬ", "🚀"),
    "airplane_cargo": ("ГРУЗОВОЙ САМОЛЕТ", "📦"),
    "helicopter": ("ВЕРТОЛЕТ", "🚁"),
    "drone": ("ПРОМЫШЛЕННЫЙ ДРОН", "🛰️"),
    "seaplane": ("ГИДРОСАМОЛЕТ", "🌊"),
    "car_modern": ("СОВРЕМЕННЫЙ АВТОМОБИЛЬ", "🚗"),
    "car_sport": ("СПОРТИВНУЮ МАШИНУ", "🏎️"),
    "car_suv": ("ВНЕДОРОЖНИК", "🚙"),
    "car_electric": ("ЭЛЕКТРОМОБИЛЬ", "⚡"),
    "truck_cargo": ("ГРУЗОВИК", "🚚"),
    "truck_pickup": ("ПИКАП", "🛻"),
    "bus_city": ("ГОРОДСКОЙ АВТОБУС", "🚌"),
    "tractor": ("ТРАКТОР", "🚜"),
    "excavator": ("ЭКСКАВАТОР", "🏗️"),
    "bulldozer": ("БУЛЬДОЗЕР", "🚜"),
    "crane_construction": ("СТРОИТЕЛЬНЫЙ КРАН", "🏗️"),
    "concrete_mixer": ("БЕТОНОМЕШАЛКУ", "🚒"),
    "road_roller": ("ДОРОЖНЫЙ КАТОК", "🛣️"),
    "loader": ("ПОГРУЗЧИК", "🚜"),
    "ship_cargo": ("ГРУЗОВОЙ КОРАБЛЬ", "🚢"),
    "yacht": ("РОСКОШНУЮ ЯХТУ", "⛵"),
    "fishing_boat": ("РЫБОЛОВЕЦКУЮ ЛОДКУ", "🎣"),
    "submarine": ("ПОДВОДНУЮ ЛОДКУ", "🌊"),
    "ferry": ("ПАРОМ", "⛴️"),
    "wind_turbine": ("ВЕТРЯНУЮ ТУРБИНУ", "💨"),
    "industrial_crane": ("ПРОМЫШЛЕННЫЙ КРАН", "🏭"),
    "industrial_robot": ("РОБОТА-МАНИПУЛЯТОРА", "🤖"),
    "oil_rig": ("НЕФТЯНУЮ ВЫШКУ", "⛽"),
    "solar_farm": ("СОЛНЕЧНУЮ ФЕРМУ", "☀️"),
}

# Location mappings for vehicles
VEHICLE_LOCATIONS = {
    "construction_site": ("НА СТРОЙПЛОЩАДКЕ", "🏗️"),
    "factory": ("НА ЗАВОДЕ", "🏭"),
    "shipyard": ("НА СУДОСТРОИТЕЛЬНОМ ЗАВОДЕ", "🚢"),
    "hangar": ("В АНГАРЕ", "🛫"),
    "industrial_zone": ("В ПРОМЗОНЕ", "🏭"),
    "empty_field": ("В ЧИСТОМ ПОЛЕ", "🌾"),
    "forest_clearing": ("НА ПОЛЯНЕ", "🌲"),
    "desert": ("В ПУСТЫНЕ", "🌵"),
    "mountain_valley": ("В ГОРНОЙ ДОЛИНЕ", "⛰️"),
    "snowy_plain": ("В СНЕЖНОЙ РАВНИНЕ", "❄️"),
    "city_outskirts": ("НА ОКРАИНЕ ГОРОДА", "🌆"),
    "parking_lot": ("НА ПАРКОВКЕ", "🅿️"),
    "abandoned_industrial": ("НА ЗАБРОШЕННОМ ЗАВОДЕ", "🏚️"),
    "building_roof": ("НА КРЫШЕ", "🏢"),
    "ocean_coast": ("НА БЕРЕГУ ОКЕАНА", "🌊"),
    "floating_platform": ("НА ПЛАТФОРМЕ", "⚓"),
    "island": ("НА ОСТРОВЕ", "🏝️"),
    "quarry": ("В КАРЬЕРЕ", "🪨"),
    "port": ("В ПОРТУ", "⚓"),
}

# Room type (accusative RU for templates like «привёл в порядок СПАЛЬНЮ»)
ROOM_CLICKBAIT_TYPES = {
    "studio": ("СТУДИЮ", "STUDIO APARTMENT", "🏠"),
    "bedroom": ("СПАЛЬНЮ", "BEDROOM", "🛏️"),
    "living": ("ГОСТИНУЮ", "LIVING ROOM", "🛋️"),
    "kitchen": ("КУХНЮ", "KITCHEN", "🍳"),
    "kids": ("ДЕТСКУЮ", "KIDS ROOM", "🧸"),
    "loft": ("ЛОФТ", "LOFT SPACE", "🏭"),
}

# Lighting / mood phrase for room titles
ROOM_LIGHTING_CLICKBAIT = {
    "morning_soft": ("С УТРЕННИМ СВЕТОМ", "IN SOFT MORNING LIGHT", "☀️"),
    "daylight_neutral": ("В ДНЕВНОМ СВЕТЕ", "IN DAYLIGHT", "🌤️"),
    "golden_hour": ("В ЗОЛОТОМ СВЕТЕ", "AT GOLDEN HOUR", "🌅"),
    "warm_lamps": ("ПРИ ТЁПЛОМ СВЕТЕ ЛАМП", "WITH WARM LAMPS", "💡"),
    "overcast_soft": ("В РАССЕЯННОМ СВЕТЕ", "IN SOFT OVERCAST", "☁️"),
}


def _round_duration(seconds: float) -> int:
    """
    Round duration to nearest 5 seconds for catchy titles.
    
    Rules:
    - < 5 sec → 5 sec
    - 5-10 sec → round to 5
    - 10-30 sec → round to nearest 5
    - > 30 sec → round to nearest 10
    """
    if seconds < 5:
        return 5
    elif seconds <= 30:
        return round(seconds / 5) * 5
    else:
        return round(seconds / 10) * 10


def generate_clickbait_title(
    content_type: Literal["house", "vehicle", "room"],
    style_or_type: str,
    location: str,
    duration_seconds: float,
    language: Literal["ru", "en"] = "ru",  # NEW parameter
) -> str:
    """
    Generate a clickbait title with real video duration.
    
    Args:
        content_type: "house" for Mode8, "vehicle" for Mode9, "room" for Mode12
        style_or_type: House style, vehicle type, or room type key (e.g. bedroom)
        location: Location (house/vehicle) or room lighting key (Mode12)
        duration_seconds: Real final video duration in seconds
        language: Title language ("ru" or "en")
        
    Returns:
        Clickbait title in specified language
    """
    # Round duration for catchiness
    rounded_duration = _round_duration(duration_seconds)
    
    if content_type == "house":
        # Select templates based on language
        templates = HOUSE_TEMPLATES if language == "ru" else HOUSE_TEMPLATES_EN
        type_mapping = HOUSE_TYPES
        location_mapping = HOUSE_LOCATIONS
        default_emoji = "🏠"
    elif content_type == "room":
        templates = ROOM_TEMPLATES if language == "ru" else ROOM_TEMPLATES_EN
        type_mapping = ROOM_CLICKBAIT_TYPES
        location_mapping = ROOM_LIGHTING_CLICKBAIT
        default_emoji = "🏠"
    else:  # vehicle
        # Select templates based on language
        templates = VEHICLE_TEMPLATES if language == "ru" else VEHICLE_TEMPLATES_EN
        type_mapping = VEHICLE_TYPES
        location_mapping = VEHICLE_LOCATIONS
        default_emoji = "🚗"
    
    # Get type name and emoji
    type_info = type_mapping.get(style_or_type.lower(), (style_or_type.upper(), style_or_type.upper(), default_emoji))
    if language == "ru":
        type_name = type_info[0]  # Russian name
    else:
        type_name = type_info[1]  # English name
    type_emoji = type_info[2]
    
    # Get location variant (room lighting uses triples: RU, EN, emoji)
    loc_info = location_mapping.get(location.lower())
    if loc_info is None:
        if content_type == "room":
            loc_info = (
                f"СВЕТОМ {location.upper().replace('_', ' ')}",
                f"IN {location.upper().replace('_', ' ')} LIGHT",
                "📍",
            )
        else:
            loc_info = (f"В {location.upper()}", "📍")
    if content_type == "room" and len(loc_info) >= 3:
        if language == "ru":
            location_text = loc_info[0]
            location_emoji = loc_info[2]
        else:
            location_text = loc_info[1]
            location_emoji = loc_info[2]
    else:
        location_text = loc_info[0]
        location_emoji = loc_info[1] if len(loc_info) > 1 else "📍"
    
    # Choose template randomly
    template = random.choice(templates)
    
    # Build style variant (house templates only)
    style_variant = ""
    if content_type == "house":
        if language == "ru":
            if style_or_type.lower() in ["modern", "contemporary", "minimalist"]:
                style_variant = f"({type_name})"
            elif style_or_type.lower() in ["villa", "mansion", "estate"]:
                style_variant = "РОСКОШНЫЙ"
            elif style_or_type.lower() in ["cottage", "cabin", "chalet"]:
                style_variant = "УЮТНЫЙ"
        else:
            if style_or_type.lower() in ["modern", "contemporary", "minimalist"]:
                style_variant = f"({type_name})"
            elif style_or_type.lower() in ["villa", "mansion", "estate"]:
                style_variant = "LUXURY"
            elif style_or_type.lower() in ["cottage", "cabin", "chalet"]:
                style_variant = "COZY"
    
    # Fill template
    title = template.format(
        house_type=type_name,
        vehicle_type=type_name,  # Support both keys
        style_variant=style_variant,
        location_variant=location_text,
        duration=rounded_duration,
        emoji=type_emoji if "{emoji}" in template else "",
    )
    
    return title


# ═══════════════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test Mode 8 (House Building)
    print("=== MODE 8 EXAMPLES ===")
    for i in range(5):
        title = generate_clickbait_title(
            content_type="house",
            style_or_type="villa",
            location="desert",
            duration_seconds=23.7,
        )
        print(f"{i+1}. {title}")
    
    print("\n=== MODE 9 EXAMPLES ===")
    for i in range(5):
        title = generate_clickbait_title(
            content_type="vehicle",
            style_or_type="car_sport",
            location="factory",
            duration_seconds=28.3,
        )
        print(f"{i+1}. {title}")

    print("\n=== MODE 12 (ROOM) EXAMPLES ===")
    for i in range(5):
        title = generate_clickbait_title(
            content_type="room",
            style_or_type="bedroom",
            location="golden_hour",
            duration_seconds=32.0,
        )
        print(f"{i+1}. {title}")
