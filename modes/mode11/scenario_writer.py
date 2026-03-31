"""
Mode 11 Scenario Writer — Landmark timelapse (reference chain complete→site; video playback build-up).

Default uses five stages; clips interpolate from emptier to more complete with landmark-specific labor.
"""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel

from modes.mode11.creative_blueprints import get_creative_blueprint

STRUCTURE_TYPES: dict[str, dict[str, Any]] = {
    "giza_pyramids": {
        "name": "Пирамиды Гизы",
        "name_en": "Giza Pyramids",
        "location": "Giza plateau, Egypt",
        "identity": "Great Pyramid complex with limestone casing history, desert plateau, Cairo haze",
        "engineering": "2.3 million blocks, ramp logistics, precise cardinal alignment",
        "materials": "limestone, granite blocks, sand-filled joints",
        "signature_elements": "main pyramid mass, smaller companion pyramids, causeway traces",
    },
    "great_wall": {
        "name": "Великая Китайская стена",
        "name_en": "Great Wall of China",
        "location": "Northern China mountain ridges",
        "identity": "long crenellated wall following mountain spine with watchtowers",
        "engineering": "rammed earth cores, brick/stone skins, sticky-rice lime mortar",
        "materials": "brick, stone, compacted earth",
        "signature_elements": "serpentine ridge line, beacon towers every segment",
    },
    "colosseum": {
        "name": "Колизей",
        "name_en": "Colosseum",
        "location": "Rome, Italy",
        "identity": "elliptical amphitheater, arcaded facade, exposed hypogeum remains",
        "engineering": "Roman concrete foundation, travertine frame, vault network",
        "materials": "travertine, tuff, brick, Roman concrete",
        "signature_elements": "stacked arches, radial structure, arena bowl",
    },
    "eiffel_tower": {
        "name": "Эйфелева башня",
        "name_en": "Eiffel Tower",
        "location": "Paris, France",
        "identity": "latticed iron tower over Champ de Mars",
        "engineering": "18,038 prefabricated elements, 2.5M rivets, aerodynamic profile",
        "materials": "wrought iron lattice and riveted joints",
        "signature_elements": "four inclined legs, first/second platform, top spire",
    },
    "taj_mahal": {
        "name": "Тадж-Махал",
        "name_en": "Taj Mahal",
        "location": "Agra, India",
        "identity": "white marble mausoleum with central dome and minarets",
        "engineering": "river-adapted foundations, pietra dura inlay, minarets tilted outward",
        "materials": "white marble, sandstone, inlay stonework",
        "signature_elements": "main onion dome, four minarets, plinth symmetry",
    },
    "christ_redeemer": {
        "name": "Христос-Искупитель",
        "name_en": "Christ the Redeemer",
        "location": "Rio de Janeiro, Brazil",
        "identity": "art-deco statue on Corcovado with arms outstretched",
        "engineering": "reinforced concrete core, soapstone cladding, mountain logistics",
        "materials": "reinforced concrete, soapstone tiles",
        "signature_elements": "cross-like silhouette, pedestal, mountain skyline",
    },
    "statue_of_liberty": {
        "name": "Статуя Свободы",
        "name_en": "Statue of Liberty",
        "location": "Liberty Island, New York, USA",
        "identity": "copper-clad statue with torch and crown spikes",
        "engineering": "flexible inner frame by Eiffel, repoussé copper skin panels",
        "materials": "copper sheets, steel frame, stone pedestal",
        "signature_elements": "torch arm, crown, draped robe silhouette, pedestal mass",
    },
    "hanging_gardens": {
        "name": "Висячие сады Семирамиды",
        "name_en": "Hanging Gardens of Babylon",
        "location": "Legendary Babylon/Nineveh Mesopotamian setting",
        "identity": "multi-terrace elevated gardens with dense vegetation and water channels",
        "engineering": "stacked terraces, layered waterproofing, water-lift irrigation",
        "materials": "stone terraces, baked brick, bitumen layers, lead waterproofing",
        "signature_elements": "tiered terraces, lush trees, cascading irrigation",
    },
}

FULL_STAGE_SEQUENCE = [
    "final_complete",
    "weathered_damage",
    "major_partial_loss",
    "core_structure_exposed",
    "fragmented_ruins",
    "near_disappearance",
    "fully_removed",
]

DEFAULT_NUM_STAGES = 5

STAGE_TEMPLATES: dict[str, dict[str, str]] = {
    "final_complete": {
        "name": "полный объект",
        "name_en": "fully completed monument",
        "action": "монумент в завершенном и узнаваемом виде",
        "action_en": "monument shown complete and iconic",
    },
    "weathered_damage": {
        "name": "первые повреждения",
        "name_en": "initial weathering damage",
        "action": "поверхностные потери облицовки, трещины и эрозия",
        "action_en": "surface cladding loss, cracks, and erosion marks",
    },
    "major_partial_loss": {
        "name": "частичное разрушение",
        "name_en": "major partial loss",
        "action": "крупные фрагменты исчезают, форма еще читается",
        "action_en": "large sections removed while silhouette remains readable",
    },
    "core_structure_exposed": {
        "name": "обнаженный каркас",
        "name_en": "core structure exposed",
        "action": "внешние слои сняты, видны конструктивные ядра",
        "action_en": "outer layers removed, inner cores become visible",
    },
    "fragmented_ruins": {
        "name": "разрозненные руины",
        "name_en": "fragmented ruins",
        "action": "остаются изолированные фрагменты без цельного объема",
        "action_en": "isolated remnants remain without full mass",
    },
    "near_disappearance": {
        "name": "почти исчез",
        "name_en": "near disappearance",
        "action": "единичные остатки и следы фундамента",
        "action_en": "only tiny remnants and foundation traces remain",
    },
    "fully_removed": {
        "name": "полностью исчез",
        "name_en": "fully removed",
        "action": "объект отсутствует, только площадка и окружение",
        "action_en": "object absent, only location context is visible",
    },
}

