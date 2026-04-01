"""
Per-landmark creative briefs for Mode 11: narrative arc, photo/video prompt plans,
and per-stage director notes (all canonical stage_key values).

Used for both 5-scene (milestone) and 7-scene (full arc) profiles; the scenario
includes profile-specific wording via profile_5_en / profile_7_en.
"""

from __future__ import annotations

from typing import Any

_FULL_STAGE_ORDER = [
    "final_complete",
    "weathered_damage",
    "major_partial_loss",
    "core_structure_exposed",
    "fragmented_ruins",
    "near_disappearance",
    "fully_removed",
]

# Prepended to every landmark’s photo_plan_en so still generation enforces linear steps for ALL structures.
PHOTO_LINEAR_PACING_HEADER_EN = (
    "GLOBAL (every landmark): Obey the numeric PHOTO QUOTA / STILL-IMAGE CONTRACT in each prompt — equal steps on the "
    "0–100% ‘remaining iconic mass’ scale between consecutive frames. Forbidden: penultimate still reads mostly intact "
    "while the final still is bare ground; before the empty site, show trace-level ruins only."
)

VIDEO_LINEAR_PACING_HEADER_EN = (
    "GLOBAL (every landmark): Each clip must advance only its EVEN CLIP PACING / completeness band (~start%→~end%) "
    "steadily over the full duration — no burst-then-stall."
)


def _photo_plan_with_linear_header(photo_plan_en: list[str] | None) -> list[str]:
    rows = [str(x).strip() for x in (photo_plan_en or []) if str(x).strip()]
    if rows and rows[0] == PHOTO_LINEAR_PACING_HEADER_EN:
        return rows
    return [PHOTO_LINEAR_PACING_HEADER_EN, *rows]


def _video_plan_with_linear_header(video_plan_en: list[str] | None) -> list[str]:
    rows = [str(x).strip() for x in (video_plan_en or []) if str(x).strip()]
    if rows and rows[0] == VIDEO_LINEAR_PACING_HEADER_EN:
        return rows
    return [VIDEO_LINEAR_PACING_HEADER_EN, *rows]

