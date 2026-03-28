"""
Mode 9 Scenario Writer — Vehicle Building Timelapse.

Generates sequential assembly stages for vehicle construction timelapse video.
Each stage represents a transformation from state A to state B.
Vehicles: Airplane, Car, Tractor
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════════════
# VEHICLE TYPES
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_TYPES: dict[str, dict[str, Any]] = {
    # ✈️ АВИАЦИЯ
    "airplane_passenger": {
        "name": "пассажирский самолёт",
        "name_en": "passenger airplane",
        "visual": "пассажирский самолёт, металлический фюзеляж, крылья с закрылками, хвостовое оперение, реактивные двигатели под крыльями",
        "materials": "алюминий, титан, композитные материалы, сталь",
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
        "visual": "робот-манипулятор, суставы, захват, панель управления",
        "materials": "алюминий, сервомоторы, электроника",
        "setting": "завод роботов, автоматизированный цех",
        "setting_en": "robotics factory, automated workshop",
    },
    "oil_rig": {
        "name": "буровая установка",
        "name_en": "oil rig",
        "visual": "нефтяная вышка, буровая колонна, насосы, платформы",
        "materials": "сталь, специальные сплавы",
        "setting": "нефтяное месторождение, буровая площадка",
        "setting_en": "oil field, drilling site",
    },
    "solar_farm": {
        "name": "солнечная панельная ферма",
        "name_en": "solar panel farm",
        "visual": "солнечные панели на металлических опорах, инверторы, кабели",
        "materials": "кремний, алюминий, стекло, медь",
        "setting": "солнечная электростанция, пустыня",
        "setting_en": "solar power plant, desert",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LOCATIONS / SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

LOCATIONS: dict[str, dict[str, Any]] = {
    # 🏗️ ИНДУСТРИАЛЬНЫЕ
    "construction_site": {
        "name": "строительная площадка",
        "name_en": "construction site",
        "visual": "строительная площадка, краны, строительные материалы, техника",
        "background": "небоскрёбы на горизонте, стройматериалы, рабочие",
        "background_en": "skyscrapers on horizon, construction materials, workers",
    },
    "factory": {
        "name": "завод / производственный цех",
        "name_en": "factory / production workshop",
        "visual": "современный сборочный цех, конвейерная линия, промышленные роботы",
        "background": "роботы-манипуляторы, конвейер, запчасти на полках",
        "background_en": "robotic arms, conveyor belt, parts on shelves",
    },
    "shipyard": {
        "name": "верфь",
        "name_en": "shipyard",
        "visual": "судостроительная верфь, сухие доки, стапели, подъёмные краны",
        "background": "корабли на разных стадиях сборки, морская вода",
        "background_en": "ships at various stages, sea water",
    },
    "hangar": {
        "name": "авиационный ангар",
        "name_en": "aviation hangar",
        "visual": "большой промышленный ангар, высокий потолок, металлические фермы",
        "background": "инструменты на стенах, подъёмные краны, оборудование",
        "background_en": "tools on walls, overhead cranes, equipment",
    },
    "industrial_zone": {
        "name": "индустриальная зона",
        "name_en": "industrial zone",
        "visual": "промышленная зона, заводы, трубы, склады",
        "background": "дымящие трубы, грузовики, краны",
        "background_en": "smoking pipes, trucks, cranes",
    },
    # 🌿 ПРИРОДА
    "empty_field": {
        "name": "пустое поле",
        "name_en": "empty field",
        "visual": "открытое поле, зелёная трава, чистое небо",
        "background": "деревья на горизонте, холмы",
        "background_en": "trees on horizon, hills",
    },
    "forest_clearing": {
        "name": "лесная поляна",
        "name_en": "forest clearing",
        "visual": "поляна в лесу, деревья вокруг, естественное освещение",
        "background": "высокие деревья, кустарники",
        "background_en": "tall trees, bushes",
    },
    "desert": {
        "name": "пустыня",
        "name_en": "desert",
        "visual": "песчаная пустыня, дюны, яркое солнце",
        "background": "песчаные холмы, кактусы",
        "background_en": "sand dunes, cacti",
    },
    "mountain_valley": {
        "name": "горная долина",
        "name_en": "mountain valley",
        "visual": "долина между горами, скалистые вершины, река",
        "background": "горные пики, облака",
        "background_en": "mountain peaks, clouds",
    },
    "snowy_plain": {
        "name": "снежная равнина",
        "name_en": "snowy plain",
        "visual": "заснеженная равнина, белый снег, холодное небо",
        "background": "сугробы, ледяные образования",
        "background_en": "snowdrifts, ice formations",
    },
    # 🌆 УРБАН
    "city_outskirts": {
        "name": "городская окраина",
        "name_en": "city outskirts",
        "visual": "окраина города, здания на горизонте, дороги",
        "background": "городской силуэт, шоссе",
        "background_en": "city skyline, highway",
    },
    "parking_lot": {
        "name": "парковка / пустая площадка",
        "name_en": "parking lot / empty area",
        "visual": "асфальтированная площадка, разметка, ограждения",
        "background": "зданий поблизости, фонарные столбы",
        "background_en": "nearby buildings, lamp posts",
    },
    "abandoned_industrial": {
        "name": "заброшенный промышленный объект",
        "name_en": "abandoned industrial site",
        "visual": "старый заброшенный завод, ржавые конструкции, разбитые окна",
        "background": "разрушенные здания, старый металл",
        "background_en": "destroyed buildings, old metal",
    },
    "building_roof": {
        "name": "крыша здания",
        "name_en": "building roof",
        "visual": "плоская крыша здания, парапет, вид на город",
        "background": "городской пейзаж, небо",
        "background_en": "cityscape, sky",
    },
    # 🌊 УНИКАЛЬНЫЕ
    "ocean_coast": {
        "name": "побережье океана",
        "name_en": "ocean coast",
        "visual": "берег океана, волны, пляж, скалы",
        "background": "океанский горизонт, чайки",
        "background_en": "ocean horizon, seagulls",
    },
    "floating_platform": {
        "name": "плавучая платформа",
        "name_en": "floating platform",
        "visual": "большая плавучая платформа, понтоны, крепления",
        "background": "вода, береговая линия",
        "background_en": "water, shoreline",
    },
    "island": {
        "name": "остров",
        "name_en": "island",
        "visual": "остров посреди воды, пляж, растительность",
        "background": "океан, другие острова",
        "background_en": "ocean, other islands",
    },
    "quarry": {
        "name": "карьер",
        "name_en": "quarry",
        "visual": "открытый карьер, скальные породы, техника",
        "background": "скальные стены, щебень",
        "background_en": "rock walls, gravel",
    },
    "port": {
        "name": "порт",
        "name_en": "port",
        "visual": "морской порт, причалы, контейнеры, краны",
        "background": "грузовые суда, портовые сооружения",
        "background_en": "cargo ships, port facilities",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# ASSEMBLY STAGES (Sequential Transformations)
# ═══════════════════════════════════════════════════════════════════════════

ASSEMBLY_STAGES: dict[str, dict[str, Any]] = {
    "empty_space": {
        "name": "пустое пространство",
        "name_en": "empty space",
        "visual": "пустая сборочная площадка, чистый бетонный пол, инструменты и оборудование на заднем плане",
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
    },
    "frame_chassis": {
        "name": "рамка и шасси",
        "name_en": "frame and chassis",
        "visual": "металлический каркас, шасси на подъёмниках, видны несущие балки, нет кузова",
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
    },
    "engine": {
        "name": "двигатель",
        "name_en": "engine",
        "visual": "установленный двигатель в отсеке, видны провода и трубки, рама вокруг",
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
    },
    "body_panels": {
        "name": "кузовные панели",
        "name_en": "body panels",
        "visual": "кузовные панели на месте, двери, крылья, крыша — всё ещё без покраски, видны швы",
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
    },
    "wheels": {
        "name": "колёса",
        "name_en": "wheels",
        "visual": "колёса установлены на шасси, видны диски и шины, машина стоит на земле",
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
    },
    "interior": {
        "name": "салон",
        "name_en": "interior",
        "visual": "собранный салон, сиденья установлены, руль на месте, приборная панель, видны детали интерьера",
        "start_state": "пустой салон",
        "start_state_en": "empty interior",
        "end_state": "полностью собранный интерьер",
        "end_state_en": "fully assembled interior",
        "action": "сборка салона и установка сидений",
        "action_en": "assembling interior and seats",
        "workers": "сборщики устанавливают сиденья, электрики подключают панель, рабочие монтируют обивку",
        "workers_en": "assemblers installing seats, electricians connecting dashboard, workers mounting upholstery",
        "machinery": "пневматические отвёртки, подъёмники для сидений, тестеры",
        "machinery_en": "pneumatic screwdrivers, seat lifts, testers",
        "micro_actions": [
            "сиденье устанавливается на крепления",
            "электрик подключает проводку панели",
            "руль устанавливается на колонку",
            "обивка натягивается на детали",
        ],
        "micro_actions_en": [
            "seat being mounted on brackets",
            "electrician connecting dashboard wiring",
            "steering wheel installed on column",
            "upholstery being stretched over parts",
        ],
        "build_intensity": "medium",
        "time_of_day": "afternoon",
        "is_peak_moment": False,
        "next": "paint_finish",
    },
    "paint_finish": {
        "name": "покраска и финиш",
        "name_en": "paint and finish",
        "visual": "полностью готовый транспорт, блестящая окраска, все детали на месте, чистый и отполированный",
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
    },
}

# Последовательности этапов для разного количества стадий
# УНИВЕРСАЛЬНЫЕ ДЛЯ ВСЕХ ТРАНСПОРТНЫХ СРЕДСТВ

# 5 этапов: сокращённая версия
DEFAULT_STAGE_SEQUENCE = [
    "empty_space", 
    "base_structure", 
    "main_components", 
    "body_shell", 
    "paint_completion"
]

# 6 этапов: стандартная версия
EXTENDED_STAGE_SEQUENCE = [
    "empty_space", 
    "base_structure", 
    "main_components", 
    "body_shell", 
    "systems_equipment", 
    "paint_completion"
]

# 7 этапов: полная версия
FULL_STAGE_SEQUENCE = [
    "empty_space", 
    "base_structure", 
    "main_components", 
    "body_shell", 
    "systems_equipment", 
    "interior_finish", 
    "paint_completion"
]


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
    """Select a vehicle type."""
    if preferred and preferred in VEHICLE_TYPES:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(VEHICLE_TYPES.keys()))
    return "car"


def select_location(preferred: str | None = None) -> str:
    """Select a location."""
    if preferred and preferred in LOCATIONS:
        return preferred
    if preferred == "random" or preferred is None:
        return random.choice(list(LOCATIONS.keys()))
    return "factory"


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
    vehicle_type: str,
    location: str,
) -> str:
    """Build detailed visual prompt for an assembly stage (ALWAYS in English)."""
    stage = ASSEMBLY_STAGES.get(stage_key)
    vehicle = VEHICLE_TYPES.get(vehicle_type, VEHICLE_TYPES["car"])
    loc = LOCATIONS.get(location, LOCATIONS["factory"])

    workers_en = stage.get("workers_en") if stage else None
    machinery_en = stage.get("machinery_en") if stage else None

    result = f"""{stage['name_en'].capitalize()} stage. {stage['visual']}.
Vehicle: {vehicle['name_en']} — {vehicle['visual']}.
Setting: {loc['name_en']} — {loc['visual']}.
Materials: {vehicle['materials']}.
Background: {loc['background_en']}."""
    if workers_en:
        result += f"\nWorkers: {workers_en}."
    if machinery_en:
        result += f"\nMachinery: {machinery_en}."
    return result


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