STRUCTURE_STAGE_DETAILS: dict[str, dict[str, str]] = {
    "giza_pyramids": {
        "final_complete": "Bright limestone casing intact, crisp pyramid edges and full monumental geometry.",
        "weathered_damage": "Casing stones partially missing, wind erosion visible, small collapses near corners.",
        "major_partial_loss": "Upper casing and side bands removed, irregular stepped core appears.",
        "core_structure_exposed": "Inner block courses exposed with missing faces and open void sections.",
        "fragmented_ruins": "Only truncated pyramid masses and detached block clusters remain.",
        "near_disappearance": "Low mounds of stone and faint base outlines on desert plateau.",
        "fully_removed": "Empty desert platform with only subtle archaeological traces.",
    },
    "great_wall": {
        "final_complete": "Continuous wall spine and intact watchtowers on mountain ridges.",
        "weathered_damage": "Crenellations chipped, surface cracks and missing parapet sections.",
        "major_partial_loss": "Long gaps split the wall; several towers are half-collapsed.",
        "core_structure_exposed": "Outer brick skin lost, rammed-earth cores and inner fill exposed.",
        "fragmented_ruins": "Disconnected stubs and isolated tower ruins along the ridge.",
        "near_disappearance": "Short scattered remnants barely follow the original path.",
        "fully_removed": "Natural mountain ridgeline remains without wall structures.",
    },
    "colosseum": {
        "final_complete": "Complete elliptical amphitheater with layered arches and coherent facade.",
        "weathered_damage": "Facade damage, missing arch stones, fissures in outer ring.",
        "major_partial_loss": "Large arcades collapsed; bowl shape still partly readable.",
        "core_structure_exposed": "Internal radial walls and vault skeleton dominate view.",
        "fragmented_ruins": "Broken ring fragments and detached arch segments only.",
        "near_disappearance": "Low masonry islands and arena footprint traces remain.",
        "fully_removed": "Open Roman ground with no standing amphitheater remains.",
    },
    "eiffel_tower": {
        "final_complete": "Full iron lattice tower with all levels and top spire.",
        "weathered_damage": "Localized lattice losses and damaged sections in upper levels.",
        "major_partial_loss": "Upper tower and parts of mid-section removed, silhouette shortened.",
        "core_structure_exposed": "Sparse structural legs and cross-bracing skeleton left.",
        "fragmented_ruins": "Only partial leg fragments and scattered iron frameworks.",
        "near_disappearance": "Minimal metal remnants near foundations and anchor zones.",
        "fully_removed": "Open Champ de Mars perspective without tower presence.",
    },
    "taj_mahal": {
        "final_complete": "Full marble mausoleum with central dome and four minarets.",
        "weathered_damage": "Marble surface wear, inlay loss, cracks in selected sections.",
        "major_partial_loss": "Portions of dome cladding and minaret tops missing.",
        "core_structure_exposed": "Inner masonry and support volumes visible under lost marble skin.",
        "fragmented_ruins": "Broken dome base, minaret stumps, scattered facade fragments.",
        "near_disappearance": "Low plinth remnants and sparse marble debris.",
        "fully_removed": "Symmetric platform area visible with no mausoleum mass.",
    },
    "christ_redeemer": {
        "final_complete": "Complete art-deco statue with full arm span over pedestal.",
        "weathered_damage": "Soapstone wear and localized fractures at hands and robe edges.",
        "major_partial_loss": "Arms and upper body sections partially lost, silhouette broken.",
        "core_structure_exposed": "Concrete core and internal reinforcement become visible.",
        "fragmented_ruins": "Pedestal plus fractured torso remnants only.",
        "near_disappearance": "Small concrete fragments at pedestal edge.",
        "fully_removed": "Corcovado viewpoint remains without statue body.",
    },
    "statue_of_liberty": {
        "final_complete": "Complete statue with torch, crown, drapery and pedestal context.",
        "weathered_damage": "Copper skin damage and cracks near torch/crown details.",
        "major_partial_loss": "Torch arm and upper sections significantly removed.",
        "core_structure_exposed": "Inner frame and partial copper shell segments visible.",
        "fragmented_ruins": "Scattered statue sections and reduced pedestal-top remnants.",
        "near_disappearance": "Only minor fragments near pedestal crown line.",
        "fully_removed": "Harbor backdrop and pedestal area without statue silhouette.",
    },
    "hanging_gardens": {
        "final_complete": "Dense multi-level terraces with flowing irrigation and trees.",
        "weathered_damage": "Vegetation thinning, cracked channels, partial terrace erosion.",
        "major_partial_loss": "Upper terraces collapsed, irrigation network heavily disrupted.",
        "core_structure_exposed": "Bare stepped masonry and waterproofing layers become visible.",
        "fragmented_ruins": "Broken terrace blocks and isolated retaining walls remain.",
        "near_disappearance": "Low ruin mounds and faint stepped contour traces.",
        "fully_removed": "Mesopotamian landscape with no visible garden superstructure.",
    },
}