STRUCTURE_CREATIVE_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "giza_pyramids": {
        "narrative_en": (
            "Giza plateau story: casing gleams on the Great Pyramid, then storms and quarry theft strip facing stones, "
            "cores stagger, and finally only desert grid lines and sand remain. Heat haze and chalky dust define every frame."
        ),
        "narrative_ru": (
            "Плато Гизы: сияющий казённик пирамид, затем ветер и утрата облицовки, обнажение ярусов ядра и в конце — "
            "пустыня и лишь намёк на основание. Сохраняйте жару, дымку Каира и масштаб всего комплекса в кадре."
        ),
        "photo_plan_en": [
            "Image 1: intact limestone casing read on main pyramid plus companion pyramids; crisp edges, long plateau shadows.",
            "Each later still: remove mass downward and outward—never rebuild; sand accumulates in sync with losses.",
            "Keep all pyramid tips below frame top edge; show companion pyramids shrinking consistently if visible.",
            "Material truth: bedding planes, joint lines, and collapse scree familiar to real masonry failures.",
            "Light: harsh sun, stable time-of-day across stages; no golden-hour jump between frames.",
            "Final frame: empty plateau; distant Cairo smear unchanged.",
        ],
        "video_plan_en": [
            "Reconstruction clips: sled teams, ramps, and course-by-course lifting—always believable to Old Kingdom logistics.",
            "Show mass returning from quarry lines toward the site; dust plumes but no modern cranes or brand markings.",
            "Preserve the southwest / elevated plateau sightline implied by the camera brief.",
            "From rubble transitions: workers re-stack cores before bright casing bands return; never pop-in whole volumes.",
            "Audio-agnostic visuals only; emphasize timelapse motion of ropes, chisels, and dragging sledges.",
        ],
        "profile_5_en": (
            "Five scenes: ~equal visual steps of remaining mass between frames (~25 percentage points each); "
            "each still must match its quota so reconstruction playback never races at the start then crawls."
        ),
        "profile_7_en": (
            "Seven scenes: finer but still linear steps (~16–17 points each); weathering and near-vanish beats split "
            "the same total mass loss evenly, not bunched at one end."
        ),
        "stage_photo_director": {
            "final_complete": "Bright casing, sharp arrises, companion pyramids readable; plateau pristine.",
            "weathered_damage": "Wind-scoured faces, minor chip fields, first missing casing patches; geometry still elegant.",
            "major_partial_loss": "Large casing bands gone; stepped core reads as staggered mastaba-like tiers.",
            "core_structure_exposed": "Rough limestone and granite core visible; voids and snap-off blocks along edges.",
            "fragmented_ruins": "Truncated masses and isolated stacks; sand drifts in quarry-scar hollows.",
            "near_disappearance": "Low rubble windrows; faint base line where pyramid sat.",
            "fully_removed": "Only desert leveling and subtle footings; Cairo haze on horizon unchanged.",
        },
    },
    "great_wall": {
        "narrative_en": (
            "Ridge-line epic: unbroken crenellations and towers along a mountain spine weather into breaks, slips, and finally "
            "a bare ridgeline. Mist bands and vertical green valleys stay locked behind the wall silhouette."
        ),
        "narrative_ru": (
            "Хребет и стена: сплошной бой и башни, затем проломы и осипание кладки, в конце — голый склон без кладки. "
            "Туман и зелень долин только фон, не меняйте долготу пути стены."
        ),
        "photo_plan_en": [
            "Image 1: continuous curtain wall + beacon tower rhythm climbing the ridge; readable merlons.",
            "Degrade from parapets inward: chips, gaps, then half-collapsed towers—never add new masonry.",
            "Expose rammed-earth ochre between brick wythes as skins peel; keep mountain backdrop identical.",
            "Rubble should follow gravity down-slope; not scattered randomly in the sky.",
            "Maintain a leading line that matches the camera’s oblique ridge follow.",
            "Final: natural ridge only; trail of foundation scratches optional.",
        ],
        "video_plan_en": [
            "Rebuild: foundation trenches → stub segments → continuous run → parapets and beacon roofs.",
            "Use historical mortar spreading, brick chains, and rammed lifts visible in timelapse.",
            "Scaffolding hugs towers; no modern safety-orange plastics as hero elements.",
            "Keep wall width believable relative to towers; don’t balloon thickness between clips.",
            "Each clip ends closer to the iconic continuous battlements read.",
        ],
        "profile_5_en": (
            "Five scenes: linear steps of how much wall+tower mass remains (~25 points per frame); "
            "breach geometry must scale evenly so timelapse build rate stays steady."
        ),
        "profile_7_en": "Seven scenes: smaller equal steps; parapet chips and footing traces fill gaps without hoarding change in one clip.",
        "stage_photo_director": {
            "final_complete": "Long serpentine wall + towers; mist in valleys; crisp brick rhythm.",
            "weathered_damage": "Chipped merlons, surface spalls; wall still continuous.",
            "major_partial_loss": "Collapsed bay windows along ridge; silhouette broken but path obvious.",
            "core_structure_exposed": "Earth core and inner wythes visible in wide gaps.",
            "fragmented_ruins": "Isolated tower stumps and wall islands along the spine.",
            "near_disappearance": "Scattered low footings; grass reclaiming rampart line.",
            "fully_removed": "Mountain ridgeline alone; faint terrace scars only.",
        },
    },
    "colosseum": {
        "narrative_en": (
            "Rome’s ellipse loses its travertine skin: arches crack, vaults daylight, then only arena-ring ghosts remain. "
            "Keep hypogeum grid hints where the camera catches interior shadow."
        ),
        "narrative_ru": (
            "Овал Колизея: целый фасад из травертина, затем провалы арок и нервюр, обнажение кирпича и бетона, "
            "в конце — лишь отметка арены. Римский свет тёплый, пыльная атмосфера лета."
        ),
        "photo_plan_en": [
            "Frame 1: stacked arcades intact; partial hypogeum readable as in reference tourism shots.",
            "Fail modes: ring tension loss → voussoir drops → radial wall exposure → isolated islands.",
            "Never circular fisheye; keep verticals of exterior rings plausible.",
            "Arena sand and shadow pockets consistent; don’t teleport sun azimuth.",
            "Debris piles hug footprint; Roman ground plane visible in final empties.",
            "Preserve iconic ellipse proportion in every stage (width vs height).",
        ],
        "video_plan_en": [
            "Assembly clips echo historical sequence: foundation ring → lower arcade rings → vaults → bowl seating → facade dressing.",
            "Centering wood and treadwheel cranes at arches; keystones seated with taps.",
            "Crowd-absent monumental read; small scale figures optional and distant.",
            "Radial walls close before outer ring reads finished; hypogeum grid reappears logically.",
            "Dust from stone cutting; travertine color warms as new faces appear.",
        ],
        "profile_5_en": (
            "Five scenes: distribute ellipse mass loss in ~equal steps (~25 points); avoid looking almost-finished early "
            "then barely changing — each keyframe moves the ruin state by a full step."
        ),
        "profile_7_en": "Seven scenes: ~16–17 point steps; weathering and near-vanish are separate equal slices, not extra delay at the end.",
        "stage_photo_director": {
            "final_complete": "Full ellipse, three-tier arches; warm travertine; hypogeum hints consistent.",
            "weathered_damage": "Missing arch stones; façade cracks; bowl still mostly enclosed.",
            "major_partial_loss": "Collapsed sections; silhouette still elliptical but gapped.",
            "core_structure_exposed": "Brick-and-concrete radial ribs dominate; outer ring partial.",
            "fragmented_ruins": "Broken ring arcs; separated voussoir piles on sand.",
            "near_disappearance": "Low island chunks at arena level; footprints in dust.",
            "fully_removed": "Flat Roman ground; no standing amphitheater mass.",
        },
    },
    "eiffel_tower": {
        "narrative_en": (
            "Paris lattice story: lace iron rust-patches then member removals from the crown down until Champ de Mars regains sky. "
            "Keep four-leg symmetry and rivet rhythm legible until very late stages."
        ),
        "narrative_ru": (
            "Эйфелева башня: цельная решётка и шпиль, затем потеря верхних поясов и прогулов, обнажение узлов, "
            "в конце — пустой парк. Сохраняйте центрирование по оси Марсового поля."
        ),
        "photo_plan_en": [
            "First frame: full tower with platforms and needle; axial symmetry perfect.",
            "Strip top-down: losing lattices before primary legs fail; believable cantilever snap backs.",
            "Hot-riveted joints and puddle-iron color language consistent.",
            "Park tree canopy and paths frozen; only tower iron changes.",
            "No melting metal blobs; breaks are snapped/buckled members with sparks optional in motion blur only for video.",
            "Final wide: horizon shows no tower silhouette—only people-scale park features.",
        ],
        "video_plan_en": [
            "Rebuild: anchor bolts → stub legs → cross-braced mid → platforms → upper lattice → spire.",
            "Rivet gangs and period derricks; traveling climbers that hug existing iron.",
            "Each clip increases readable height toward the familiar Paris profile.",
            "Wind guy wires vibrate; no anachronistic LED floodlight rigs as hero props.",
            "Within the same locked frame as stage_000, keep tower-vs-park scale believable until the mass is gone.",
        ],
        "profile_5_en": (
            "Five scenes: each frame sheds ~equal share of lattice height/readable iron (~25 points); "
            "top-down logic still applies, but the *amount* gone per stage stays even."
        ),
        "profile_7_en": "Seven scenes: rust and anchor dust split the journey into ~16–17 point steps for smoother but still even pacing.",
        "stage_photo_director": {
            "final_complete": "Four legs, two decks, needle; symmetric lattice shadows on lawns.",
            "weathered_damage": "Localized lattice holes; patina variation; spire intact.",
            "major_partial_loss": "Upper lattice removed; shortened silhouette; mid platforms damaged.",
            "core_structure_exposed": "Sparse diagonals; legs partly disconnected at crown zones.",
            "fragmented_ruins": "Broken leg stubs; scattered truss on grass.",
            "near_disappearance": "Anchor pits and small iron scraps; vast sky.",
            "fully_removed": "Unobstructed Champ de Mars sightline; no tower.",
        },
    },
    "taj_mahal": {
        "narrative_en": (
            "Marble mausoleum poetry: mirror symmetry over the pool axis; inlay sparkle, then dome skin loss, minaret reduction, "
            "until the plinth reads alone. Yamuna moisture haze stays soft on the horizon."
        ),
        "narrative_ru": (
            "Тадж-Махал: белый мрамор и четыре минарета по оси бассейна, затем утрата инкрустации и массы купола, "
            "в конце — симметричная площадка без объёма мавзолея. Сохраняйте отражение в воде, пока рамка позволяет."
        ),
        "photo_plan_en": [
            "Frame 1: onion dome crisp; minarets plumb; reflecting pool geometry perfect.",
            "Degrade with radial symmetry—both wings fail evenly; no accidental twin composition shift.",
            "Pietra dura loss reads as gouges and missing semi-precious chips before marble sheets fall.",
            "Red sandstone subsidiary structures (if visible) degrade slower than white marble skin.",
            "Humid north Indian light; soft contrast; no neon color grade jumps.",
            "Final: empty plinth and stairs; pool edge geometry unchanged.",
        ],
        "video_plan_en": [
            "Rebuild: plinth grid → drum and arches → dome ribs → marble skin → minaret finials → inlay bands polished last.",
            "Scaffolding bamboo aesthetic; ox-lift lines for slabs; artisans with small chisels at inlay benches.",
            "Reflection reappears in lockstep with façade completion.",
            "Calligraphy bands masked then revealed in believable craft order.",
            "Crowds absent; birds over water allowed for scale-free life.",
        ],
        "profile_5_en": (
            "Five scenes: symmetric mass loss in ~25-point steps (dome, minarets, drum degrade together per quota); "
            "no ‘almost done’ look halfway through the run."
        ),
        "profile_7_en": "Seven scenes: weathering and near-vanish as extra equal slices; transitions stay perceptible every clip.",
        "stage_photo_director": {
            "final_complete": "White marble gleam; four minarets; central dome; pool symmetry.",
            "weathered_damage": "Surface wear; minor inlay loss; cracks localized.",
            "major_partial_loss": "Dome cladding gaps; minaret tops damaged; mass reduced but symmetry held.",
            "core_structure_exposed": "Inner masonry and ribs under stripped marble; iwans raw.",
            "fragmented_ruins": "Broken drum; minaret stumps; marble debris on plinth.",
            "near_disappearance": "Low plinth fragments; sparse debris at stairs.",
            "fully_removed": "Symmetrical terrace without mausoleum mass; pool frame persists.",
        },
    },
    "christ_redeemer": {
        "narrative_en": (
            "Corcovado statue: soapstone tiles and art-deco silhouette against Guanabara Bay; fractures open concrete core, arms fail first, "
            "then only pedestal mass whispers the old pose."
        ),
        "narrative_ru": (
            "Статуя на Корковаду: мыльный камень и жест с распростёртыми руками; трещины открывают бетон, "
            "плечи и голова уходят первыми, остаётся постамент и горизонт залива."
        ),
        "photo_plan_en": [
            "First frame: full cross-shaped silhouette; pedestal and mountain skyline locked.",
            "Damage progression: tile pops → limb loss → core exposure on torso/head.",
            "Keep bay atmospheric perspective; never swap to ocean-front beach palette.",
            "Soapstone matte vs concrete rough contrast must read in closeups if any.",
            "No heroic re-lighting; maintain midday Brazilian haze logic.",
            "Final: pedestal crown without statue body; skyline untouched.",
        ],
        "video_plan_en": [
            "Rebuild: pedestal pour → core column → armature stubs → soapstone cladding up the robe → head and hands carved last.",
            "Spider scaffolds; small mixers at pedestal; repoussé-style tile setting on curves.",
            "Arms widen in correct sequence before fingers detail returns.",
            "Safety nets billow; distant cargo ships static in bay.",
            "Finish with symbolic open-arm pose matching world-icon profile.",
        ],
        "profile_5_en": (
            "Five scenes: ~25-point steps along statue+pedestal read; limbs/torso loss paced evenly, not all motion in the first clip."
        ),
        "profile_7_en": "Seven scenes: weathering and rubble beats subdivide the same total into even steps.",
        "stage_photo_director": {
            "final_complete": "Full figure; arms wide; pedestal; bay and peaks behind.",
            "weathered_damage": "Tile chips at hands and robe edges; figure intact.",
            "major_partial_loss": "Arms reduced; head loss begins; cross-like read weakening.",
            "core_structure_exposed": "Concrete ribs and rebar hints in torso; partial soapstone islands.",
            "fragmented_ruins": "Torso chunks on pedestal; head gone.",
            "near_disappearance": "Concrete chips at shoulders; mostly pedestal.",
            "fully_removed": "Pedestal alone; mountain viewpoint unchanged.",
        },
    },
    "statue_of_liberty": {
        "narrative_en": (
            "Harbor copper drama: green patina and torch flare over New York Harbor; skin panels peel, inner Eiffel frame appears, "
            "crown spikes vanish until Liberty Island reads nearly empty except pedestal geology."
        ),
        "narrative_ru": (
            "Статуя Свободы: зелёная медь и факел над гаванью; листы оболочки уходят, виден каркас, "
            "корона и рука гаснут первыми; финал — остров и постамент без силуэта."
        ),
        "photo_plan_en": [
            "Frame 1: copper green uniform; torch above eye line; pedestal brow readable.",
            "Fail torch arm and crown early; robe folds survive mid-sequence.",
            "Harbor sparkle and ferry-scale distance locked; don’t jump to helicopter ultra-wide.",
            "Interior frame glimpses through tears should echo Eiffel lattice language subtly.",
            "Tablet outline degrades in sync with torso; no symmetrical ‘healing’ of fractures.",
            "Final: harbor backdrop with pedestal; no colossal statue mass.",
        ],
        "video_plan_en": [
            "Rebuild: pedestal granite courses → internal stair tower → copper foot → robe sheets sequenced → arm and torch → crown rays.",
            "Rivet lines march upward; forge heat at night optional as background bokeh only.",
            "Acid/patina wash teams even copper green tone near the end.",
            "Keep waterline and ferry wakes frozen except micro motion for timelapse life.",
            "End on classic three-quarter harbor read with torch high.",
        ],
        "profile_5_en": (
            "Five scenes: torch/crown/robe loss spread in ~25-point quota steps; copper and frame visibility advance evenly."
        ),
        "profile_7_en": "Seven scenes: patina and rubble as finer equal increments — steady perceived build rate.",
        "stage_photo_director": {
            "final_complete": "Torch high; crown spikes; robe drape; pedestal mass.",
            "weathered_damage": "Panel seams stressed; micro holes at folds; torch intact.",
            "major_partial_loss": "Torch arm compromised; upper torso thinned; crown damaged.",
            "core_structure_exposed": "Steel frame arcs inside torn copper; face partial.",
            "fragmented_ruins": "Shoulder islands; crown gone; scattered panels on deck.",
            "near_disappearance": "Shreds at pedestal cheeks; small copper scraps.",
            "fully_removed": "Pedestal and seawall; harbor open sky.",
        },
    },
    "hanging_gardens": {
        "narrative_en": (
            "Legendary Mesopotamian terraces: lush irrigation and trees on baked-brick tiers decay into cracked bitumen, "
            "channel drought, and collapsed gardens until only a stepped ghost remains in haze."
        ),
        "narrative_ru": (
            "Висячие сады: ярусы, вода и зелень; пересыхают желоба, крошится кладка и гидроизоляция, "
            "растительность гаснет, остаётся намётка террас в дымке Месопотамии."
        ),
        "photo_plan_en": [
            "Frame 1: dense terraces, water glints, trees overhanging channels in cross-section-friendly view.",
            "Hydraulic failure precedes total collapse: wilting → cracked channels → terrace slumps.",
            "Bitumen sheen and baked brick color stable; vegetation thins progressively.",
            "Avoid fantasy giant waterfalls; keep flows modest and engineered.",
            "Same locked cross-section camera as stage_000 must keep terrace stack readability each stage.",
            "Final: arid stepped mounds; no lush canopy.",
        ],
        "video_plan_en": [
            "Rebuild: survey lines → mud-brick lifts → bitumenbrush waterproofing → lead layers optional generic → replant canopies → restart channels → full green cascade.",
            "Gardeners, pot haulers, and shaduf-style lifts; smoke from distant kilns.",
            "Water sheets reappear before treetops peak to sell gravity-fed irrigation logic.",
            "Leaf flutter in timelapse compressed; dust in sun shafts.",
            "Finish with legendary lush cross-section read consistent with camera brief.",
        ],
        "profile_5_en": (
            "Five scenes: greenery + masonry + water each lose ~25 points worth of ‘full gardens’ read per step; "
            "avoid collapsing almost everything in one frame."
        ),
        "profile_7_en": "Seven scenes: vegetation vs hydraulic vs terrace failure as three equal bands within the linear schedule.",
        "stage_photo_director": {
            "final_complete": "Terraced greenery; water sheets; baked brick faces; dense canopy.",
            "weathered_damage": "Thinning trees; cracked runnels; some terrace edge chips.",
            "major_partial_loss": "Upper terraces failed; big gaps in planting beds; water erratic.",
            "core_structure_exposed": "Bitumen layers and naked stepped cores; sparse shrubs.",
            "fragmented_ruins": "Broken retaining walls; isolated pillars; dry channels.",
            "near_disappearance": "Low mounds with reed shadows; faint steps.",
            "fully_removed": "Flat alluvial plain texture; legendary site quiet.",
        },
    },
}


