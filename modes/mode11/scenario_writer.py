"""
Mode 11 Scenario Writer — Landmark timelapse (reference chain complete→site; video playback build-up).

Default uses six stages; clips interpolate from emptier to more complete with landmark-specific labor.
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

DEFAULT_NUM_STAGES = 6

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

# Authoritative per-stage copy for **5-scene runs only** (_select_stage_sequence(5) keys, complete → cleared).
# Keys match those five milestones: final_complete → major_partial_loss → core_structure_exposed → fragmented_ruins → fully_removed.
STRUCTURE_FIVE_SCENE_DETAIL_EN: dict[str, dict[str, str]] = {
    "giza_pyramids": {
        "final_complete": (
            "Great Pyramid of Khufu (Cheops) fully finished: smooth bright white limestone casing, gilded pyramidion on "
            "the apex; original height read ~146.6 m; crisp pyramid geometry."
        ),
        "major_partial_loss": (
            "Outer casing blocks removed and pyramidion taken away; stepped core masonry exposed. Overall height still reads "
            "similar, but every face is visibly stepped, not smooth slabs."
        ),
        "core_structure_exposed": (
            "Upper half of the pyramid dismantled above ~mid-height (roof line near ~70 m gone). Lower half remains with a "
            "flat truncated top; internal passages and chambers partly visible or open."
        ),
        "fragmented_ruins": (
            "Only the base survives — roughly the first 10–15 courses (~15 m tall), reading as a truncated platform stump. "
            "The main pyramid volume above is removed."
        ),
        "fully_removed": (
            "Leveled limestone plateau of the Giza desert: no pyramid mass, only graded desert ground and distant haze — "
            "same horizon, empty construction-free space."
        ),
    },
    "great_wall": {
        "final_complete": (
            "Ming-era wall segment complete: height ~7–8 m, crenellated parapet, watchtowers with loopholes and passage gates, "
            "continuous ridge-mounted curtain."
        ),
        "major_partial_loss": (
            "Parapet merlons and the upper masonry course stripped off; towers still present but shortened; curtain height "
            "reduced to ~5 m."
        ),
        "core_structure_exposed": (
            "Tower superstructures demolished down to wall deck level; upper third of wall removed; height near ~3 m; "
            "loopholes and elevated walkways gone."
        ),
        "fragmented_ruins": (
            "Outer stone/brick facing shells removed; a broad ridge berm of exposed rammed-earth core (rice-paste mortar) "
            "is all that remains — no neat battlements."
        ),
        "fully_removed": (
            "Mountain ridgeline with natural relief only: no wall line, towers, or earth-core mound — bare geological spine."
        ),
    },
    "colosseum": {
        "final_complete": (
            "Complete Flavian amphitheater: three stacked arcaded orders, fourth attic with mast fixtures for the velarium; "
            "open hypogeum, sand arena, and seating bowl all coherent."
        ),
        "major_partial_loss": (
            "Attic tier and velarium masts dismantled; three arcaded rings remain; arena floor and hypogeum vaults still read "
            "intact below."
        ),
        "core_structure_exposed": (
            "Third (Corinthian) and second (Ionic) arcaded levels removed; only the first (Doric) tier stands ~12 m; hypogeum "
            "largely filled/silted and only partly legible."
        ),
        "fragmented_ruins": (
            "First order cleared down to springing of the ground-floor arches; exposed concrete platform ring and stumps of "
            "travertine piers only — no continuous amphitheater bowl."
        ),
        "fully_removed": (
            "Shallow basin where the ancient artificial lake sat: no standing arches, concrete collar, or arena ring — "
            "empty depressed Roman ground matching the site footprint."
        ),
    },
    "eiffel_tower": {
        "final_complete": (
            "Full iron lattice tower ~300 m to the third platform (~330 m including slender antenna/telegraph spire); public "
            "lifts; all three platforms and upper lattice complete."
        ),
        "major_partial_loss": (
            "Upper needle and all iron above the third platform (~276 m) removed; new top is the third deck — height read "
            "~276 m."
        ),
        "core_structure_exposed": (
            "All lattice between second (~115 m) and third platforms removed; lower half with first and second platforms "
            "remains; upper silhouette halved."
        ),
        "fragmented_ruins": (
            "Only the four inclined legs tied by the first platform (~57 m) remain; central mast and upper platforms gone — "
            "low ‘table’ of iron at splay-tips only."
        ),
        "fully_removed": (
            "Champ de Mars lawns: concrete piers shaved flush with grade; no tower iron, no stump — open park perspective "
            "toward Trocadéro axis."
        ),
    },
    "taj_mahal": {
        "final_complete": (
            "Complete white-marble mausoleum complex: four flanking minarets, main onion dome, four subsidiary domes/chhatris, "
            "reflecting canal charbagh, red-sandstone gate screen when in view."
        ),
        "major_partial_loss": (
            "All four minarets and the cluster of small domes removed; main marble block under the primary dome still stands "
            "symmetrically."
        ),
        "core_structure_exposed": (
            "Marble veneer and pietra dura inlay fully stripped; red sandstone structural core and ribs exposed across drum "
            "and walls."
        ),
        "fragmented_ruins": (
            "Main dome and upper third of walls dismantled; stump of mausoleum base ~15 m tall above the plinth — no soaring "
            "silhouette."
        ),
        "fully_removed": (
            "Yamuna riverfront terrace graded flat: no marble mass, domes, or minarets — only leveled podium plane and water "
            "edge context."
        ),
    },
    "christ_redeemer": {
        "final_complete": (
            "Finished Art Deco statue ~38 m including pedestal, ~28 m arm-span; soapstone tile skin over "
            "reinforced-concrete structure."
        ),
        "major_partial_loss": (
            "Soapstone cladding stripped from head and arms; gray concrete/rebar skeleton exposed there; torso and legs "
            "still covered in soapstone tiles."
        ),
        "core_structure_exposed": (
            "Every soapstone tile removed; complete exposed concrete carcass of the colossus including limbs and core shaft."
        ),
        "fragmented_ruins": (
            "Reinforced concrete of arms, head, and upper torso above the waist removed; lower legs fused to pedestal block "
            "remain as a short monolithic stub."
        ),
        "fully_removed": (
            "Corcovado summit natural rock and vegetation only: no statue mass or artificial pedestal podium — open "
            "mountain viewpoint toward Guanabara Bay."
        ),
    },
    "statue_of_liberty": {
        "final_complete": (
            "Completed copper-clad colossus on massive pedestal; ~93 m to torch tip; green patina, raised torch, seven-ray "
            "diadem."
        ),
        "major_partial_loss": (
            "Torch assembly and upper crown spikes removed; head keeps basic volume but no radiating rays or flame cup."
        ),
        "core_structure_exposed": (
            "Copper skin off head and torch-bearing right arm; riveted steel armature of Eiffel’s design visible in those "
            "zones; robe still sheeted elsewhere."
        ),
        "fragmented_ruins": (
            "All copper sheets stripped; internal steel mast and armatures largely cut away; granite pedestal mass may remain "
            "as truncated base."
        ),
        "fully_removed": (
            "Liberty Island foreground without colossal figure or large dressed pedestal block; historic Fort Wood masonry "
            "may remain at shoreline; harbor water and skyline unchanged."
        ),
    },
    "hanging_gardens": {
        "final_complete": (
            "Reconstruction reference: four superposed landscaped terraces ~40–50 m total stack; dense trees, shrubs, and sheet "
            "water cascades; baked-brick vaults hidden by plant soil."
        ),
        "major_partial_loss": (
            "All plants, humus, and deck soil lifted off; terraces show dull lead waterproof pans and naked brick groin "
            "vaults — engineering skeleton visible."
        ),
        "core_structure_exposed": (
            "Third and fourth landscaped tiers entirely gone; only two lower tiers remain totaling ~20 m visible ziggurat "
            "stump."
        ),
        "fragmented_ruins": (
            "Second and first planted decks removed; broad brick podium foundation, hydraulic lift pits, and broken hoists "
            "only — no vertical garden stack."
        ),
        "fully_removed": (
            "Mesopotamian river plain (Euphrates or Nineveh haze line): flat alluvium without ziggurat or terrace shadows — "
            "legendary site reads empty."
        ),
    },
}

# **7-scene runs only**: matches FULL_STAGE_SEQUENCE order (complete → cleared).
# Keys: final_complete → weathered_damage → major_partial_loss → core_structure_exposed → fragmented_ruins → near_disappearance → fully_removed
STRUCTURE_SEVEN_SCENE_DETAIL_EN: dict[str, dict[str, str]] = {
    "giza_pyramids": {
        "final_complete": (
            "Great Pyramid of Khufu complete: polished white limestone casing, golden pyramidion; all ~2.3 M blocks in "
            "place; internal chambers and corridors sealed and intact."
        ),
        "weathered_damage": (
            "Pyramidion removed; upper third of casing stripped from each face — stepped core blocks visible at the summit, "
            "casing preserved only on lower ~two-thirds; silhouette slightly truncated."
        ),
        "major_partial_loss": (
            "All casing gone — fully stepped core like medieval views; internal corridors still largely hidden within masonry."
        ),
        "core_structure_exposed": (
            "Upper half dismantled above the King’s Chamber level — vast flat truncation deck; relieving chambers and "
            "granite beams exposed from within the mass."
        ),
        "fragmented_ruins": (
            "Chamber-and-corridor zone removed down to ~30–50 m height — only lower third remains; Queen’s Chamber, "
            "descending corridor, and shafts fully open to the eye."
        ),
        "near_disappearance": (
            "Only roughly the first ten masonry courses plus footing remain — low 3–4 m platform suggesting unfinished "
            "base; faint ramp berms still readable."
        ),
        "fully_removed": (
            "Leveled Giza plateau limestone: no blocks or foundation pits — bare natural rock plane and desert, same horizon."
        ),
    },
    "great_wall": {
        "final_complete": (
            "Ming stone-brick curtain complete: ~8 m tall, crenellated parapet with loopholes; watchtowers every ~200 m with "
            "lifted gates; continuous fighting walkway on top."
        ),
        "weathered_damage": (
            "Merlons and upper walkway deck removed — wall top flush; tower heights cut by ~⅓ losing upper stories and roof caps."
        ),
        "major_partial_loss": (
            "Towers lowered to wall deck only; upper wall course stripped — height ~5 m; outer ashlar facing off exposing "
            "rammed-earth core bound with rice mortar."
        ),
        "core_structure_exposed": (
            "Curtain sliced to ~3 m; only a ~4 m-wide earth berm flanked by tatters of side stone cladding — towers gone."
        ),
        "fragmented_ruins": (
            "Earth core shaved to ~1.5 m — broad but very low ridge scarcely reading against mountain slope; compaction "
            "laminations visible."
        ),
        "near_disappearance": (
            "All fill removed — sporadic foundation stones and leveled 3–4 m wide alignment strips, grass-colonized, hint at "
            "the old base line."
        ),
        "fully_removed": (
            "Mountain spine with zero wall or earthworks — only native plants and outcrops; no anthropogenic ridge mound."
        ),
    },
    "colosseum": {
        "final_complete": (
            "Full amphitheater: three arcaded tiers, fourth attic with velarium masts; hypogeum beneath sand arena; marble "
            "seat tiers; wooden arena floor; lift shafts and cages in the underground service grid."
        ),
        "weathered_damage": (
            "Attic + velarium hardware stripped; uppermost seating sweeps dismantled — three arch orders still fully wrap the "
            "ellipse."
        ),
        "major_partial_loss": (
            "Third Corinthian order and part of the second Ionic ring removed — outer height drops to second-tier springing; "
            "hypogeum largely intact though arena decking is breached."
        ),
        "core_structure_exposed": (
            "Second order gone — sole remaining Doric tier ~12 m; hypogeum filled with soil and refuse so only its roof ghost "
            "shows."
        ),
        "fragmented_ruins": (
            "First order deconstructed to arch springing line; interior radial walls gone — perimeter travertine piers on a "
            "concrete ring; hypogeum fully buried under debris."
        ),
        "near_disappearance": (
            "Only foundation platform and isolated pier stumps — travertine rubble defines the footprint; interior graded flat "
            "with gravel fill."
        ),
        "fully_removed": (
            "Former lake depression: grassed low basin with natural hummocks — no vaulting, concrete, or seating ring remains."
        ),
    },
    "eiffel_tower": {
        "final_complete": (
            "Complete tower to ~330 m with broadcast antennas; three platforms, lifts, tricolor paint finish, night lighting."
        ),
        "weathered_damage": (
            "Antenna mast and lattice above 300 m removed — height read 300 m; third gallery at 276 m becomes exposed summit."
        ),
        "major_partial_loss": (
            "Third platform and upper lattice down to ~200 m eliminated — stump near 200 m with central pylon and primary "
            "Warren trusses only."
        ),
        "core_structure_exposed": (
            "All iron above second platform (115 m) cleared — four legs still tie decks 1 and 2; lifts serve only to level two."
        ),
        "fragmented_ruins": (
            "Second deck gone; each leg shortened to ~⅓ of original height — only lower pylons linked by first platform at 57 m."
        ),
        "near_disappearance": (
            "First gallery removed; legs truncated near 10 m — four concrete socket blocks with anchor bolts and short "
            "stub columns above grade."
        ),
        "fully_removed": (
            "Champ de Mars park without tower — exposed concrete plinth pads poured for the piers (optionally earth-buried "
            "later); lawns and axis unobstructed."
        ),
    },
    "taj_mahal": {
        "final_complete": (
            "Full complex: white marble mausoleum, four ~40 m minarets, main dome, four subsidiary domes, great gate, "
            "charbagh canals, flanking mosque and jawab wings."
        ),
        "weathered_damage": (
            "Minarets demolished to stubs; chhatris around the drum removed — central marble block with sole great dome "
            "remains symmetrically."
        ),
        "major_partial_loss": (
            "Marble veneer stripped from the mausoleum; gate and lateral buildings taken down — red sandstone core exposed; "
            "formal garden geometry still readable."
        ),
        "core_structure_exposed": (
            "Main dome and upper third of mausoleum walls removed — ~15 m high battered stump resembling unfinished fort "
            "works."
        ),
        "fragmented_ruins": (
            "Mausoleum walls cleared to stylobate — only ~7 m-high marble-faced platform; canals silted, planting disrupted."
        ),
        "near_disappearance": (
            "Stylobate dismantled and pile foundations drawn — timber piles and well-caisson shadows in the soil only."
        ),
        "fully_removed": (
            "Yamuna foreshore terrace slowly rewilding — graded vacant mud bank without building masses."
        ),
    },
    "christ_redeemer": {
        "final_complete": (
            "Completed monument ~38 m with pedestal, 28 m arm span; soapstone skin; night accent lighting; crow’s nest over "
            "Rio panorama."
        ),
        "weathered_damage": (
            "Soapstone removed from head and hands revealing reinforced-concrete structure there; torso and legs still tiled."
        ),
        "major_partial_loss": (
            "All soapstone cladding gone — entire figure reads as exposed concrete with rebar and formwork scars."
        ),
        "core_structure_exposed": (
            "Arms and head concrete demolished — columnar torso-and-leg shaft rising from pedestal."
        ),
        "fragmented_ruins": (
            "Torso and legs above pedestal jackhammered away — short ~3 m reinforced-concrete plinth cube only."
        ),
        "near_disappearance": (
            "Pedestal dismantled to footing — bearing slab plus anchor bolts at rock interface, no vertical artwork above."
        ),
        "fully_removed": (
            "Corcovado summit: naked bedrock and a small leveled landing — no statue pedestal bulk, jungle skyline intact."
        ),
    },
    "statue_of_liberty": {
        "final_complete": (
            "Finished 93 m colossus on pedestal: green copper skin, gold-leafed torch, seven-ray crown; internal Eiffel steel "
            "armature."
        ),
        "weathered_damage": (
            "Torch rig and crown spikes removed — head volume simplified without rays."
        ),
        "major_partial_loss": (
            "Copper sheets off head and torch arm — skeletal steel visible in those zones; remainder still patinated copper."
        ),
        "core_structure_exposed": (
            "All copper gone — central mast, auxiliary trusses, and interior spiral stair fully visible aerially."
        ),
        "fragmented_ruins": (
            "Steel skeleton cut down to waist — lower trusses plus granite pedestal base remain."
        ),
        "near_disappearance": (
            "Residual iron removed; pedestal stonework lowered to Fort Wood roofline — star-shaped fort walls emerging."
        ),
        "fully_removed": (
            "Liberty Island without statue or podium mass — low circular masonry of Fort Wood only; harbor vista clear."
        ),
    },
    "hanging_gardens": {
        "final_complete": (
            "Reconstruction vision: four stacked garden terraces ~50 m; each deck green with trees, waterfalls, summit "
            "pavilion; lead pans over brick vaults; active lift screws."
        ),
        "weathered_damage": (
            "Vegetation and soil lifts off every deck — dull lead waterproofing sheets naked; hoists still idle but present."
        ),
        "major_partial_loss": (
            "Third and fourth garden tiers removed — lower pair ~25 m tall; hydraulic feed broken so upper terraces dry."
        ),
        "core_structure_exposed": (
            "Second tier cleared — single lower arcade ~12 m of brick groins on columns carrying nothing above."
        ),
        "fragmented_ruins": (
            "Lower vaults demolished — massive brick footings, intake culverts, and broken chain pumps in excavation only."
        ),
        "near_disappearance": (
            "Foundation pits filled and graded — faint clay piping and shallow channel scars hint at irrigation only."
        ),
        "fully_removed": (
            "Euphrates / Nineveh floodplain — natural silty ground with barely perceptible ancient ditch lines, no standing "
            "garden engineering."
        ),
    },
}

# Per-landmark 6-scene pacing plans (playback direction: empty -> complete).
# Sequence is aligned to _select_stage_sequence(6):
# fully_removed -> near_disappearance -> fragmented_ruins -> core_structure_exposed -> major_partial_loss -> final_complete
STRUCTURE_SIX_SCENE_PROFILE_EN: dict[str, str] = {
    "giza_pyramids": (
        "Six scenes (Giza): 0% empty plateau -> ~3% only base grid/foundation traces and first block staging -> "
        "~10% low stepped stump starts reading -> ~25% clear lower pyramid mass with large missing upper volume -> "
        "~50% half-height pyramid body with major upper losses -> 100% complete iconic pyramids."
    ),
    "great_wall": (
        "Six scenes (Great Wall): 0% bare ridgeline -> ~3% only footing line and earth prep -> "
        "~10% short low wall segments and tower bases -> ~25% discontinuous but recognizable wall sections -> "
        "~50% long connected runs with large breaches -> 100% continuous wall and tower rhythm."
    ),
    "colosseum": (
        "Six scenes (Colosseum): 0% empty Roman ground -> ~3% elliptical foundation ring and excavation prep -> "
        "~10% low arcade stubs and partial ring start -> ~25% clear lower amphitheater bowl with major upper voids -> "
        "~50% half-preserved ring with readable ellipse -> 100% full iconic Colosseum facade and bowl."
    ),
    "eiffel_tower": (
        "Six scenes (Eiffel Tower): 0% open Champ de Mars skyline -> ~3% anchors/foundation pads and minimal steel prep -> "
        "~10% short leg stubs and initial cross-bracing -> ~25% lower tower with first platform read -> "
        "~50% mid-height tower with missing upper half -> 100% full lattice tower with platforms and spire."
    ),
    "taj_mahal": (
        "Six scenes (Taj Mahal): 0% empty terrace -> ~3% plinth/foundation preparation only -> "
        "~10% low structural start, drum/plinth mass emerging -> ~25% recognizable mausoleum base with major missing dome/minarets -> "
        "~50% half-complete main mass, upper elements heavily reduced -> 100% full Taj complex silhouette."
    ),
    "christ_redeemer": (
        "Six scenes (Christ the Redeemer): 0% empty Corcovado viewpoint -> ~3% pedestal/foundation prep only -> "
        "~10% lower core and pedestal mass start -> ~25% recognizable statue base/torso with major missing limbs -> "
        "~50% half-preserved figure silhouette with large losses -> 100% full iconic open-arm statue."
    ),
    "statue_of_liberty": (
        "Six scenes (Statue of Liberty): 0% open island/harbor without colossus -> ~3% pedestal crown and base prep only -> "
        "~10% lower structural core and partial robe base -> ~25% recognizable statue lower mass with major upper losses -> "
        "~50% half-complete statue body, torch/crown still heavily incomplete -> 100% full Liberty silhouette."
    ),
    "hanging_gardens": (
        "Six scenes (Hanging Gardens): 0% flat alluvial plain -> ~3% terrace footprint and irrigation base prep only -> "
        "~10% low masonry terraces and channel starts -> ~25% recognizable lower garden stack with sparse greenery -> "
        "~50% half-developed terraces and partial water flow -> 100% full multi-tier lush gardens with complete hydraulic read."
    ),
}


def _unique_stage_detail_for_prompt(structure_key: str, stage_key: str, num_stages: int) -> str:
    """Prefer explicit 7- or 5-scene schedules; otherwise generic STRUCTURE_STAGE_DETAILS."""
    if num_stages == 7:
        seven = STRUCTURE_SEVEN_SCENE_DETAIL_EN.get(structure_key, {}).get(stage_key, "")
        if seven:
            return seven
    if num_stages == 5:
        five = STRUCTURE_FIVE_SCENE_DETAIL_EN.get(structure_key, {}).get(stage_key, "")
        if five:
            return five
    return STRUCTURE_STAGE_DETAILS.get(structure_key, {}).get(stage_key, "")


# Appended to every still visual_prompt; keep wording aligned with mode11 video_generator + contextual_prompt_generator.
MODE11_SINGLE_CAMERA_RIG_RULES_EN = """SINGLE LOCKED CAMERA — entire reference chain (mandatory):
- One virtual camera only for stage_000…stage_last: same world position, same height, same azimuth/bearing toward the subject, same lens focal length, same 9:16 crop. Every later frame must match stage_000 framing intent pixel-for-pixel (only the monument state changes).
- When mass shrinks or disappears, do NOT zoom, do NOT widen, do NOT raise/lower the camera, do NOT re-center on rubble — keep the identical field of view; empty ground/sky fills what the monument used to occupy.
- Forbidden: alternate angle, second unit, drone path/orbit, dolly, crane, pan, tilt, roll, Dutch angle, handheld reframing, focal-length change, lens swap, digital zoom, “hero” re-compose, reframing for composition.
"""


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

def linear_monument_remaining_pct(stage_index: int, num_stages: int) -> int:
    """Share of iconic-complete mass/detail still visible: 100 = full monument, 0 = cleared site.

    Linear in stage index so reference frames and clips distribute visual change evenly over runtime
    (avoids huge early jumps then barely perceptible late edits).
    """
    if num_stages <= 1:
        return 100
    if num_stages == 6:
        # Requested pacing profile (still chain complete->empty):
        # 100 -> 50 -> 25 -> 10 -> 3 -> 0
        # Playback (empty->complete): empty, foundation prep, early start, 25%, 50%, complete.
        ladder_6 = [100, 50, 25, 10, 3, 0]
        idx = max(0, min(stage_index, len(ladder_6) - 1))
        return ladder_6[idx]
    return max(0, min(100, round(100 * (1 - stage_index / (num_stages - 1)))))


def monument_remaining_pct_rubric(pct: int) -> str:
    """Plain-English still-image checklist for a target % of iconic mass remaining."""
    if pct >= 100:
        return (
            "HOW THIS % MUST LOOK: Full iconic volume, height, and silhouette — the completed landmark unmistakable."
        )
    if pct >= 70:
        return (
            "HOW THIS % MUST LOOK: Monument still clearly dominates the frame; real damage, but most mass and outline "
            "remain; never mistaken for a ruin field."
        )
    if pct >= 45:
        return (
            "HOW THIS % MUST LOOK: Large voids and missing chunks; roughly half the ‘complete’ read is gone; "
            "silhouette fragmentary but some major masses still hint at the old shape."
        )
    if pct >= 20:
        return (
            "HOW THIS % MUST LOOK: MOSTLY GONE — low rubble rows, stumps, foundation islands, scattered spalls only; "
            "NO intact dome/tower/statue body, NO ‘nearly finished build’ read. "
            "If a casual viewer still sees the famous whole object, you FAILED the quota."
        )
    if pct > 0:
        return (
            "HOW THIS % MUST LOOK: Near-disappearance — faint footprint, a few stones, dust scuffs; "
            "no vertical landmark presence."
        )
    return (
        "HOW THIS % MUST LOOK: Cleared site only — same ground plane and distant context, zero standing monument mass."
    )


def _even_timelapse_quota_text(stage_index: int, num_stages: int) -> str:
    if num_stages <= 1:
        return ""
    pct = linear_monument_remaining_pct(stage_index, num_stages)
    step = max(1, round(100 / (num_stages - 1)))
    prev_pct = linear_monument_remaining_pct(stage_index - 1, num_stages) if stage_index > 0 else None
    next_pct = (
        linear_monument_remaining_pct(stage_index + 1, num_stages) if stage_index < num_stages - 1 else None
    )
    rubric = monument_remaining_pct_rubric(pct)

    if prev_pct is not None and next_pct is not None:
        neighbor_line = (
            f"THREE-FRAME LADDER (0–100 scale of how much of the COMPLETE monument still reads): "
            f"previous still ~{prev_pct}%, THIS still ~{pct}%, next still ~{next_pct}% — only ~{step} points per hop; "
            f"never compress multiple hops into one image.\n"
        )
    elif prev_pct is not None:
        neighbor_line = (
            f"STEP FROM PREVIOUS STILL: was ~{prev_pct}% — remove only ~{step} points of mass/detail to reach ~{pct}%.\n"
        )
    else:
        neighbor_line = (
            f"STEP FROM COMPLETE: first damaged still — drop ~{step} points from 100% to land ~{pct}%; "
            f"next still will be ~{next_pct}%.\n"
        )

    last_i = num_stages - 1
    anti_cliff = ""
    if stage_index == last_i - 1:
        anti_cliff = (
            "ANTI-FAILURE — PENULTIMATE STILL: Do NOT output an almost-intact iconic monument here while the last "
            "still is bare ground. At this quota the structure must already be *trace-level ruins* (see rubric). "
            f"The final still removes only the last ~{step} points (leftover rubble/print), not the whole landmark.\n"
        )
    if stage_index == last_i:
        anti_cliff = (
            "FINAL STILL: The frame before was already ~"
            f"{prev_pct if prev_pct is not None else step}% (near-vanish). Remove ONLY residual piles/scars — "
            f"~{step} points — to reach cleared site; do not imply a intact monument existed one frame earlier.\n"
        )

    return (
        f"PHOTO QUOTA (mandatory, numeric): THIS image = **~{pct}%** of iconic-complete visible mass, height, "
        f"silhouette, and landmark detail still present (100 = full, 0 = gone). Every consecutive pair differs by "
        f"**~{step}** points only.\n"
        f"{neighbor_line}"
        f"{anti_cliff}"
        f"{rubric}\n"
        "Map UNIQUE STAGE DETAIL onto this budget (what falls off this step), never skip the percentage.\n"
        "FORBIDDEN: a still at quota ≤30% that still reads as a mostly whole famous building; "
        "FORBIDDEN: idolizing the anchor (stage_000) — later frames must be far more destroyed AND hit the number."
    )


def _clamp_mode11_num_stages(n: int) -> int:
    """Product supports 5 (milestone), 6 (smooth build), or 7 (full arc)."""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return DEFAULT_NUM_STAGES
    if v >= 7:
        return 7
    if v >= 6:
        return 6
    return 5


def _select_stage_sequence(num_stages: int) -> list[str]:
    total = max(2, min(num_stages, len(FULL_STAGE_SEQUENCE)))
    if total == 6:
        # Custom sequence to avoid front-loaded build speed in playback:
        # complete -> 50% -> 25% -> early start -> foundation prep -> empty.
        return [
            "final_complete",
            "major_partial_loss",
            "core_structure_exposed",
            "fragmented_ruins",
            "near_disappearance",
            "fully_removed",
        ]
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
    seq = list(stage_sequence or FULL_STAGE_SEQUENCE)
    n_st = len(seq)
    transition_keys = _build_reconstruction_transition_keys(seq)
    out: list[dict[str, Any]] = []
    for from_key, to_key in transition_keys:
        key = _tk(from_key, to_key)
        block = labor_map.get(key) or _default_reconstruction_labor(from_key, to_key)
        try:
            idx_from = seq.index(from_key)
            idx_to = seq.index(to_key)
        except ValueError:
            idx_from, idx_to = n_st - 1, max(0, n_st - 2)
        c_start = linear_monument_remaining_pct(idx_from, n_st) if n_st else 0
        c_end = linear_monument_remaining_pct(idx_to, n_st) if n_st else 0
        step = abs(c_end - c_start)
        out.append(
            {
                "from_stage_key": from_key,
                "to_stage_key": to_key,
                "workers_en": block["workers_en"],
                "machinery_en": block["machinery_en"],
                "action_en": block["action_en"],
                "micro_actions_en": list(block.get("micro_actions_en") or []),
                "completeness_start_pct": c_start,
                "completeness_end_pct": c_end,
                "timelapse_step_pct": step,
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
    monument_remaining_pct: int = 100
    camera_position_en: str | None = None


def select_structure_type(preferred: str | None = None) -> str:
    if not preferred or preferred == "random":
        return random.choice(list(STRUCTURE_TYPES.keys()))
    if preferred in STRUCTURE_TYPES:
        return preferred
    for key in STRUCTURE_TYPES:
        if preferred.lower() in key:
            return key
    return "colosseum"


def _build_visual_prompt(
    structure: dict[str, Any],
    stage_key: str,
    stage_index: int = 0,
    num_stages: int = 1,
) -> str:
    stage = STAGE_TEMPLATES[stage_key]
    structure_key = structure.get("key", "")
    unique_stage_detail = _unique_stage_detail_for_prompt(structure_key, stage_key, num_stages)
    deconstruction_mechanics = STRUCTURE_DECONSTRUCTION_MECHANICS.get(
        structure_key,
        "Physical deconstruction must follow gravity, structural dependencies, and material behavior.",
    )
    camera_directive = STRUCTURE_CAMERA_DIRECTIVES.get(
        structure_key,
        "Three-quarter exterior view, medium-wide lens, level horizon, upright monument.",
    )
    quota_block = _even_timelapse_quota_text(stage_index, num_stages)
    quota_para = f"{quota_block}\n\n" if quota_block else ""
    use_five_canon = num_stages == 5 and bool(
        STRUCTURE_FIVE_SCENE_DETAIL_EN.get(structure_key, {}).get(stage_key)
    )
    use_seven_canon = num_stages == 7 and bool(
        STRUCTURE_SEVEN_SCENE_DETAIL_EN.get(structure_key, {}).get(stage_key)
    )
    use_exact_schedule = use_five_canon or use_seven_canon
    if use_seven_canon:
        detail_heading = "UNIQUE STAGE DETAIL (7-scene exact landmark schedule — follow literally)"
    elif use_five_canon:
        detail_heading = "UNIQUE STAGE DETAIL (5-scene exact landmark schedule — follow literally)"
    else:
        detail_heading = "UNIQUE STAGE DETAIL"
    return (
        f"MONUMENT: {structure['name_en']}\n"
        f"LOCATION: {structure['location']}\n"
        f"STAGE: {stage['name_en']}\n\n"
        "TIMELAPSE RULES:\n"
        "- Fixed camera, same lens, same frame composition in all stages\n"
        "- Same weather/background; only monument state changes (each stage more damaged than the iconic complete state — never repaired or restored)\n"
        "- Constant field of view vs stage_000: while the monument exists, keep its full height and footprint in frame as in the complete shot; when it is gone, show the same patch of ground/sky — never change focal length or camera distance to “fit” rubble or empty space\n"
        "- Camera must stay above the monument top line on the complete reference; later stages reuse that exact camera height and aim even when little or no monument remains\n"
        "- Keep the frame upright: do not rotate, flip, or tilt the image\n"
        "- Horizon must stay level (no dutch angle)\n"
        "- Photorealistic smartphone/drone hybrid look, no CGI/cartoon\n"
        "- No logos or readable text\n"
        + (
            "- If the 5- or 7-scene UNIQUE STAGE DETAIL conflicts with DECONSTRUCTION MECHANICS, follow the STAGE DETAIL\n"
            if use_exact_schedule
            else ""
        )
        + "\n"
        f"{MODE11_SINGLE_CAMERA_RIG_RULES_EN}\n"
        f"{quota_para}"
        f"CAMERA POSITION: {camera_directive}\n\n"
        f"IDENTITY: {structure['identity']}\n"
        f"ENGINEERING DETAIL: {structure['engineering']}\n"
        f"MATERIALS: {structure['materials']}\n"
        f"SIGNATURE ELEMENTS: {structure['signature_elements']}\n\n"
        f"TRANSFORMATION: {stage['action_en']}\n"
        f"{detail_heading}: {unique_stage_detail}\n"
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
    n_chain = len(stage_sequence)
    if len(stage_sequence) >= 7:
        profile_note_en = creative.get("profile_7_en") or ""
    elif len(stage_sequence) == 6:
        profile_note_en = STRUCTURE_SIX_SCENE_PROFILE_EN.get(
            structure_key,
            (
                "Six scenes: enforce smooth construction pacing in playback order — "
                "empty site (0%) -> foundation/prep (~3%) -> early build (~10%) -> quarter build (~25%) "
                "-> half build (~50%) -> complete iconic state (100%)."
            ),
        )
    else:
        profile_note_en = creative.get("profile_5_en") or ""
    camera_en = STRUCTURE_CAMERA_DIRECTIVES.get(
        structure_key,
        "Three-quarter exterior view, medium-wide lens, level horizon, upright monument.",
    )
    scenes: list[dict[str, Any]] = []
    for i, stage_key in enumerate(stage_sequence):
        stage = STAGE_TEMPLATES[stage_key]
        next_key = stage_sequence[min(i + 1, len(stage_sequence) - 1)]
        next_stage = STAGE_TEMPLATES[next_key]
        remaining_pct = linear_monument_remaining_pct(i, n_chain)
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
                visual_prompt=_build_visual_prompt(structure, stage_key, stage_index=i, num_stages=n_chain),
                action=stage["action"],
                action_en=stage["action_en"],
                build_intensity="high" if stage_key in ("major_partial_loss", "core_structure_exposed") else "medium",
                is_peak_moment=stage_key == "core_structure_exposed",
                photo_director_note_en=stage_director.get(stage_key),
                monument_remaining_pct=remaining_pct,
                camera_position_en=camera_en,
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
        "camera_position_en": camera_en,
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