STRUCTURE_CAMERA_DIRECTIVES: dict[str, str] = {
    "giza_pyramids": (
        "High-angle elevated exterior from southwest plateau, mid-wide 28mm perspective, "
        "camera altitude above highest pyramid apex, full monument complex entirely visible in frame, "
        "horizon level, all pyramids upright with clean vertical perspective."
    ),
    "great_wall": (
        "High-angle oblique ridge-following exterior from above nearby tower height, medium-wide 30mm perspective, "
        "camera altitude above highest local wall/tower point, full visible wall segment entirely in frame, "
        "wall leading line into distance, horizon level and no tilt."
    ),
    "colosseum": (
        "Fixed high-angle elevated three-quarter viewpoint that reveals both exterior arcades and visible interior arena/hypogeum, "
        "camera altitude above top ring line, full Colosseum mass entirely visible in frame, "
        "medium-wide 26mm lens, horizon level, monument upright with no rotation."
    ),
    "eiffel_tower": (
        "High-angle elevated centered exterior from Champ de Mars axis, 24-28mm lens, "
        "camera altitude above top spire, entire tower from base legs to spire fully visible in frame, "
        "verticals corrected and no dutch angle."
    ),
    "taj_mahal": (
        "Symmetrical frontal high-angle exterior from reflecting pool axis, camera altitude above central dome, "
        "35mm lens, full mausoleum and all four minarets entirely visible in frame, fully upright."
    ),
    "christ_redeemer": (
        "Frontal high-angle medium telephoto view from opposite ridge, camera altitude above statue head, "
        "full statue and pedestal entirely visible in frame, stable skyline and level horizon, statue upright."
    ),
    "statue_of_liberty": (
        "Harbor-side high-angle three-quarter exterior from elevated ferry/drone distance, 35mm lens, "
        "camera altitude above torch tip, full statue and pedestal entirely visible in frame, "
        "horizon level and no frame rotation."
    ),
    "hanging_gardens": (
        "High-angle three-quarter elevated cross-sectional exterior that also exposes internal terraces and irrigation channels, "
        "camera altitude above top terrace canopy, full terrace stack entirely visible in frame, "
        "medium-wide 28mm lens, stepped geometry upright and horizon level."
    ),
}

def _clamp_mode11_num_stages(n: int) -> int:
    """Product only supports 5 (milestone) or 7 (full arc); align with server normalization."""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return DEFAULT_NUM_STAGES
    return 7 if v >= 7 else 5


def _select_stage_sequence(num_stages: int) -> list[str]:
    total = max(2, min(num_stages, len(FULL_STAGE_SEQUENCE)))
    if total == len(FULL_STAGE_SEQUENCE):
        return list(FULL_STAGE_SEQUENCE)
    # Pick evenly distributed milestones and keep order: complete -> removed.
    picked: list[int] = []
    max_index = len(FULL_STAGE_SEQUENCE) - 1
    for i in range(total):
        idx = round(i * max_index / (total - 1))
        if not picked or idx != picked[-1]:
            picked.append(idx)
    while len(picked) < total:
        for idx in range(max_index + 1):
            if idx not in picked:
                picked.append(idx)
            if len(picked) == total:
                break
    picked.sort()
    return [FULL_STAGE_SEQUENCE[i] for i in picked]


def _build_reconstruction_transition_keys(stage_sequence: list[str]) -> list[tuple[str, str]]:
    # Playback order of keyframe videos: empty site -> ... -> complete monument.
    return [
        (stage_sequence[i], stage_sequence[i - 1])
        for i in range(len(stage_sequence) - 1, 0, -1)
    ]


def _tk(a: str, b: str) -> str:
    return f"{a}__{b}"