def _default_blueprint(structure_key: str) -> dict[str, Any]:
    return {
        "narrative_en": f"Landmark {structure_key}: monotonic damage from iconic complete to cleared site; keep materials honest.",
        "narrative_ru": f"Объект {structure_key}: только нарастающее разрушение от целого вида к пустой площадке.",
        "photo_plan_en": [
            "Still frames move from intact monument toward ruins without repairs.",
            "Preserve camera lock, horizon, and background identity.",
            "Each stage increases visible damage or removal of mass.",
            "Final frame shows site context without main monument mass.",
        ],
        "video_plan_en": [
            "Clips rebuild from empty toward complete with period-appropriate labor.",
            "Fixed high-angle; full monument in frame at end states.",
            "No magical morph; staged assembly and materials handling.",
        ],
        "profile_5_en": "Five scenes: coarse milestones but ~equal remaining-mass steps between frames; physically plausible loss.",
        "profile_7_en": "Seven scenes: finer steps, still equal perceptual weight per stage — no front-loaded destruction.",
        "stage_photo_director": {k: f"Stage {k}: adjust mass loss consistent with global mechanics." for k in _FULL_STAGE_ORDER},
    }


def get_creative_blueprint(structure_key: str) -> dict[str, Any]:
    if structure_key in STRUCTURE_CREATIVE_BLUEPRINTS:
        bp = dict(STRUCTURE_CREATIVE_BLUEPRINTS[structure_key])
    else:
        bp = _default_blueprint(structure_key)
    bp["photo_plan_en"] = _photo_plan_with_linear_header(bp.get("photo_plan_en"))
    bp["video_plan_en"] = _video_plan_with_linear_header(bp.get("video_plan_en"))
    return bp
