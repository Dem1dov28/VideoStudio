"""
Mode 9 Scenario Writer — Vehicle Assembly Timelapse.

Generates sequential assembly stages for vehicle construction timelapse video.
Each stage represents a transformation from state A to state B.

Enhancements based on Mode8 improvements:
- Detailed vehicle descriptions with visual details and typical features
- Enhanced locations with atmosphere, dynamic features, camera recommendations
- Fixed camera specifications for consistent drone/static views
- State tracking flags for assembly progression validation
- Structured visual prompts with consistency rules
- Support for 5-8 assembly stages with proper sequences
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel

from modes.mode9.architectural_variations import (
    get_vehicle_variation,
    build_varied_visual_prompt,
)


# ═══════════════════════════════════════════════════════════════════════════
# CAMERA SPECIFICATIONS (Fixed for consistency across all stages)
# ═══════════════════════════════════════════════════════════════════════════

CAMERA_SPECS: dict[str, dict[str, str]] = {
    "static_side_elevated": {
        "name": "static side elevated view",
        "description": "camera positioned at 90-degree side angle, 30 meters distance, 12 meters elevation, capturing FULL vehicle profile",
        "lens": "35mm equivalent, moderate wide angle",
        "height": "12-15 meters above ground",
        "angle": "15-degree downward angle",
        "distance": "30-35 meters from vehicle",
        "framing": "vehicle occupies 50% of frame horizontally, ENTIRE vehicle fully visible",
        "movement": "STATIC - no camera movement between stages",
        "best_for": ["factory", "hangar", "construction_site", "industrial_zone"],
    },
    "static_front_quarter": {
        "name": "static front three-quarter view",
        "description": "camera positioned at 45-degree front angle, 35 meters distance, 10 meters elevation, capturing front and side",
        "lens": "35mm equivalent, moderate wide angle",
        "height": "10-12 meters above ground",
        "angle": "10-degree downward angle",
        "distance": "35-40 meters from vehicle",
        "framing": "vehicle occupies 45% of frame, ENTIRE vehicle front and side visible",
        "movement": "STATIC - no camera movement between stages",
        "best_for": ["factory", "hangar", "parking_lot", "building_roof"],
    },
    "drone_elevated": {
        "name": "elevated drone overview",
        "description": "drone positioned at 30-degree angle, 50 meters distance, 25 meters elevation, bird's eye perspective",
        "lens": "28mm equivalent, wide angle",
        "height": "25-30 meters above ground",
        "angle": "30-degree downward angle",
        "distance": "50-60 meters from vehicle",
        "framing": "vehicle occupies 40% of frame, ENTIRE vehicle visible with surroundings",
        "movement": "STATIC - no camera movement between stages",
        "best_for": ["empty_field", "desert", "ocean_coast", "mountain_valley", "construction_site"],
    },
    "ground_level_pan": {
        "name": "ground level panoramic view",
        "description": "camera at ground level, 40 meters distance, capturing vehicle against landscape backdrop",
        "lens": "50mm equivalent, standard",
        "height": "3-4 meters above ground",
        "angle": "5-degree upward angle",
        "distance": "40-50 meters from vehicle",
        "framing": "vehicle occupies 50% of frame, ENTIRE vehicle visible, landscape background prominent",
        "movement": "STATIC - no camera movement between stages",
        "best_for": ["empty_field", "desert", "mountain_valley", "snowy_plain"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LOCATION DYNAMIC FEATURES (Interactive elements for each location type)
# ═══════════════════════════════════════════════════════════════════════════

LOCATION_DYNAMIC_FEATURES: dict[str, dict[str, Any]] = {
    "factory": {
        "environment_interaction": "assembly line and conveyor systems visible, robotic arms in background",
        "visible_elements": ["конвейерная лента", "промышленные роботы", "подъёмные краны", "освещение цеха", "организованные стеллажи"],
        "assembly_context": "professional factory environment with organized workflow",
        "camera_recommendation": "static_side_elevated",
        "full_vehicle_visibility": "vehicle fully visible from elevated side angle, factory floor extends behind",
        "dynamic_description": "сборка происходит в современном цеху с конвейером и роботами на заднем плане",
    },
    "hangar": {
        "environment_interaction": "high ceiling with metal trusses, specialized aviation equipment, runway visible through doors",
        "visible_elements": ["металлические фермы потолка", "авиационное оборудование", "взлётная полоса вдали", "освещение через окна", "инструменты на стенах"],
        "assembly_context": "aviation hangar with massive space for large vehicle assembly",
        "camera_recommendation": "static_front_quarter",
        "full_vehicle_visibility": "vehicle fully visible with hangar depth showing behind",
        "dynamic_description": "сборка в просторном авиационном ангаре с видом на взлётную полосу",
    },
    "shipyard": {
        "environment_interaction": "dry dock or water visible, massive cranes, other vessels in background, maritime atmosphere",
        "visible_elements": ["сухой док или вода", "портальные краны", "другие суда", "причал", "морской горизонт"],
        "assembly_context": "maritime shipyard with water access and heavy lifting equipment",
        "camera_recommendation": "drone_elevated",
        "full_vehicle_visibility": "vessel fully visible from elevated angle with water/dock in background",
        "dynamic_description": "сборка на судостроительной верфи с видом на воду и портовые краны",
    },
    "construction_site": {
        "environment_interaction": "tower cranes, building materials, unfinished structures, urban skyline in distance",
        "visible_elements": ["башенные краны", "строительные материалы", "незаконченные конструкции", "городской силуэт", "строительная техника"],
        "assembly_context": "active construction site with ongoing building work",
        "camera_recommendation": "drone_elevated",
        "full_vehicle_visibility": "vehicle fully visible with construction activity in background",
        "dynamic_description": "сборка на активной строительной площадке с кранами и городом на заднем плане",
    },
    "empty_field": {
        "environment_interaction": "open sky, grass field, distant trees, natural horizon",
        "visible_elements": ["открытое небо", "зелёная трава", "деревья на горизонте", "холмы", "естественное освещение"],
        "assembly_context": "open outdoor space with natural surroundings",
        "camera_recommendation": "ground_level_pan",
        "full_vehicle_visibility": "vehicle fully visible against open landscape",
        "dynamic_description": "сборка на открытом поле с панорамным видом на природу и горизонт",
    },
    "ocean_coast": {
        "environment_interaction": "waves, beach, rocks, seagulls, ocean horizon, salty breeze atmosphere",
        "visible_elements": ["волны", "песчаный пляж", "скалы", "чайки", "океанский горизонт", "прибой"],
        "assembly_context": "coastal location with maritime atmosphere",
        "camera_recommendation": "drone_elevated",
        "full_vehicle_visibility": "vehicle fully visible with ocean and beach in background",
        "dynamic_description": "сборка на побережье океана с видом на волны и пляж",
    },
    "desert": {
        "environment_interaction": "sand dunes, sparse vegetation, bright sun, sharp shadows, extreme heat atmosphere",
        "visible_elements": ["песчаные дюны", "кактусы", "резкие тени", "яркое солнце", "пустынный пейзаж"],
        "assembly_context": "desert environment with extreme conditions",
        "camera_recommendation": "drone_elevated",
        "full_vehicle_visibility": "vehicle fully visible against desert landscape",
        "dynamic_description": "сборка в пустынной местности среди песчаных дюн и яркого солнца",
    },
    "mountain_valley": {
        "environment_interaction": "mountain peaks, valley floor, river, pine forest, majestic scenery",
        "visible_elements": ["горные пики", "долина", "река", "хвойный лес", "величественные виды"],
        "assembly_context": "mountain valley with dramatic elevation and scenery",
        "camera_recommendation": "ground_level_pan",
        "full_vehicle_visibility": "vehicle fully visible with mountains towering behind",
        "dynamic_description": "сборка в горной долине с величественными пиками и хвойным лесом",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# VEHICLE TYPES (Enhanced with detailed descriptions)
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_TYPES: dict[str, dict[str, Any]] = {
    # ✈️ АВИАЦИЯ
    "airplane_passenger": {
        "name": "пассажирский самолёт",
        "name_en": "passenger airplane",
        "description": "Крупное пассажирское воздушное судно для коммерческих авиаперевозок. Многочисленные иллюминаторы вдоль фюзеляжа, мощные реактивные двигатели под крыльями, хвостовое оперение с логотипом авиакомпании. Исторически важный тип транспорта соединяющий континенты.",
        "visual": "пассажирский самолёт с металлическим фюзеляжем, крылья с закрылками и элеронами, хвостовое оперение с килем и стабилизаторами, четыре или два реактивных двигателя под крыльями, множество иллюминаторов в два ряда",
        "materials": "авиационный алюминий, титановые сплавы, композитные материалы, высокопрочная сталь, закалённое стекло иллюминаторов",
        "typical_features": ["многочисленные иллюминаторы", "реактивные двигатели", "хвостовое оперение", "шасси с множеством колёс", "кабина пилотов", "грузовой отсек"],
        "setting": "авиационный ангар, взлётная полоса на заднем плане",
        "setting_en": "aviation hangar, runway in background",
    },
    "airplane_private": {
        "name": "частный джет",
        "name_en": "private jet",
        "visual": "роскошный частный самолёт, обтекаемый фюзеляж, небольшие крылья, спойлеры",
        "materials": "композитные материалы, алюминий, кожа салона",
        "setting": "частный аэропорт, ангар для джетов",
        "setting_en": "private airport, jet hangar",
    },
    "airplane_fighter": {
        "name": "военный истребитель",
        "name_en": "fighter jet",
        "visual": "военный самолёт, треугольные крылья, реактивный двигатель, камуфляжная окраска",
        "materials": "титан, алюминий, композиты, сталь",
        "setting": "военный ангар, взлётно-посадочная полоса",
        "setting_en": "military hangar, airbase runway",
    },
    "airplane_cargo": {
        "name": "грузовой самолёт",
        "name_en": "cargo airplane",
        "visual": "крупный грузовой самолёт, широкий фюзеляж, грузовая дверь, мощные двигатели",
        "materials": "сталь, алюминий, композиты",
        "setting": "грузовой терминал аэропорта, складская зона",
        "setting_en": "cargo terminal, warehouse zone",
    },
    "helicopter": {
        "name": "вертолёт",
        "name_en": "helicopter",
        "visual": "вертолёт с большим несущим винтом, хвостовой винт, кабина пилота, шасси",
        "materials": "алюминий, композиты, сталь, стекло",
        "setting": "вертолётная площадка, ангар",
        "setting_en": "helipad, hangar",
    },
    "drone": {
        "name": "промышленный дрон",
        "name_en": "industrial drone",
        "visual": "большой квадрокоптер, промышленные пропеллеры, камера, сенсоры",
        "materials": "карбон, пластик, алюминий",
        "setting": "лаборатория дронов, испытательная площадка",
        "setting_en": "drone lab, testing area",
    },
    "seaplane": {
        "name": "гидросамолёт",
        "name_en": "seaplane",
        "visual": "самолёт с поплавками вместо шасси, корпус для посадки на воду",
        "materials": "алюминий, композиты, нержавеющая сталь",
        "setting": "причал, водная станция",
        "setting_en": "dock, water station",
    },
    # 🚗 АВТОМОБИЛИ
    "car_modern": {
        "name": "современный автомобиль",
        "name_en": "modern car",
        "visual": "современный седан, обтекаемый кузов, светодиодные фары, легкосплавные диски",
        "materials": "сталь, алюминий, пластик, стекло",
        "setting": "автомобильный завод, сборочный цех",
        "setting_en": "car factory, assembly plant",
    },
    "car_sport": {
        "name": "спортивный автомобиль",
        "name_en": "sports car",
        "visual": "низкий спортивный автомобиль, агрессивный дизайн, большие колёса, спойлер",
        "materials": "карбон, алюминий, кожа",
        "setting": "спорткар завод, гоночная мастерская",
        "setting_en": "sportscar factory, racing workshop",
    },
    "car_suv": {
        "name": "внедорожник",
        "name_en": "SUV",
        "visual": "крупный внедорожник, высокий клиренс, массивные колёса, рейлинги на крыше",
        "materials": "сталь, алюминий, пластик",
        "setting": "завод внедорожников, сборочная линия",
        "setting_en": "SUV factory, assembly line",
    },
    "car_electric": {
        "name": "электромобиль",
        "name_en": "electric vehicle",
        "visual": "футуристичный электромобиль, гладкий кузов, скрытая решётка радиатора",
        "materials": "алюминий, композиты, литиевые батареи",
        "setting": "завод электромобилей, чистый цех",
        "setting_en": "EV factory, clean room",
    },
    "truck_cargo": {
        "name": "грузовик",
        "name_en": "cargo truck",
        "visual": "большой грузовик, кабина, грузовой отсек, много колёс",
        "materials": "сталь, алюминий, резина",
        "setting": "завод грузовиков, промышленная зона",
        "setting_en": "truck factory, industrial zone",
    },
    "truck_pickup": {
        "name": "пикап",
        "name_en": "pickup truck",
        "visual": "пикап с открытой платформой, мощные колёса, прочная рама",
        "materials": "сталь, алюминий, пластик",
        "setting": "завод пикапов, сборочный цех",
        "setting_en": "pickup factory, assembly plant",
    },
    "bus_city": {
        "name": "городской автобус",
        "name_en": "city bus",
        "visual": "длинный автобус, много окон, двери для пассажиров",
        "materials": "сталь, алюминий, стекло",
        "setting": "автобусный завод, сборочная линия",
        "setting_en": "bus factory, assembly line",
    },
    # 🚜 СПЕЦТЕХНИКА
    "tractor": {
        "name": "трактор",
        "name_en": "tractor",
        "visual": "мощный трактор, большие колёса с грубым протектором, кабина, фаркоп",
        "materials": "сталь, чугун, резина",
        "setting": "завод тракторов, сельскохозяйственный цех",
        "setting_en": "tractor factory, agricultural plant",
    },
    "excavator": {
        "name": "экскаватор",
        "name_en": "excavator",
        "visual": "строительный экскаватор, длинная стрела, ковш, гусеницы или колёса",
        "materials": "сталь, гидравлика, резина",
        "setting": "завод спецтехники, строительная площадка",
        "setting_en": "construction machinery plant, building site",
    },
    "bulldozer": {
        "name": "бульдозер",
        "name_en": "bulldozer",
        "visual": "мощный бульдозер, большой отвал спереди, гусеницы",
        "materials": "сталь, гидравлика, чугун",
        "setting": "завод бульдозеров, карьер",
        "setting_en": "bulldozer factory, quarry",
    },
    "crane_construction": {
        "name": "подъёмный кран",
        "name_en": "construction crane",
        "visual": "высокий строительный кран, длинная стрела, противовес, кабина оператора",
        "materials": "сталь, гидравлика, электроника",
        "setting": "строительная площадка, завод кранов",
        "setting_en": "construction site, crane factory",
    },
    "concrete_mixer": {
        "name": "бетономешалка",
        "name_en": "concrete mixer",
        "visual": "грузовик с вращающимся барабаном, шасси, разгрузочный желоб",
        "materials": "сталь, гидравлика, резина",
        "setting": "завод бетономешалок, бетонный узел",
        "setting_en": "concrete mixer factory, batching plant",
    },
    "road_roller": {
        "name": "дорожный каток",
        "name_en": "road roller",
        "visual": "дорожный каток, большой металлический валик, кабина оператора",
        "materials": "сталь, гидравлика, резина",
        "setting": "завод дорожной техники, строительство дорог",
        "setting_en": "road machinery factory, road construction",
    },
    "loader": {
        "name": "погрузчик",
        "name_en": "loader",
        "visual": "фронтальный погрузчик, ковш спереди, шарнирно-сочленённая рама",
        "materials": "сталь, гидравлика, резина",
        "setting": "завод погрузчиков, склад",
        "setting_en": "loader factory, warehouse",
    },
    # 🚢 ТРАНСПОРТ
    "ship_cargo": {
        "name": "грузовой корабль",
        "name_en": "cargo ship",
        "visual": "большое грузовое судно, контейнеры на палубе, мостик",
        "materials": "сталь, алюминий, композиты",
        "setting": "верфь, док, порт",
        "setting_en": "shipyard, dock, port",
    },
    "yacht": {
        "name": "яхта",
        "name_en": "yacht",
        "visual": "роскошная яхта, гладкий корпус, мачты, палуба",
        "materials": "стеклопластик, алюминий, тик",
        "setting": "яхтенная верфь, марина",
        "setting_en": "yacht yard, marina",
    },
    "fishing_boat": {
        "name": "рыболовное судно",
        "name_en": "fishing boat",
        "visual": "рыболовецкое судно, сети, лебёдки, рыбный трюм",
        "materials": "сталь, алюминий, нейлон",
        "setting": "рыболовная верфь, рыбацкий порт",
        "setting_en": "fishing yard, fishing port",
    },
    "submarine": {
        "name": "подводная лодка",
        "name_en": "submarine",
        "visual": "подводная лодка, цилиндрический корпус, рубка, винты",
        "materials": "специальная сталь, титан, композиты",
        "setting": "подводная верфь, сухой док",
        "setting_en": "submarine yard, dry dock",
    },
    "ferry": {
        "name": "паром",
        "name_en": "ferry",
        "visual": "пассажирский паром, несколько палуб, трапы, окна",
        "materials": "сталь, алюминий, стекло",
        "setting": "паромная верфь, портовая зона",
        "setting_en": "ferry yard, port zone",
    },
    # 💨 ИНДУСТРИЯ
    "wind_turbine": {
        "name": "ветряная турбина",
        "name_en": "wind turbine",
        "visual": "высокая ветряная турбина, три больших лопасти, генератор",
        "materials": "сталь, композиты, медь",
        "setting": "ветряная ферма, производственная площадка",
        "setting_en": "wind farm, production site",
    },
    "industrial_crane": {
        "name": "промышленный кран",
        "name_en": "industrial crane",
        "visual": "массивный промышленный кран, балки, лебёдки, кабина",
        "materials": "сталь, гидравлика, электроника",
        "setting": "промышленный завод, цех тяжёлого машиностроения",
        "setting_en": "industrial plant, heavy machinery workshop",
    },
    "industrial_robot": {
        "name": "промышленный робот",
        "name_en": "industrial robot",
        "description": "Промышленный робот-манипулятор для автоматизации производственных процессов. Многосуставная рука с захватом, панель управления, точное позиционирование. Будущее автоматизации производства.",
        "visual": "промышленный робот-манипулятор с несколькими суставами руки, различные типы захватов на конце, панель управления с дисплеем, основание на платформе или подвешенный к потолку, кабели питания",
        "materials": "алюминиевые сплавы корпуса, сервомоторы в суставах, электронные контроллеры, редукторы, гибкие кабели",
        "typical_features": ["суставы руки", "захват", "панель управления", "сервомоторы", "точное позиционирование", "программируемый"],
        "setting": "завод роботов, автоматизированный цех",
        "setting_en": "robotics factory, automated workshop",
    },
    "oil_rig": {
        "name": "буровая установка",
        "name_en": "oil rig",
        "description": "Нефтяная буровая вышка для добычи нефти и газа. Высокая башня с буровой колонной, насосы, платформы. Индустриальный гигант добывающей отрасли.",
        "visual": "высокая нефтяная вышка с буровой колонной и талевой системой, насосные установки, платформы для обслуживания, трубопроводы, резервуары, жилые модули для персонала",
        "materials": "высокопрочная сталь конструкции, специальные сплавы для агрессивной среды, буровые трубы, гидравлические системы",
        "typical_features": ["буровая башня", "буровая колонна", "насосы", "платформы", "трубопроводы", "резервуары"],
        "setting": "нефтяное месторождение, буровая площадка",
        "setting_en": "oil field, drilling site",
    },
    "solar_farm": {
        "name": "солнечная панельная ферма",
        "name_en": "solar panel farm",
        "description": "Солнечная электростанция с множеством фотоэлектрических панелей на металлических опорах. Инверторы, кабели, система отслеживания солнца. Чистая зелёная энергия.",
        "visual": "ряды солнечных панелей на металлических опорах под углом к солнцу, инверторные станции, кабельные лотки, система отслеживания солнца, трансформаторная подстанция, ограждение",
        "materials": "кремниевые панели, алюминиевые опоры, закалённое стекло, медные кабели, инверторы, бетонные фундаменты",
        "typical_features": ["солнечные панели", "металлические опоры", "инверторы", "кабели", "отслеживание солнца", "трансформатор"],
        "setting": "солнечная электростанция, пустыня",
        "setting_en": "solar power plant, desert",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LOCATIONS / SETTINGS (Enhanced with descriptions, atmosphere, dynamic features)
# ═══════════════════════════════════════════════════════════════════════════

# Note: LOCATION_DYNAMIC_FEATURES is defined at the end of this file
# and imported here to avoid circular reference

LOCATIONS: dict[str, dict[str, Any]] = {
    # 🏗️ ИНДУСТРИАЛЬНЫЕ
    "construction_site": {
        "name": "строительная площадка",
        "name_en": "construction site",
        "description": "Активная строительная площадка с башенными кранами, строительными материалами и техникой. Городской пейзаж на заднем плане, динамичная атмосфера постоянного движения.",
        "visual": "строительная площадка с бетонным основанием, башенные краны на фоне, строительные материалы аккуратно сложены, техника для работы, ограждение по периметру",
        "background": "небоскрёбы на горизонте, другие строящиеся объекты, городской пейзаж, строительная техника в работе",
        "background_en": "skyscrapers on horizon, other construction projects, cityscape, construction machinery at work",
        "atmosphere": "динамичная, строительная, промышленная, активная",
        "typical_elements": ["башенные краны", "строительные материалы", "техника", "ограждение", "бетонное основание", "рабочие", "городской силуэт"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},  # Will be populated after LOCATION_DYNAMIC_FEATURES is defined
    },
    "factory": {
        "name": "завод / производственный цех",
        "name_en": "factory / production workshop",
        "description": "Современный сборочный цех с конвейерной линией, промышленными роботами-манипуляторами и организованным рабочим пространством. Чистая промышленная среда с хорошим освещением.",
        "visual": "современный сборочный цех с высоким потолком, конвейерная линия проходит через центр, промышленные роботы на постах, стеллажи с запчастями, яркое освещение",
        "background": "роботы-манипуляторы на заднем плане, конвейерная лента, запчасти на стеллажах, промышленное оборудование, рабочие в униформе",
        "background_en": "robotic arms in background, conveyor belt, parts on shelves, industrial equipment, workers in uniform",
        "atmosphere": "промышленная, организованная, технологичная, чистая",
        "typical_elements": ["конвейер", "роботы", "стеллажи", "освещение", "рабочие", "оборудование", "организованное пространство"],
        "camera_recommendation": "static_side_elevated",
        "dynamic_features": {},
    },
    "shipyard": {
        "name": "верфь",
        "name_en": "shipyard",
        "description": "Судостроительная верфь с сухими доками, стапелями и мощными подъёмными кранами. Морская вода, промышленная атмосфера, масштабные операции по сборке судов.",
        "visual": "судостроительная верфь с сухим доком или водой, массивные портальные краны, стапели для сборки, корпуса судов на разных стадиях, промышленные здания верфи",
        "background": "корабли и суда на разных стадиях сборки, морская вода в доке, портовые краны, горизонт с морем",
        "background_en": "ships at various assembly stages, sea water in dock, port cranes, horizon with sea",
        "atmosphere": "морская, промышленная, масштабная, историческая",
        "typical_elements": ["сухой док", "краны", "корпуса судов", "вода", "стапели", "верфские здания", "причал"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "hangar": {
        "name": "авиационный ангар",
        "name_en": "aviation hangar",
        "description": "Большой промышленный ангар с высоким потолком, металлическими фермами и специализированным оборудованием для авиации. Просторное помещение для сборки и обслуживания летательных аппаратов.",
        "visual": "большой промышленный ангар с высоким потолком и металлическими фермами, массивные ворота, подъёмные краны под потолком, инструменты на стенах, яркое освещение",
        "background": "инструменты на стенах, подъёмные краны, авиационное оборудование, взлётная полоса видна через открытые ворота, другие летательные аппараты",
        "background_en": "tools on walls, overhead cranes, aviation equipment, runway visible through open doors, other aircraft",
        "atmosphere": "просторная, промышленная, специализированная, точная",
        "typical_elements": ["металлические фермы", "высокий потолок", "краны", "инструменты", "оборудование", "ворота", "освещение"],
        "camera_recommendation": "static_front_quarter",
        "dynamic_features": {},
    },
    "industrial_zone": {
        "name": "индустриальная зона",
        "name_en": "industrial zone",
        "description": "Промышленная зона с заводами, дымящими трубами и складами. Интенсивная производственная деятельность, грузовики, краны. Сердце промышленности.",
        "visual": "промышленная зона с заводскими корпусами, дымящие трубы на фоне, склады, грузовики на территории, краны, железнодорожные пути",
        "background": "дымящие трубы заводов, грузовики на манёврах, погрузочные краны, железнодорожные вагоны, промышленные здания",
        "background_en": "smoking factory pipes, trucks maneuvering, loading cranes, railway cars, industrial buildings",
        "atmosphere": "промышленная, активная, производственная, масштабная",
        "typical_elements": ["заводы", "трубы", "склады", "грузовики", "краны", "железная дорога", "промышленные здания"],
        "camera_recommendation": "static_side_elevated",
        "dynamic_features": {},
    },
    # 🌿 ПРИРОДА
    "empty_field": {
        "name": "пустое поле",
        "name_en": "empty field",
        "description": "Открытое поле с зелёной травой и чистым небом. Простор, естественное освещение, горизонт с деревьями. Идеально для демонстрации крупной техники в естественных условиях.",
        "visual": "открытое поле с зелёной травой, ровная поверхность для сборки, чистое голубое небо, естественное солнечное освещение, далёкий горизонт",
        "background": "деревья на горизонте, холмы вдали, облака в небе, естественный пейзаж, возможно сельскохозяйственные поля",
        "background_en": "trees on horizon, hills in distance, clouds in sky, natural landscape, possibly agricultural fields",
        "atmosphere": "открытая, естественная, просторная, свободная",
        "typical_elements": ["трава", "небо", "горизонт", "деревья", "холмы", "солнце", "пространство"],
        "camera_recommendation": "ground_level_pan",
        "dynamic_features": {},
    },
    "forest_clearing": {
        "name": "лесная поляна",
        "name_en": "forest clearing",
        "description": "Поляна в лесу с деревьями по периметру и естественным освещением. Уединённое место для сборки, гармония с природой, свежий воздух.",
        "visual": "поляна в лесу с ровной площадкой для сборки, высокие деревья окружают поляну по периметру, естественное освещение сквозь кроны, зелёная трава",
        "background": "высокие деревья по краям поляны, кустарники, лесная чаща, пение птиц, естественная тишина",
        "background_en": "tall trees at clearing edges, bushes, forest thicket, birdsong, natural silence",
        "atmosphere": "уединённая, природная, тихая, свежая",
        "typical_elements": ["деревья", "поляна", "трава", "кустарники", "лес", "природа", "тишина"],
        "camera_recommendation": "ground_level_pan",
        "dynamic_features": {},
    },
    "desert": {
        "name": "пустыня",
        "name_en": "desert",
        "description": "Песчаная пустыня с дюнами и ярким солнцем. Резкие тени, экстремальные условия, минимум растительности. Испытание техники в суровых условиях.",
        "visual": "песчаная пустыня с дюнами, ровная площадка для сборки утрамбована, яркое солнце создаёт резкие тени, сухой климат, кактусы и редкие кустарники",
        "background": "песчаные дюны на горизонте, редкие кактусы, яркое солнце, голубое небо без облаков, сухой воздух",
        "background_en": "sand dunes on horizon, rare cacti, bright sun, cloudless blue sky, dry air",
        "atmosphere": "экстремальная, яркая, безмолвная, сухая",
        "typical_elements": ["песок", "дюны", "солнце", "кактусы", "тень", "жара", "пустынный пейзаж"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "mountain_valley": {
        "name": "горная долина",
        "name_en": "mountain valley",
        "description": "Долина между горами со скалистыми вершинами и возможно рекой. Чистый воздух, величественные пейзажи, ощущение масштаба и величия природы.",
        "visual": "долина между горами с ровной площадкой для сборки, скалистые вершины возвышаются по сторонам, возможно река или ручей, хвойный лес на склонах",
        "background": "высокие горные пики со снегом, облака окутывают вершины, хвойный лес на склонах, чистый воздух, величественные виды",
        "background_en": "high mountain peaks with snow, clouds around summits, coniferous forest on slopes, clean air, majestic views",
        "atmosphere": "величественная, чистая, вдохновляющая, свежая",
        "typical_elements": ["горы", "пики", "долина", "река", "лес", "скалы", "облака"],
        "camera_recommendation": "ground_level_pan",
        "dynamic_features": {},
    },
    "snowy_plain": {
        "name": "снежная равнина",
        "name_en": "snowy plain",
        "description": "Заснеженная равнина с белым снегом и холодным небом. Зимние условия, сугробы, ледяные образования. Красота зимнего пейзажа.",
        "visual": "заснеженная равнина с утрамбованной площадкой для сборки, белый снег покрывает всё вокруг, холодное зимнее небо, возможны сугробы по краям",
        "background": "сугробы, ледяные образования, голые деревья на горизонте, серое зимнее небо, снежный пейзаж",
        "background_en": "snowdrifts, ice formations, bare trees on horizon, gray winter sky, snowy landscape",
        "atmosphere": "холодная, чистая, тихая, зимняя",
        "typical_elements": ["снег", "сугробы", "лед", "холод", "зима", "белый пейзаж", "небо"],
        "camera_recommendation": "ground_level_pan",
        "dynamic_features": {},
    },
    # 🌆 УРБАН
    "city_outskirts": {
        "name": "городская окраина",
        "name_en": "city outskirts",
        "description": "Окраина города с зданиями на горизонте и дорогами. Переходная зона между городом и природой, инфраструктура, развитие.",
        "visual": "окраина города с открытой площадкой для сборки, здания виднеются на горизонте, дороги и инфраструктура, застройка вдали",
        "background": "городской силуэт на горизонте, шоссе с движением, новостройки, промышленные объекты, развивающаяся инфраструктура",
        "background_en": "city skyline on horizon, highway with traffic, new buildings, industrial facilities, developing infrastructure",
        "atmosphere": "переходная, развивающаяся, городская, открытая",
        "typical_elements": ["город", "здания", "дороги", "инфраструктура", "шоссе", "новостройки", "горизонт"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "parking_lot": {
        "name": "парковка / пустая площадка",
        "name_en": "parking lot / empty area",
        "description": "Асфальтированная площадка с разметкой и ограждениями. Организованное пространство в городе, удобство доступа, инфраструктура.",
        "visual": "асфальтированная площадка с разметкой парковочных мест, ограждения по периметру, фонарные столбы, ровная поверхность для сборки",
        "background": "здания поблизости, фонарные столбы, дорожные знаки, городская инфраструктура, возможно другие припаркованные машины",
        "background_en": "nearby buildings, lamp posts, road signs, urban infrastructure, possibly other parked vehicles",
        "atmosphere": "городская, организованная, функциональная, доступная",
        "typical_elements": ["асфальт", "разметка", "ограждения", "фонари", "здания", "город", "инфраструктура"],
        "camera_recommendation": "static_front_quarter",
        "dynamic_features": {},
    },
    "abandoned_industrial": {
        "name": "заброшенный промышленный объект",
        "name_en": "abandoned industrial site",
        "description": "Старый заброшенный завод с ржавыми конструкциями и разбитыми окнами. Постапокалиптическая атмосфера, ностальгия, заброшенность.",
        "visual": "старый заброшенный заводской корпус с ржавыми металлическими конструкциями, разбитыми окнами, зарослями, обветшалые здания",
        "background": "разрушенные здания, ржавый металл, разбитое стекло, заросли травы и кустов, следы былой промышленной мощи",
        "background_en": "destroyed buildings, rusty metal, broken glass, overgrown grass and bushes, traces of former industrial power",
        "atmosphere": "заброшенная, постапокалиптическая, ностальгическая, таинственная",
        "typical_elements": ["ржавчина", "разрушения", "заброшенность", "заросли", "старое оборудование", "разбитые окна"],
        "camera_recommendation": "static_side_elevated",
        "dynamic_features": {},
    },
    "building_roof": {
        "name": "крыша здания",
        "name_en": "building roof",
        "description": "Плоская крыша здания с парапетом и видом на город. Уникальное городское пространство, панорама, высота.",
        "visual": "плоская крыша высотного здания с парапетом по краям, ровная поверхность для сборки, вентиляционные выходы, антенны",
        "background": "панорама города вокруг, небоскрёбы, улицы внизу, небо над головой, городская застройка",
        "background_en": "city panorama around, skyscrapers, streets below, sky overhead, urban development",
        "atmosphere": "возвышенная, городская, панорамная, эксклюзивная",
        "typical_elements": ["крыша", "парапет", "вид на город", "небоскрёбы", "панорама", "высота", "небо"],
        "camera_recommendation": "static_front_quarter",
        "dynamic_features": {},
    },
    # 🌊 УНИКАЛЬНЫЕ
    "ocean_coast": {
        "name": "побережье океана",
        "name_en": "ocean coast",
        "description": "Берег океана с волнами, пляжем и скалами. Морской горизонт, чайки, свежий бриз. Свобода и широта океанских просторов.",
        "visual": "берег океана с песчаным пляжем или скалистым побережьем, ровная площадка для сборки над уровнем воды, волны океана, яркое солнце",
        "background": "бескрайний океанский горизонт, волны с белой пеной, чайки в небе, скалы по берегу, морской бриз",
        "background_en": "endless ocean horizon, waves with white foam, seagulls in sky, coastal rocks, sea breeze",
        "atmosphere": "свободная, морская, живописная, освежающая",
        "typical_elements": ["океан", "волны", "пляж", "скалы", "чайки", "горизонт", "солнце", "бриз"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "floating_platform": {
        "name": "плавучая платформа",
        "name_en": "floating platform",
        "description": "Большая плавучая платформа с понтонами и креплениями на воде. Морская или речная база для сборки, инженерное решение.",
        "visual": "большая плавучая платформа на понтонах, ровная площадка для сборки, крепления и швартовые устройства, ограждения по периметру",
        "background": "вода вокруг платформы, береговая линия вдали, возможно другие суда или платформы, открытая водная поверхность",
        "background_en": "water around platform, shoreline in distance, possibly other vessels or platforms, open water surface",
        "atmosphere": "морская, инженерная, открытая, уникальная",
        "typical_elements": ["платформа", "понтоны", "вода", "берег", "крепления", "ограждения", "открытое пространство"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "island": {
        "name": "остров",
        "name_en": "island",
        "description": "Остров посреди воды с пляжем и растительностью. Изолированное место, тропическая или умеренная атмосфера, уникальная локация.",
        "visual": "остров с ровной площадкой для сборки, песчаный пляж по периметру, тропическая или лесная растительность, окружён водой",
        "background": "вода океана или моря вокруг, другие острова на горизонте, небо, природная растительность, пальмы или деревья",
        "background_en": "ocean or sea water around, other islands on horizon, sky, natural vegetation, palm trees or trees",
        "atmosphere": "изолированная, тропическая, уникальная, природная",
        "typical_elements": ["остров", "вода", "пляж", "растительность", "пальмы", "горизонт", "изоляция"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "quarry": {
        "name": "карьер",
        "name_en": "quarry",
        "description": "Открытый карьер со скальными породами и техникой. Добывающая промышленность, масштабные земляные работы, сырьевая база.",
        "visual": "открытый карьер с террасами выработки, скальные породы, площадка для сборки на одном из ярусов, карьерная техника, конвейеры",
        "background": "скальные стены карьера, террасы выработки, щебень и порода, карьерная техника в работе, промышленная инфраструктура",
        "background_en": "quarry rock walls, mining terraces, gravel and rock, quarry equipment at work, industrial infrastructure",
        "atmosphere": "промышленная, масштабная, добывающая, сырьевая",
        "typical_elements": ["карьер", "скалы", "террасы", "техника", "порода", "щебень", "промышленность"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
    "port": {
        "name": "порт",
        "name_en": "port",
        "description": "Морской порт с причалами, контейнерами и кранами. Логистический узел, грузооборот, международные перевозки. Ворота мира.",
        "visual": "морской порт с бетонными причалами, контейнерные площадки, портовые краны, площадка для сборки на причале или терминале",
        "background": "грузовые суда у причалов, портовые краны в работе, контейнеры, складские здания, морская вода, горизонт",
        "background_en": "cargo ships at berths, port cranes at work, containers, warehouse buildings, sea water, horizon",
        "atmosphere": "логистическая, морская, активная, международная",
        "typical_elements": ["причалы", "контейнеры", "краны", "суда", "порт", "вода", "грузоперевозки"],
        "camera_recommendation": "drone_elevated",
        "dynamic_features": {},
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# ASSEMBLY STAGES (Sequential Transformations with State Tracking)
# ═══════════════════════════════════════════════════════════════════════════

ASSEMBLY_STAGES: dict[str, dict[str, Any]] = {
    "empty_space": {
        "name": "пустое пространство",
        "name_en": "empty space",
        "visual": "пустая сборочная площадка, чистый бетонный пол или ровная поверхность, инструменты и оборудование на заднем плане, подготовленное пространство",
        "start_state": "пустое пространство",
        "start_state_en": "empty space",
        "end_state": "подготовленная площадка",
        "end_state_en": "prepared assembly area",
        "action": "вид площадки до начала сборки",
        "action_en": "view of the area before assembly starts",
        "workers": None,
        "workers_en": None,
        "micro_actions": [],
        "micro_actions_en": [],
        "build_intensity": "low",
        "time_of_day": "morning",
        "is_peak_moment": False,
        "next": "frame_chassis",
        # State tracking flags
        "has_frame": False,
        "has_engine": False,
        "has_body": False,
        "has_wheels": False,
        "has_interior": False,
        "has_paint": False,
        "has_scaffolding": False,
    },
    "frame_chassis": {
        "name": "рамка и шасси",
        "name_en": "frame and chassis",
        "visual": "металлический каркас и шасси на подъёмниках, видны несущие балки и рама, нет кузовных панелей, открытая конструкция",
        "start_state": "пустая площадка",
        "start_state_en": "empty area",
        "end_state": "собранное шасси и рама",
        "end_state_en": "assembled chassis and frame",
        "action": "сборка несущей рамы и шасси",
        "action_en": "assembling the main frame and chassis",
        "workers": "сварщики работают с рамой, слесари собирают шасси, рабочие устанавливают подвеску",
        "workers_en": "welders working on frame, mechanics assembling chassis, workers installing suspension",
        "machinery": "подъёмники держат раму, сварочные аппараты, гайковерты",
        "machinery_en": "lifts holding frame, welding machines, impact wrenches",
        "micro_actions": [
            "сварщик варит шов на раме",
            "рабочий закручивает болт гайковёртом",
            "подъёмник медленно опускает шасси",
            "слесарь проверяет выравнивание",
        ],
        "micro_actions_en": [
            "welder welding seam on frame",
            "worker tightening bolt with impact wrench",
            "lift slowly lowering chassis",
            "mechanic checking alignment",
        ],
        "build_intensity": "medium",
        "time_of_day": "morning",
        "is_peak_moment": False,
        "next": "engine",
        # State tracking flags
        "has_frame": True,
        "has_engine": False,
        "has_body": False,
        "has_wheels": False,
        "has_interior": False,
        "has_paint": False,
        "has_scaffolding": True,
    },
    "engine": {
        "name": "двигатель",
        "name_en": "engine",
        "visual": "установленный двигатель в моторном отсеке на шасси, видны провода и трубки подключения, рама вокруг, нет кузовных панелей",
        "start_state": "рамка без двигателя",
        "start_state_en": "frame without engine",
        "end_state": "двигатель установлен",
        "end_state_en": "engine installed",
        "action": "установка двигателя в отсек",
        "action_en": "installing the engine into the bay",
        "workers": "механики устанавливают двигатель, инженеры подключают проводку, техники проверяют крепления",
        "workers_en": "mechanics installing engine, engineers connecting wiring, technicians checking mounts",
        "machinery": "кран поднимает двигатель, подъёмная платформа, диагностическое оборудование",
        "machinery_en": "crane lifting engine, lifting platform, diagnostic equipment",
        "micro_actions": [
            "кран медленно опускает двигатель",
            "механик направляет установку",
            "рабочий подключает проводку",
            "техник затягивает крепления",
        ],
        "micro_actions_en": [
            "crane slowly lowering engine",
            "mechanic guiding installation",
            "worker connecting wiring harness",
            "technician tightening mounts",
        ],
        "build_intensity": "high",
        "time_of_day": "midday",
        "is_peak_moment": True,
        "next": "body_panels",
        # State tracking flags
        "has_frame": True,
        "has_engine": True,
        "has_body": False,
        "has_wheels": False,
        "has_interior": False,
        "has_paint": False,
        "has_scaffolding": True,
    },
    "body_panels": {
        "name": "кузовные панели",
        "name_en": "body panels",
        "visual": "кузовные панели установлены на раму, двери, крылья, крыша на месте — всё ещё без покраски, видны сварные швы и стыки",
        "start_state": "шасси с двигателем",
        "start_state_en": "chassis with engine",
        "end_state": "собранный кузов без покраски",
        "end_state_en": "assembled body without paint",
        "action": "установка кузовных панелей",
        "action_en": "installing body panels",
        "workers": "сборщики крепят панели, сварщики обрабатывают швы, рабочие устанавливают двери",
        "workers_en": "assemblers attaching panels, welders working on seams, workers installing doors",
        "machinery": "пневматические инструменты, сварочные аппараты, подъёмники для панелей",
        "machinery_en": "pneumatic tools, welding machines, panel lifts",
        "micro_actions": [
            "рабочий прикрепляет дверь к петлям",
            "сварщик обрабатывает шов",
            "панель опускается на место",
            "рабочий проверяет зазоры",
        ],
        "micro_actions_en": [
            "worker attaching door to hinges",
            "welder working on seam",
            "panel being lowered into place",
            "worker checking panel gaps",
        ],
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
        "next": "wheels",
        # State tracking flags
        "has_frame": True,
        "has_engine": True,
        "has_body": True,
        "has_wheels": False,
        "has_interior": False,
        "has_paint": False,
        "has_scaffolding": True,
    },
    "wheels": {
        "name": "колёса",
        "name_en": "wheels",
        "visual": "колёса установлены на шасси, видны диски и шины, транспортное средство стоит на земле на своих колёсах, кузов собран",
        "start_state": "кузов на опорах",
        "start_state_en": "body on supports",
        "end_state": "колёса установлены",
        "end_state_en": "wheels installed",
        "action": "установка колёс",
        "action_en": "mounting wheels",
        "workers": "шиномонтажники устанавливают колёса, рабочие затягивают болты, техники проверяют давление",
        "workers_en": "tire fitters installing wheels, workers tightening lug nuts, technicians checking pressure",
        "machinery": "гайковерты, домкраты, подъёмники",
        "machinery_en": "impact wrenches, jacks, lifts",
        "micro_actions": [
            "колесо надевается на ступицу",
            "гайковёрт затягивает болты",
            "домкрат опускает машину",
            "техник проверяет давление",
        ],
        "micro_actions_en": [
            "wheel being mounted on hub",
            "impact wrench tightening lug nuts",
            "jack lowering vehicle",
            "technician checking tire pressure",
        ],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "interior",
        # State tracking flags
        "has_frame": True,
        "has_engine": True,
        "has_body": True,
        "has_wheels": True,
        "has_interior": False,
        "has_paint": False,
        "has_scaffolding": False,
    },
    "interior": {
        "name": "установка интерьера",
        "name_en": "interior installation",
        "visual": "вид снаружи транспорта с открытыми дверями, рабочие устанавливают сиденья и панель внутри через дверные проёмы, видны детали интерьера",
        "start_state": "кузов с открытыми проёмами",
        "start_state_en": "body with open door frames",
        "end_state": "интерьер установлен, двери открыты",
        "end_state_en": "interior installed, doors open",
        "action": "установка сидений и приборной панели через дверные проёмы",
        "action_en": "installing seats and dashboard through door openings",
        "workers": "рабочие загружают сиденья через двери, техники подключают проводку снаружи, сборщики крепят элементы",
        "workers_en": "workers loading seats through doors, technicians connecting wiring from outside, assemblers securing components",
        "machinery": "подъёмники для доставки сидений, конвейер подачи деталей",
        "machinery_en": "lifts delivering seats, parts conveyor",
        "micro_actions": [
            "рабочий проносит сиденье через дверь",
            "техник подключает разъём из дверного проёма",
            "деталь интерьера подаётся к двери",
            "работник виден через открытую дверь",
        ],
        "micro_actions_en": [
            "worker carrying seat through door opening",
            "technician connecting harness from doorway",
            "interior part being delivered to door",
            "worker visible through open door",
        ],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "paint_finish",
        # State tracking flags
        "has_frame": True,
        "has_engine": True,
        "has_body": True,
        "has_wheels": True,
        "has_interior": True,
        "has_paint": False,
        "has_scaffolding": False,
    },
    "paint_finish": {
        "name": "покраска и финиш",
        "name_en": "paint and finish",
        "visual": "полностью готовое транспортное средство с блестящей окраской, все детали на месте, чистый и отполированный внешний вид, финальный результат",
        "start_state": "некрашеный корпус",
        "start_state_en": "unpainted body",
        "end_state": "полностью готовый продукт",
        "end_state_en": "fully completed product",
        "action": "окраска и финальная сборка",
        "action_en": "painting and final assembly",
        "workers": "маляры наносят краску, полировщики шлифуют поверхность, техники проводят финальную проверку",
        "workers_en": "painters applying paint, polishers buffing surface, technicians doing final inspection",
        "machinery": "окрасочные камеры, полировальные машины, диагностическое оборудование",
        "machinery_en": "paint booths, buffing machines, diagnostic equipment",
        "micro_actions": [
            "краскопульт наносит слой краски",
            "полировальная машина обрабатывает поверхность",
            "техник проверяет фары",
            "финальная протирка микрофиброй",
        ],
        "micro_actions_en": [
            "spray gun applying paint coat",
            "buffing machine working on surface",
            "technician checking headlights",
            "final wipe with microfiber",
        ],
        "build_intensity": "high",
        "time_of_day": "golden_hour",
        "is_peak_moment": True,
        "next": None,
        # State tracking flags
        "has_frame": True,
        "has_engine": True,
        "has_body": True,
        "has_wheels": True,
        "has_interior": True,
        "has_paint": True,
        "has_scaffolding": False,
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# STAGE SEQUENCES FOR 5-8 STAGES (Universal for all vehicle types)
# ═══════════════════════════════════════════════════════════════════════════

# 5 stages: abbreviated version (essential assembly steps)
STAGE_SEQUENCE_5 = [
    "empty_space",
    "frame_chassis",
    "engine",
    "body_panels",
    "paint_finish"
]

# 6 stages: standard version (adds wheels)
STAGE_SEQUENCE_6 = [
    "empty_space",
    "frame_chassis",
    "engine",
    "body_panels",
    "wheels",
    "paint_finish"
]

# 7 stages: full version (adds interior)
STAGE_SEQUENCE_7 = [
    "empty_space",
    "frame_chassis",
    "engine",
    "body_panels",
    "wheels",
    "interior",
    "paint_finish"
]

# 8 stages: complete version (all steps)
STAGE_SEQUENCE_8 = [
    "empty_space",
    "frame_chassis",
    "engine",
    "body_panels",
    "wheels",
    "interior",
    "paint_finish",
    "paint_finish"  # Duplicate for 8 stages - can be customized
]

# Legacy sequences for backward compatibility
DEFAULT_STAGE_SEQUENCE = STAGE_SEQUENCE_5
EXTENDED_STAGE_SEQUENCE = STAGE_SEQUENCE_6
FULL_STAGE_SEQUENCE = STAGE_SEQUENCE_7


def get_stage_sequence(num_stages: int) -> list[str]:
    """
    Get appropriate stage sequence based on number of stages.
    
    Args:
        num_stages: Number of assembly stages (5-8)
        
    Returns:
        List of stage keys in order
    """
    sequences = {
        5: STAGE_SEQUENCE_5,
        6: STAGE_SEQUENCE_6,
        7: STAGE_SEQUENCE_7,
        8: STAGE_SEQUENCE_8,
    }
    
    # Clamp to valid range
    num_stages = max(5, min(8, num_stages))
    return sequences.get(num_stages, STAGE_SEQUENCE_5)


def validate_stage_sequence(stage_keys: list[str]) -> list[str]:
    """
    Validate stage sequence for logical consistency.
    Ensures no backward progression in assembly state.
    
    Args:
        stage_keys: List of stage keys to validate
        
    Returns:
        Validated list (or raises ValueError if invalid)
    """
    if not stage_keys:
        raise ValueError("Stage sequence cannot be empty")
    
    prev_state = {
        "has_frame": False,
        "has_engine": False,
        "has_body": False,
        "has_wheels": False,
        "has_interior": False,
        "has_paint": False,
    }
    
    errors = []
    
    for i, stage_key in enumerate(stage_keys):
        stage = ASSEMBLY_STAGES.get(stage_key)
        if not stage:
            errors.append(f"Unknown stage: {stage_key}")
            continue
        
        current_state = {
            "has_frame": stage.get("has_frame", False),
            "has_engine": stage.get("has_engine", False),
            "has_body": stage.get("has_body", False),
            "has_wheels": stage.get("has_wheels", False),
            "has_interior": stage.get("has_interior", False),
            "has_paint": stage.get("has_paint", False),
        }
        
        # Check for backward progression
        for key in current_state:
            if prev_state[key] and not current_state[key]:
                errors.append(
                    f"Stage {i} ({stage_key}): {key} disappeared! "
                    f"Was {prev_state[key]}, now {current_state[key]}"
                )
        
        prev_state = current_state
    
    if errors:
        raise ValueError(f"Stage sequence validation failed:\n" + "\n".join(errors))
    
    return stage_keys


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class AssemblyStage(BaseModel):
    """Single assembly stage (transformation)."""
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
    build_intensity: str = "medium"
    
    # ═══════════════════════════════════════════════════════════════════
    # CAMERA CALIBRATION DATA (ABSOLUTELY CRITICAL FOR TIMELAPSE)
    # These parameters MUST remain IDENTICAL across ALL stages
    # ═══════════════════════════════════════════════════════════════════
    camera_position_x: float = 0.0  # Horizontal position (meters from center)
    camera_position_y: float = 1.5  # Height (meters from ground)
    camera_position_z: float = 5.0  # Distance from subject (meters)
    camera_angle_horizontal: float = 0.0  # Horizontal rotation (degrees)
    camera_angle_vertical: float = 0.0  # Vertical tilt (degrees)
    focal_length_mm: float = 50.0  # Focal length (mm, full-frame equivalent)
    horizon_line_percent: float = 40.0  # Horizon position (% from bottom)
    cloud_motion_direction: str = "right"  # ALWAYS "right" for consistent timelapse
    time_of_day: str = "midday"
    is_peak_moment: bool = False


class VehicleScenario(BaseModel):
    """Complete vehicle assembly timelapse scenario."""
    title: str
    title_en: str
    vehicle_type: str
    vehicle_type_name: str
    location: str
    location_name: str
    stages: list[AssemblyStage]
    total_duration: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def select_vehicle_type(preferred: str | None = None) -> str:
    """Select a vehicle type, with support for categories."""
    if not preferred or preferred == "random":
        return random.choice(list(VEHICLE_TYPES.keys()))
    
    # 1. Exact match
    if preferred in VEHICLE_TYPES:
        return preferred
        
    # 2. Category match (e.g. "car" -> "car_modern", "airplane" -> "airplane_passenger")
    category_matches = [k for k in VEHICLE_TYPES.keys() if k.startswith(f"{preferred}_")]
    if category_matches:
        return random.choice(category_matches)
        
    # 3. Fuzzy prefix match
    fuzzy_matches = [k for k in VEHICLE_TYPES.keys() if preferred.lower() in k.lower()]
    if fuzzy_matches:
        return random.choice(fuzzy_matches)

    return "car_modern"


def select_location(preferred: str | None = None) -> str:
    """Select a location."""
    if preferred and preferred in LOCATIONS:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(LOCATIONS.keys()))
    return "factory"


def build_visual_prompt(
    stage_key: str,
    vehicle_type: str,
    location: str,
    variation: dict[str, Any] | None = None,
) -> str:
    """
    Build detailed visual prompt for an assembly stage with structured sections.
    
    Args:
        stage_key: Assembly stage key
        vehicle_type: Vehicle type key
        location: Location key
        variation: Optional vehicle variation from architectural_variations
        
    Returns:
        Structured visual prompt with consistency rules
    """
    stage = ASSEMBLY_STAGES.get(stage_key)
    vehicle = VEHICLE_TYPES.get(vehicle_type, VEHICLE_TYPES["car_modern"])
    loc = LOCATIONS.get(location, LOCATIONS["factory"])
    
    if not stage:
        return f"Assembly stage: {stage_key}"
    
    # Get camera specification for location
    camera_key = loc.get("camera_recommendation", "static_side_elevated")
    camera_spec = CAMERA_SPECS.get(camera_key, CAMERA_SPECS["static_side_elevated"])
    
    # Get dynamic features for location
    dynamic_features = loc.get("dynamic_features", {})
    dynamic_desc = dynamic_features.get("dynamic_description", f"assembly at {loc['name_en']}")
    full_visibility = dynamic_features.get("full_vehicle_visibility", "vehicle fully visible in frame")
    
    # Build vehicle description (with variation if available)
    if variation:
        vehicle_desc = variation.get("visual_description", vehicle.get("description", vehicle["name_en"]))
        color_info = f"Color: {variation.get('primary_color', '')} ({variation.get('finish', '')})"
        accent_info = f"Accents: {', '.join(variation.get('accent_features', [])[:3])}"
    else:
        vehicle_desc = vehicle.get("description", vehicle["name_en"])
        color_info = f"Materials: {vehicle.get('materials', 'metal, composite')}"
        accent_info = f"Features: {', '.join(vehicle.get('typical_features', [])[:3]) if 'typical_features' in vehicle else ''}"
    
    # Get workers and machinery
    workers_en = stage.get("workers_en")
    machinery_en = stage.get("machinery_en")
    
    # Build structured prompt
    prompt_parts = [
        f"STAGE: {stage['name_en'].upper()}",
        f"Scene: {stage['visual']}",
        "",
        "━━━ CAMERA SPECIFICATION (FIXED FOR ALL STAGES) ━━━",
        f"View: {camera_spec['name']}",
        f"Specification: {camera_spec['description']}",
        f"Lens: {camera_spec['lens']}",
        f"Height: {camera_spec['height']}",
        f"Angle: {camera_spec['angle']}",
        f"Distance: {camera_spec['distance']}",
        f"Framing: {camera_spec['framing']}",
        f"CRITICAL: {camera_spec['movement']} - use EXACT same position for ALL stages",
        "",
        "━━━ CURRENT STATE (MUST MATCH THIS EXACTLY) ━━━",
        f"Frame/Chassis: {'YES - fully assembled frame visible' if stage.get('has_frame') else 'NO - empty space only'}",
        f"Engine: {'YES - engine installed in bay' if stage.get('has_engine') else 'NO - no engine yet'}",
        f"Body Panels: {'YES - body assembled (unpainted)' if stage.get('has_body') else 'NO - no body panels'}",
        f"Wheels: {'YES - wheels mounted on axles' if stage.get('has_wheels') else 'NO - on supports/jacks'}",
        f"Interior: {'YES - seats and dashboard installed' if stage.get('has_interior') else 'NO - empty cabin'}",
        f"Paint/Finish: {'YES - painted and polished' if stage.get('has_paint') else 'NO - unpainted/raw metal'}",
        f"Scaffolding: {'YES - scaffolding/structure around vehicle' if stage.get('has_scaffolding') else 'NO - no scaffolding'}",
        "",
        "━━━ VEHICLE CHARACTER ━━━",
        f"Type: {vehicle['name_en']}",
        f"Description: {vehicle_desc[:200]}",
        f"{color_info}",
        f"{accent_info}",
        "",
        "━━━ LOCATION & SETTING ━━━",
        f"Location: {loc['name_en']}",
        f"Environment: {loc.get('description', loc['visual'])[:150]}",
        f"Background: {loc['background_en']}",
        f"Full Vehicle Visibility: {full_visibility}",
        f"Dynamic Elements: {dynamic_desc}",
        "",
        "━━━ ASSEMBLY ACTIVITY ━━━",
    ]
    
    if workers_en:
        prompt_parts.append(f"Workers: {workers_en}")
    if machinery_en:
        prompt_parts.append(f"Machinery: {machinery_en}")
    
    prompt_parts.extend([
        f"Action: {stage['action_en']}",
        "",
        "━━━ CRITICAL CONSISTENCY RULES (MUST FOLLOW) ━━━",
        "1. CAMERA: Use EXACT camera specs above for ALL stages - position never changes",
        "2. FULL VEHICLE: Entire vehicle structure must be visible in EVERY frame",
        "3. BACKGROUND: Location elements (sky, buildings, landscape) must remain IDENTICAL",
        "4. VEHICLE POSITION: The vehicle must stay in the EXACT same location on ground",
        "5. PROGRESSION: Assembly only moves forward - parts appear, never disappear",
        "6. FRAME RULE: Once frame appears, it must stay consistent in all following stages",
        "7. ENGINE RULE: Once engine is installed, it remains visible in all stages",
        "8. BODY RULE: Once body panels are on, they stay on (just get painted)",
        "9. FINAL STAGE: Complete painted vehicle, all parts installed, NO scaffolding",
    ])
    
    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCENARIO GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_scenario(
    vehicle_type: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
) -> VehicleScenario:
    """
    Generate a vehicle assembly timelapse scenario.

    Args:
        vehicle_type: Vehicle type key (airplane, car, tractor)
        location: Location key (hangar, factory, workshop, outdoor)
        num_stages: Number of stages (5-7)
        language: Output language

    Returns:
        Complete VehicleScenario
    """
    # Select vehicle and location
    vehicle_key = select_vehicle_type(vehicle_type)
    loc_key = select_location(location)

    vehicle = VEHICLE_TYPES[vehicle_key]
    loc = LOCATIONS[loc_key]

    # Get stage sequence
    num_stages = max(5, min(7, num_stages))
    stage_keys = get_stage_sequence(num_stages)

    # Build stages
    stages = []
    total_duration = 0

    for i, stage_key in enumerate(stage_keys):
        stage_data = ASSEMBLY_STAGES[stage_key]

        visual_prompt = build_visual_prompt(
            stage_key,
            vehicle_key,
            loc_key,
        )

        stage = AssemblyStage(
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
            # CAMERA CALIBRATION - IDENTICAL FOR ALL STAGES
            camera_position_x=0.0,
            camera_position_y=1.5,
            camera_position_z=5.0,
            camera_angle_horizontal=0.0,
            camera_angle_vertical=0.0,
            focal_length_mm=50.0,
            horizon_line_percent=40.0,
            cloud_motion_direction="right",  # ALWAYS right for consistent timelapse
        )
        stages.append(stage)
        total_duration += stage.duration

    # Build title
    if language == "en":
        title = f"Building a {vehicle['name_en']}"
        title_en = title
    else:
        title = f"Сборка {vehicle['name']}"
        title_en = f"Building a {vehicle['name_en']}"

    scenario = VehicleScenario(
        title=title,
        title_en=title_en,
        vehicle_type=vehicle_key,
        vehicle_type_name=vehicle["name"],
        location=loc_key,
        location_name=loc["name"],
        stages=stages,
        total_duration=total_duration,
    )

    logger.success(
        f"[Mode9 Scenario] Generated: {title} | "
        f"{len(stages)} stages | {vehicle['name']} | {loc['name']}"
    )

    return scenario


async def run_mode9_scenario_writer(
    vehicle_type: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Main entry point for Mode 9 scenario generation.

    Args:
        vehicle_type: Vehicle type preference
        location: Location preference
        num_stages: Number of assembly stages (5-7)
        language: Output language
        control: Pipeline control dict

    Returns:
        dict compatible with pipeline
    """
    from pipeline_control import checkpoint

    await checkpoint(control)

    scenario = generate_scenario(
        vehicle_type=vehicle_type,
        location=location,
        num_stages=num_stages,
        language=language,
    )

    # Convert to dict for pipeline compatibility
    return {
        "title": scenario.title,
        "title_en": scenario.title_en,
        "vehicle_type": scenario.vehicle_type,
        "vehicle_type_name": scenario.vehicle_type_name,
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