# Per-landmark labor, tools, and build order for RECONSTRUCTION clips (matches RECONSTRUCTION_TRANSITION_KEYS).
STRUCTURE_RECONSTRUCTION_LABOR: dict[str, dict[str, dict[str, Any]]] = {
    "giza_pyramids": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Surveyors, quarry laborers, rope teams marking base grid; workers hauling first limestone sled loads.",
            "machinery_en": "Wooden A-frames, sledges, simple wooden cranes (shaduf-style levers), sand ramps — no modern brands.",
            "action_en": "Lay out plateau base lines; bring first core blocks and rough staging ramps; desert site becomes an active quarry-to-site supply line.",
            "micro_actions_en": [
                "chalk lines and pegs at plateau",
                "teams drag sledges across sand",
                "first course blocks bedded on leveled sand",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Masons stacking core blocks in courses; workers on ramps packing rubble fill; overseers coordinating tier heights.",
            "machinery_en": "Earthen ramps wrapping faces; wooden rollers; rope hoists at corners.",
            "action_en": "Raise truncated pyramid cores and detached clusters until stepped geometry reads as a pyramid mass again.",
            "micro_actions_en": [
                "pounding wedges to seat blocks",
                "workers climb ramps with baskets of chips",
                "corner alignment with sighting rods",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Specialist facing crews; teams flushing joints; workers clearing spoil.",
            "machinery_en": "Wooden gantries along edges; lever bars; sledges for heavy facing stones.",
            "action_en": "Close core voids; add inner courses and rough faces before fine casing.",
            "micro_actions_en": [
                "hauling granite from river barges (background)",
                "packing joint sand",
                "checking course lines with cords",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Casing stone teams; sculptors trimming edges; many workers on scaffold lines.",
            "machinery_en": "Scaffolding belts around faces; hand cranes; water sprayers to cut dust.",
            "action_en": "Install bright limestone casing bands and restore crisp pyramid edges and companion pyramid volumes.",
            "micro_actions_en": [
                "casing blocks lifted course by course",
                "workers tap blocks into alignment",
                "sun glints on new facing",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Finish crews; detail masons at apex; cleaners washing faces.",
            "machinery_en": "Light wooden platforms near peak; ropes; hand tools only.",
            "action_en": "Complete upper casing and small satellite pyramid forms; subtle weathering begins (authentic patina).",
            "micro_actions_en": [
                "capstone zone work",
                "brush and wet sponge cleaning",
                "guards of honor spacing blocks",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Final inspectors walking base; small teams touching joints; figures at plateau edge for scale.",
            "machinery_en": "Minimal gear — mostly cleared site; remaining ropes coiled.",
            "action_en": "Restore pristine Giza ensemble: full casing read, crisp geometry, Cairo haze distance, iconic plateau completeness.",
            "micro_actions_en": [
                "flags of cloth markers removed",
                "last scaffold planks vanish",
                "sun angle consistent with locked camera",
            ],
        },
    },
    "great_wall": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Survey crews on ridge; laborers digging foundation trenches; soldiers guarding lines.",
            "machinery_en": "Hand carts, baskets, rammed-earth rammers, rope lines.",
            "action_en": "Reappear foundation trenches and first low retaining courses along the mountain spine.",
            "micro_actions_en": [
                "staking centerline on ridge",
                "rammed earth pounded in lifts",
                "first stone footings laid",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Bricklayers; carriers bringing bricks up slopes; mortar mixers at staging.",
            "machinery_en": "Portable lime kilns (background), barrows, simple winches at steep bits.",
            "action_en": "Raise isolated stubs and short wall segments; tower bases reappear.",
            "micro_actions_en": [
                "mortar spread with trowels",
                "chains of workers passing bricks",
                "beacon tower ring growing",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Masons tying inner and outer wythes; coolie hats; foremen with rods.",
            "machinery_en": "Scaffolds on towers; hand-crank winches; bamboo poles.",
            "action_en": "Restore continuous wall runs; expose rammed-earth core between brick skins where needed.",
            "micro_actions_en": [
                "scaffold boards lifted",
                "chipping old mortar",
                "watchtower roofs framed",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Parapet crews; carpenters setting roof beams on towers; plasterers.",
            "machinery_en": "Rope hoists along wall; stone saws pulled by teams.",
            "action_en": "Close major gaps; stand towers to near-full height; crenellations return.",
            "micro_actions_en": [
                "merlons capped",
                "signal fire bowls placed",
                "walkway planks laid",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Finish masons; cleaners; minor repair teams.",
            "machinery_en": "Light scaffolds only.",
            "action_en": "Tighten surfaces; restore uniform battlements; weathering limited to believable chips.",
            "micro_actions_en": [
                "pointing joints",
                "brushes sweeping dust",
                "tool bags carried along wall",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Patrol figures for scale; last rope teams leaving.",
            "machinery_en": "Site cleared; no heavy machines in frame.",
            "action_en": "Iconic long wall and towers readable along ridge; misty mountains consistent.",
            "micro_actions_en": [
                "banners rolled up",
                "distant birds for life",
                "sun on uniform brick",
            ],
        },
    },
    "colosseum": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Roman-style engineers with groma; laborers digging arena footprint; survey stakes.",
            "machinery_en": "Wooden cranes (treadwheel), ox carts, picks and shovels.",
            "action_en": "Lay elliptical foundation ring and first low tuff/concrete courses of outer wall.",
            "micro_actions_en": [
                "chalk arcs for ellipse",
                "concrete poured in timber forms",
                "first travertine drums arrive",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Stone carvers; masons setting voussoirs; teams raising arch centers.",
            "machinery_en": "Wooden centering for arches; A-frames; rope capstans.",
            "action_en": "Rebuild disconnected arcade fragments into coherent lower rings.",
            "micro_actions_en": [
                "keystones tapped",
                "scaffold on arena rim",
                "dust clouds from cutting",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Vault builders; bricklayers on radial walls; timber carpenters.",
            "machinery_en": "Large wooden cranes; pulley teams; wheelbarrows of pozzolana.",
            "action_en": "Restore radial vault network and inner bowl structure; hypogeum grid returns.",
            "micro_actions_en": [
                "formwork struck",
                "brick arches closed",
                "arena sand raked",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Facade masons; teams on multiple levels; sculptors dressing travertine.",
            "machinery_en": "Ring scaffolds; hand winches; water barrels for dust.",
            "action_en": "Close outer ring; stacked arches read as Colosseum facade; partial upper losses remain.",
            "micro_actions_en": [
                "hoisting arch blocks",
                "workers on cordage",
                "arena vomitoria framed",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Detail crews; metalworkers setting bronze clamps (generic); cleaners.",
            "machinery_en": "Light scaffolds; hand tools.",
            "action_en": "Repair missing arch stones; unify facade rhythm; subtle damage only.",
            "micro_actions_en": [
                "clamp holes filled",
                "chipped corners restored",
                "pigeons scared off",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Final inspectors; small figures on upper walk for scale.",
            "machinery_en": "Scaffold strike; cleared arena.",
            "action_en": "Complete iconic elliptical amphitheater: coherent arches, readable interior bowl, Rome context.",
            "micro_actions_en": [
                "last ladder removed",
                "sun on travertine",
                "crowd-free monumental read",
            ],
        },
    },
    "eiffel_tower": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Puddle-iron era riveters, foremen with blueprints on boards, ground crews.",
            "machinery_en": "Steam derrick (generic), guy wires, rivet furnaces, hand rivet guns.",
            "action_en": "Anchor bolts and first stub lattice at legs; tiny foundation forms reappear.",
            "micro_actions_en": [
                "heated rivets tossed",
                "teams lead lines",
                "sparks at forge",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Ironworkers on partial legs; painters priming; riggers.",
            "machinery_en": "Traveling cranes on temporary trestles; chain hoists.",
            "action_en": "Raise incomplete lattice legs and scattered upper stubs toward mid-height.",
            "micro_actions_en": [
                "diagonal braces bolted",
                "workers in vintage work clothes",
                "cable tensioning",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Lattice gangs; boilermakers; signalmen with flags.",
            "machinery_en": "Elevated platforms; pneumatic riveters (period look); winches.",
            "action_en": "Reconnect first and second platforms and main cross-bracing; tower silhouette grows tall.",
            "micro_actions_en": [
                "platform decks laid",
                "guardrails staged",
                "Paris park tiny at base",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Upper iron crews; painters; antenna riggers (generic).",
            "machinery_en": "Traveling climbers on tower; small hoists on spire line.",
            "action_en": "Restore upper lattice and shortened spire sections toward full height profile.",
            "micro_actions_en": [
                "spire sections lifted",
                "rivet lines marching upward",
                "wind guys vibrating",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Finishing teams; metal polishers; lighting crews (generic lanterns).",
            "machinery_en": "Light jibs at top; safety nets.",
            "action_en": "Complete top kiosks and needle; fix localized lattice losses; believable fresh paint patches.",
            "micro_actions_en": [
                "last rivet checks",
                "paint brushes",
                "flags furled",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Tiny figures on decks for scale; maintenance leaving field.",
            "machinery_en": "All temporary rigs gone.",
            "action_en": "Full wrought-iron lattice tower from Champ de Mars: four legs, platforms, spire — iconic silhouette.",
            "micro_actions_en": [
                "lattice shadow pattern crisp",
                "park trees static in background",
                "camera locked timelapse feel",
            ],
        },
    },
    "taj_mahal": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Mughal-style masons; marble cutters; symmetry surveyors with water levels.",
            "machinery_en": "Wooden cranes; ox carts; saws in water trenches.",
            "action_en": "Raise plinth grid and first marble drum sections on river-adapted foundations.",
            "micro_actions_en": [
                "reflecting pool re-flooded edge",
                "marble slabs skidded on rollers",
                "minaret footings poured",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Inlay artisans; scaffold crews; cleaners washing dust.",
            "machinery_en": "Rope hoists along minarets; wooden wheels.",
            "action_en": "Rebuild broken dome base and minaret stumps; scattered facade fragments rejoin.",
            "micro_actions_en": [
                "pietra dura chips placed",
                "arches centered",
                "white marble gleams",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Carvers; scaffolding specialists; teams on onion dome ribs.",
            "machinery_en": "Radial wooden centering for dome; pulleys at minaret tops.",
            "action_en": "Close structural cores under marble; dome curvature returns; four minarets rise straight.",
            "micro_actions_en": [
                "ribs locked",
                "marble panels hoisted",
                "calligraphy bands masked then revealed",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Facade polishers; garden crews aligning paths; marble teams on iwans.",
            "machinery_en": "Light bamboo scaffolds; hand winches.",
            "action_en": "Restore missing dome cladding and minaret tops; major silhouette readable.",
            "micro_actions_en": [
                "minaret finials placed",
                "dome sheen uniform",
                "pool symmetry fixed",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Detail inlay crews; gentle cleaners; inspectors.",
            "machinery_en": "Minimal scaffolding.",
            "action_en": "Repair fine cracks and inlay loss; subtle aging only.",
            "micro_actions_en": [
                "semi-precious chips set",
                "brushes along joints",
                "sun glints on marble",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Few robed figures for scale; gardeners finishing.",
            "machinery_en": "Gone from view.",
            "action_en": "Perfect symmetrical Taj: white marble, central dome, four minarets, reflecting axis.",
            "micro_actions_en": [
                "birds over pool",
                "last scaffold cleared",
                "mirrored facade in water",
            ],
        },
    },
    "christ_redeemer": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Concrete crews; rebar tiers; surveyors on Corcovado pedestal.",
            "machinery_en": "Mixers (period), wooden forms, hand vibrators.",
            "action_en": "Pour pedestal core and first internal column stubs for statue base.",
            "micro_actions_en": [
                "rebar cages tied",
                "concrete buckets swung",
                "mist over Rio bay",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Formworkers; crane signalers; soapstone tile setters beginning lower robe.",
            "machinery_en": "Guyed wooden crane; scaffolding on pedestal.",
            "action_en": "Grow fractured torso remnants; pedestal plus lower folds return.",
            "micro_actions_en": [
                "tiles pressed into mortar",
                "workers rappel lines",
                "clouds over city",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Armature welders (generic); sculptors; high-work specialists.",
            "machinery_en": "Spider scaffolds around core; winches for arm stubs.",
            "action_en": "Expose then re-cover reinforced core with soapstone; arms lengthen toward cross span.",
            "micro_actions_en": [
                "torch sparks hidden off-frame",
                "measuring calipers",
                "rope nets",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Head sculptors; facial detail teams; safety crews.",
            "machinery_en": "Suspended platforms at shoulders.",
            "action_en": "Restore upper body and head mass; silhouette becomes unmistakable.",
            "micro_actions_en": [
                "facial planes carved",
                "hands shaped",
                "robe folds deepened",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Finish carvers; patina washers; maintenance climbers.",
            "machinery_en": "Light ropes only.",
            "action_en": "Repair micro-losses on hands and robe edges; subtle weathering.",
            "micro_actions_en": [
                "sponge washing",
                "chip fills",
                "seagulls distant",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Final rope teams leaving; tiny tourists omitted or distant.",
            "machinery_en": "Clear.",
            "action_en": "Full art-deco Christ with outstretched arms over Rio — iconic pose, pedestal, skyline.",
            "micro_actions_en": [
                "last harness coiled",
                "sun on soapstone",
                "arms wide symmetrical",
            ],
        },
    },
    "statue_of_liberty": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Pedestal stone masons; riggers; rivet apprentices.",
            "machinery_en": "Derricks on pedestal; steam winches; rivet forges.",
            "action_en": "Rebuild pedestal crown line fragments; first internal frame stubs inside feet.",
            "micro_actions_en": [
                "granite blocks keyed",
                "chains tightened",
                "harbor water sparkle",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Copper coppersmiths; frame fitters; teams raising lower robe panels.",
            "machinery_en": "Internal spiral stair staging; hand riveters.",
            "action_en": "Reconnect lower copper skin and frame around legs; scattered upper pieces reappear.",
            "micro_actions_en": [
                "repoussé panels lifted",
                "rivet lines glowing hot",
                "internal grid shadow",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Armature crews; torch arm specialists; crown spike teams.",
            "machinery_en": "Traveling scaffold inside statue; small cranes on pedestal roof.",
            "action_en": "Expose then re-cover inner Eiffel-style frame; torso and armature align.",
            "micro_actions_en": [
                "torso plates sequenced",
                "shoulder seams closed",
                "safety nets billow",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Torch welders (generic); ladder crews; crown installers.",
            "machinery_en": "Booms reaching torch zone; harnesses.",
            "action_en": "Restore torch arm and crown spikes; upper silhouette nears completion.",
            "micro_actions_en": [
                "torch flame cavity capped",
                "crown rays bolted",
                "tablet outline sharpened",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Patina brush teams; detail smiths; rope cleaners.",
            "machinery_en": "Light jibs.",
            "action_en": "Green copper patina evenness; fix cracks; believable new copper seams.",
            "micro_actions_en": [
                "acid wash mist",
                "rivet heads uniform",
                "rope sway",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Last inspectors on pedestal; ferries distant.",
            "machinery_en": "Harbor cranes in far background only.",
            "action_en": "Full Liberty: torch, crown, robe, pedestal — classic harbor three-quarter read.",
            "micro_actions_en": [
                "flag omitted or generic",
                "sun on copper",
                "camera locked",
            ],
        },
    },
    "hanging_gardens": {
        _tk("fully_removed", "near_disappearance"): {
            "workers_en": "Canal diggers; surveyors; mud-brick molders.",
            "machinery_en": "Shadufs, sledges, reed bundles; kilns smoking in distance.",
            "action_en": "Mark terrace footprint; first low retaining mounds and irrigation trenches.",
            "micro_actions_en": [
                "string lines on plain",
                "wet mud in molds",
                "first reeds stacked",
            ],
        },
        _tk("near_disappearance", "fragmented_ruins"): {
            "workers_en": "Gardeners planting saplings; masons stacking baked brick; waterproofers with bitumen pots.",
            "machinery_en": "Arch centering; hand pumps; buckets on ropes.",
            "action_en": "Raise broken terrace blocks and isolated walls; channels begin to flow.",
            "micro_actions_en": [
                "bitumen brushed on layers",
                "lead sheets rolled (generic)",
                "water trickle in ditch",
            ],
        },
        _tk("fragmented_ruins", "core_structure_exposed"): {
            "workers_en": "Irrigation engineers; terrace crews; rope teams lifting stone.",
            "machinery_en": "Wooden cranes; terraced ramps; clay pipe layers.",
            "action_en": "Expose stepped masonry and waterproof courses; terrace stack grows with visible channels.",
            "micro_actions_en": [
                "pipes mortared in",
                "workers on tiers",
                "wet shine on bitumen",
            ],
        },
        _tk("core_structure_exposed", "major_partial_loss"): {
            "workers_en": "Planters; tree hoisting teams; gardeners pruning.",
            "machinery_en": "Elevated walkways; pulleys to upper tiers.",
            "action_en": "Collapse repairs reversed: upper terraces refill; lush canopy thickens.",
            "micro_actions_en": [
                "root balls swung",
                "leaves flutter timelapse",
                "water cascades restart",
            ],
        },
        _tk("major_partial_loss", "weathered_damage"): {
            "workers_en": "Irrigation testers; leaf sweepers; masons touching courses.",
            "machinery_en": "Light scaffolds on greenery.",
            "action_en": "Restore dense planting and flowing water; only mild wear remains.",
            "micro_actions_en": [
                "spray mist in air",
                "drips on brick",
                "birds crossing",
            ],
        },
        _tk("weathered_damage", "final_complete"): {
            "workers_en": "Final gardeners; figures on lowest terrace for scale.",
            "machinery_en": "Tools away; peaceful site.",
            "action_en": "Legendary tiered gardens: trees, cascades, baked brick faces — full cross-section read.",
            "micro_actions_en": [
                "water sparkle",
                "canopy dense",
                "horizon hazy Mesopotamia",
            ],
        },
    },
}


def _default_reconstruction_labor(from_key: str, to_key: str) -> dict[str, Any]:
    return {
        "workers_en": "Construction crews, masons, riggers, and laborers in period-appropriate work clothes.",
        "machinery_en": "Scaffolding, hand winches, barrows, rope hoists — generic unbranded site equipment.",
        "action_en": f"Physical build-up from {from_key.replace('_', ' ')} toward {to_key.replace('_', ' ')} with believable staged assembly.",
        "micro_actions_en": [
            "workers pass materials hand-to-hand",
            "dust and chips in timelapse motion",
            "shadows crawl as time compresses",
        ],
    }


def build_transition_profiles(
    structure_key: str,
    stage_sequence: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Reconstruction clips in playback order (empty -> complete)."""
    labor_map = STRUCTURE_RECONSTRUCTION_LABOR.get(structure_key, {})
    transition_keys = _build_reconstruction_transition_keys(stage_sequence or FULL_STAGE_SEQUENCE)
    out: list[dict[str, Any]] = []
    for from_key, to_key in transition_keys:
        key = _tk(from_key, to_key)
        block = labor_map.get(key) or _default_reconstruction_labor(from_key, to_key)
        out.append(
            {
                "from_stage_key": from_key,
                "to_stage_key": to_key,
                "workers_en": block["workers_en"],
                "machinery_en": block["machinery_en"],
                "action_en": block["action_en"],
                "micro_actions_en": list(block.get("micro_actions_en") or []),
            }
        )
    return out


STRUCTURE_DECONSTRUCTION_MECHANICS: dict[str, str] = {
    "giza_pyramids": (
        "Deconstruction follows gravity and block-by-block logistics: casing peels first, then upper course loss, "
        "then stepped core exposure, ending with low rubble and foundation traces."
    ),
    "great_wall": (
        "Erosion and wall-segment failure progress along ridge joints: parapets chip first, then tower collapses, "
        "then skin loss reveals rammed-earth cores before isolated stubs remain."
    ),
    "colosseum": (
        "Loss starts at facade arches and ring continuity, then vault failures expose radial skeleton, "
        "then detached masonry islands remain at arena footprint level."
    ),
    "eiffel_tower": (
        "Lattice removal progresses top-down and by structural members: secondary bracing disappears before main legs, "
        "ending with anchor-zone remnants only."
    ),
    "taj_mahal": (
        "Marble cladding and decorative inlay degrade first, then dome/minaret upper masses reduce, "
        "then structural cores and plinth traces remain with scattered stone debris."
    ),
    "christ_redeemer": (
        "Surface soapstone loss and limb fractures occur first, then torso mass reduction exposes concrete armature, "
        "ending with pedestal-adjacent fragments only."
    ),
    "statue_of_liberty": (
        "Copper skin fractures and landmark appendages fail first (torch/crown), then frame exposure increases, "
        "then only minor remnants near pedestal crown line remain."
    ),
    "hanging_gardens": (
        "Biological and hydraulic decline leads: vegetation thins and channels fail first, then terrace collapse exposes "
        "masonry waterproofing layers, ending in low ruin contours."
    ),
}


class MonumentStage(BaseModel):
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
    photo_director_note_en: str | None = None


def select_structure_type(preferred: str | None = None) -> str:
    if not preferred or preferred == "random":
        return random.choice(list(STRUCTURE_TYPES.keys()))
    if preferred in STRUCTURE_TYPES:
        return preferred
    for key in STRUCTURE_TYPES:
        if preferred.lower() in key:
            return key
    return "colosseum"


def _build_visual_prompt(structure: dict[str, Any], stage_key: str) -> str:
    stage = STAGE_TEMPLATES[stage_key]
    structure_key = structure.get("key", "")
    unique_stage_detail = STRUCTURE_STAGE_DETAILS.get(structure_key, {}).get(stage_key, "")
    deconstruction_mechanics = STRUCTURE_DECONSTRUCTION_MECHANICS.get(
        structure_key,
        "Physical deconstruction must follow gravity, structural dependencies, and material behavior.",
    )
    camera_directive = STRUCTURE_CAMERA_DIRECTIVES.get(
        structure_key,
        "Three-quarter exterior view, medium-wide lens, level horizon, upright monument.",
    )
    return (
        f"MONUMENT: {structure['name_en']}\n"
        f"LOCATION: {structure['location']}\n"
        f"STAGE: {stage['name_en']}\n\n"
        "TIMELAPSE RULES:\n"
        "- Fixed camera, same lens, same frame composition in all stages\n"
        "- Same weather/background; only monument state changes (each stage more damaged than the iconic complete state — never repaired or restored)\n"
        "- Full monument must be fully visible in frame at all times (no cropping of top, base, or side mass)\n"
        "- Camera must stay above the monument top line for a clear high-angle overview\n"
        "- Keep the frame upright: do not rotate, flip, or tilt the image\n"
        "- Horizon must stay level (no dutch angle)\n"
        "- Photorealistic smartphone/drone hybrid look, no CGI/cartoon\n"
        "- No logos or readable text\n\n"
        f"CAMERA POSITION: {camera_directive}\n\n"
        f"IDENTITY: {structure['identity']}\n"
        f"ENGINEERING DETAIL: {structure['engineering']}\n"
        f"MATERIALS: {structure['materials']}\n"
        f"SIGNATURE ELEMENTS: {structure['signature_elements']}\n\n"
        f"TRANSFORMATION: {stage['action_en']}\n"
        f"UNIQUE STAGE DETAIL: {unique_stage_detail}\n"
        f"DECONSTRUCTION MECHANICS: {deconstruction_mechanics}\n"
        "REFERENCE-IMAGE CHAIN: frames are produced in order from the iconic complete state toward the cleared site; "
        "describe ONLY this stage's physical state. Background and camera stay locked; no logos or readable text."
    )


async def run_mode11_scenario_writer(
    structure_type: str | None = None,
    language: str = "ru",
    num_stages: int = DEFAULT_NUM_STAGES,
    control: dict | None = None,
) -> dict[str, Any]:
    from pipeline_control import checkpoint

    await checkpoint(control)
    structure_key = select_structure_type(structure_type)
    structure = dict(STRUCTURE_TYPES[structure_key])
    structure["key"] = structure_key

    num_stages = _clamp_mode11_num_stages(num_stages)

    creative = get_creative_blueprint(structure_key)
    stage_director: dict[str, str] = dict(creative.get("stage_photo_director") or {})

    stage_sequence = _select_stage_sequence(num_stages)
    profile_note_en = (
        creative.get("profile_7_en") if len(stage_sequence) >= 7 else creative.get("profile_5_en")
    ) or ""
    scenes: list[dict[str, Any]] = []
    for i, stage_key in enumerate(stage_sequence):
        stage = STAGE_TEMPLATES[stage_key]
        next_key = stage_sequence[min(i + 1, len(stage_sequence) - 1)]
        next_stage = STAGE_TEMPLATES[next_key]
        scenes.append(
            MonumentStage(
                index=i,
                stage_key=stage_key,
                name=stage["name"],
                name_en=stage["name_en"],
                start_state=stage["name"],
                start_state_en=stage["name_en"],
                end_state=next_stage["name"],
                end_state_en=next_stage["name_en"],
                visual_prompt=_build_visual_prompt(structure, stage_key),
                action=stage["action"],
                action_en=stage["action_en"],
                build_intensity="high" if stage_key in ("major_partial_loss", "core_structure_exposed") else "medium",
                is_peak_moment=stage_key == "core_structure_exposed",
                photo_director_note_en=stage_director.get(stage_key),
            ).model_dump()
        )

    transition_profiles = build_transition_profiles(structure_key, stage_sequence)

    if language == "en":
        title = f"Timelapse: {structure['name_en']} — construction & restoration build-up"
    else:
        title = f"Timelapse: {structure['name']} — строительство и восстановление (таймлапс)"

    return {
        "title": title,
        "title_en": f"Timelapse: {structure['name_en']} — construction & restoration build-up",
        "structure_type": structure_key,
        "structure_name": structure["name"],
        "structure_name_en": structure["name_en"],
        "location_name": structure["location"],
        "camera_position_en": STRUCTURE_CAMERA_DIRECTIVES.get(
            structure_key,
            "Three-quarter exterior view, medium-wide lens, level horizon, upright monument.",
        ),
        "transition_profiles": transition_profiles,
        "scenes": scenes,
        "total_duration": len(scenes) * 6,
        "num_stages": len(stage_sequence),
        "narrative_arc_en": creative.get("narrative_en") or "",
        "narrative_arc_ru": creative.get("narrative_ru") or "",
        "photo_generation_plan_en": list(creative.get("photo_plan_en") or []),
        "video_generation_plan_en": list(creative.get("video_plan_en") or []),
        "stage_count_profile_en": profile_note_en,
        "creative_blueprint_key": structure_key,
    }
