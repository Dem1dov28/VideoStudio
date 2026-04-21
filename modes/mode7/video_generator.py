"""
Mode 7 Video Generator — ASMR Animal Keyboard Videos.

Two-stage parallel generation:
1. Generate ALL reference images (first frames) for ALL keyboards FIRST
2. Generate ALL videos using the saved reference images

FOCUS: ASMR sounds, NO VOICE! NO SUBTITLES!
Only high-quality press/release sounds.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_images_with_references_fastgen,
    generate_single_video_multi_ref,
)
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# REFERENCE IMAGE PATH (real keyboard base image)
# ═══════════════════════════════════════════════════════════════════════════

MODE7_DIR = Path(__file__).resolve().parent
KEYBOARD_BASE_IMAGE = MODE7_DIR / "image.png"


# ═══════════════════════════════════════════════════════════════════════════
# ANIMAL VISUAL DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════════

ANIMAL_VISUALS = {
    "cat": "реалистичный пушистый кот, мягкая шерсть, выразительные глаза, детализированные лапы с розовыми подушечками, естественные движения",
    "dog": "реалистичная собака, шерсть средней длины, детализированные лапы, дружелюбная морда",
    "kitten": "маленький пушистый котёнок, большие глаза, крошечные лапки с маленькими розовыми подушечками",
    "puppy": "маленький щенок, пушистая шерсть, большие неуклюжие лапы, милое лицо",
}


# ═══════════════════════════════════════════════════════════════════════════
# KEYBOARD VISUAL DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════════

KEYBOARD_VISUALS = {
    "honey": {
        "visual": "золотистая медовая поверхность с 8-12 выпуклыми клавишами-пузырями из густого мёда, тянется нитями, глянцевая, янтарный цвет",
        "keys": "круглые выпуклые клавиши-пузыри из густого мёда, блестят на свету",
        "texture": "густой липкий мёд, тягучий, глянцевый",
    },
    "caramel": {
        "visual": "янтарная карамельная поверхность с 9 квадратными клавишами (3x3 сетка), полупрозрачная, глянцевая",
        "keys": "квадратные упругие клавиши из карамели, полупрозрачные, янтарные",
        "texture": "упругая тягучая карамель, глянцевая, тёплая",
    },
    "jelly": {
        "visual": "разноцветное желе с 12 круглыми клавишами-пузырями, дрожит, колышется, полупрозрачное",
        "keys": "круглые дрожащие клавиши-пузыри из желе, яркие цвета",
        "texture": "мягкое упругое желе, колышется при нажатии",
    },
    "slime": {
        "visual": "неоновая слизь с 8 клавишами-вмятинами, тянется, блестит, кислотные цвета",
        "keys": "клавиши-вмятины в слизи, неоновые, глянцевые",
        "texture": "тягучая слизь, хлюпает при нажатии, неоновая",
    },
    "ice": {
        "visual": "прозрачный лёд с 9 клавишами-кристаллами (3x3), трещины, блестит, зеркальный",
        "keys": "кристаллические клавиши из льда, острые грани, прозрачные",
        "texture": "хрупкий лёд, трескается под давлением, зеркальный",
    },
    "chocolate": {
        "visual": "тёмный шоколад с 8 квадратными клавишами, глянцевый, тает, насыщенный коричневый",
        "keys": "квадратные клавиши из шоколада, мягкие, податливые",
        "texture": "мягкий тающий шоколад, оставляет следы, матовый",
    },
    "cheese": {
        "visual": "жёлтый сыр с 10 клавишами-кругами, пористый, с дырочками, матовый",
        "keys": "круглые клавиши из сыра, пористые, упругие",
        "texture": "мягкий упругий сыр, пористый, продавливается",
    },
    "marshmallow": {
        "visual": "белые маршмеллоу-клавиши 8 штук, пушистые, пружинят, воздушные",
        "keys": "пушистые клавиши-маршмеллоу, белые, пружинистые",
        "texture": "воздушный мягкий маршмеллоу, пружинит, белый",
    },
    "liquid_metal": {
        "visual": "серебристый жидкий металл с 9 клавишами-волнами, зеркальный, течёт, футуристичный",
        "keys": "клавиши-волны из жидкого металла, зеркальные, текущие",
        "texture": "текучий металл, зеркальный, пульсирует при касании",
    },
}

KEYBOARD_SOUNDS = {
    "honey": "тягучий липкий звук: глубокий густой 'чмммяууук' при нажатии, тягучее сладкое 'ппрууммм' при медленном отпускании, звук тянущихся нитей мёда",
    "caramel": "карамельный липкий звук: упругое 'клац-чмм' при нажатии, тягучее 'ппрууумм' при отпускании, сладкий густой отзвук",
    "jelly": "желейный хлюпающий звук: мягкое 'хлюп-хлюп' при нажатии, упругое 'прюмм' при отпускании, звук дрожащего желе",
    "slime": "слизистый хлюпающий звук: влажное 'хлюююк' при нажатии, тягучее 'мммяуу' при отпускании, звук тянущейся слизи",
    "ice": "ледяной хрустящий звук: звонкий 'кррряк' при нажатии, резкий 'тррресь' при отпускании, звук трескающегося льда",
    "chocolate": "шоколадный мягкий звук: приглушённое 'чмок' при нажатии, мягкое 'мммяу' при отпускании, звук тающего шоколада",
    "cheese": "сырный упругий звук: мягкое 'прууф' при нажатии, упругое 'бруумм' при отпускании, звук продавливающегося сыра",
    "marshmallow": "воздушный мягкий звук: пушистое 'пууф' при нажатии, пружинистое 'ууумм' при отпускании, звук сжимаемого маршмеллоу",
    "liquid_metal": "металлический текущий звук: звонкое 'зззинг' при нажатии, текущее 'вввууум' при отпускании, звук пульсирующего металла",
}


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_image_prompt(scene: dict[str, Any], animal_type: str, language: str = "ru") -> str:
    """
    Build a prompt for generating the reference image (first frame).
    Uses the base keyboard image as reference to preserve real keyboard structure.
    """
    keyboard = scene.get("keyboard", "honey")
    press_count = scene.get("press_count", 3)
    
    animal_visual = ANIMAL_VISUALS.get(animal_type, ANIMAL_VISUALS["cat"])
    kb_visual = KEYBOARD_VISUALS.get(keyboard, KEYBOARD_VISUALS["honey"])
    
    prompt = f"""Create a high-quality still image (first frame) for an ASMR animal keyboard video.

STYLE: Photorealistic, macro photography quality, shallow depth of field, professional product photography lighting.

━━━ REFERENCE IMAGE RULES (CRITICAL) ━━━
The uploaded reference image shows a REAL KEYBOARD with actual keys.
YOU MUST:
- Keep the EXACT keyboard layout and key structure from the reference
- Keep the REAL key shapes (square, rectangular, not just circles)
- Transform the keys to be made of {keyboard} material while keeping their SHAPE
- The keyboard should look like a real mechanical keyboard, just made of {keyboard}
- DO NOT replace keys with simple circles or blobs - use real keyboard key shapes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUBJECT: {animal_visual}

KEYBOARD MATERIAL: {kb_visual['visual']}

KEYS: Real keyboard keys made of {kb_visual['keys']}

TEXTURE: {kb_visual['texture']}

SCENE: Animal's paw is about to press down on one of the keyboard keys. The surface is ready to react.

COMPOSITION:
- Vertical 9:16 aspect ratio
- Close-up shot of the keyboard with animal paw
- Focus on the real keyboard keys with {keyboard} texture
- Soft natural lighting highlighting the texture
- Shallow depth of field (background softly blurred)
- Macro photography style — extreme detail on texture

This is the FIRST FRAME before the ASMR pressing action begins. Capture the anticipation moment."""

    return prompt


def _build_video_prompt(scene: dict[str, Any], animal_type: str, language: str = "ru") -> str:
    """
    Build a FastGen video prompt for ASMR keyboard video.
    
    FOCUS: ASMR sounds only! NO VOICE! NO SUBTITLES!
    Only high-quality press/release sounds.
    Preserves real keyboard key structure from reference.
    """
    keyboard = scene.get("keyboard", "honey")
    press_count = scene.get("press_count", 3)
    
    animal_visual = ANIMAL_VISUALS.get(animal_type, ANIMAL_VISUALS["cat"])
    kb_visual = KEYBOARD_VISUALS.get(keyboard, KEYBOARD_VISUALS["honey"])
    kb_sound = KEYBOARD_SOUNDS.get(keyboard, KEYBOARD_SOUNDS["honey"])
    
    prompt = f"""⚠️ THIS IS AN ASMR VIDEO — NO VOICE! NO DIALOGUE! NO SUBTITLES! ONLY TEXTURE SOUNDS! ⚠️

Create a single 8-second vertical ASMR video (9:16). Photorealistic style, macro photography quality.

SUBJECT: {animal_visual}

KEYBOARD MATERIAL: {kb_visual['visual']}

━━━ REFERENCE IMAGE RULES (CRITICAL) ━━━
The uploaded reference image shows a REAL KEYBOARD with actual keys.
YOU MUST preserve:
- EXACT keyboard layout and key structure from reference
- REAL key shapes (square, rectangular) — NOT circles or blobs
- The keys should be made of {keyboard} material but keep their REAL KEYBOARD SHAPE
- The keyboard looks like a real mechanical keyboard, just made of {keyboard}
- EXACT animal appearance from reference
- The vertical 9:16 composition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACTION:
The animal presses {press_count} different keys on the {keyboard} keyboard, one after another.
Each press shows:
1. Paw approaching the key
2. Pressing down on the real key (key deforms/reacts like {keyboard})
3. Lifting the paw (key slowly recovers or leaves trace)

KEY REACTION:
- Real keyboard keys visually deform when pressed
- Keys show the press marks
- Realistic physics for {keyboard} material
- Keys maintain their real keyboard shape throughout

━━━ CRITICAL: ASMR SOUND DESIGN ━━━
THIS IS AN ASMR VIDEO — SOUND IS EVERYTHING!

NO MUSIC! NO VOICE! NO DIALOGUE!

ONLY THESE SOUNDS:
{kb_sound}

The sounds should be:
- Highly detailed and textured
- Satisfying to listen to
- Clear press and release sounds
- No background noise
- ASMR-quality recording

Sound focus: Each key press should produce a distinct, satisfying ASMR sound that matches the {keyboard} material.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAMERA: Steady close-up shot. Smooth zoom-in during presses. No camera shake.
FRAMING: Vertical 9:16. Macro close-up of real keyboard keys and paw interaction.
LIGHTING: Soft professional lighting highlighting texture details.

IMPORTANT:
- Animal remains realistic — no cartoon transformation
- Keys maintain real keyboard shape — not circles
- Surface reacts physically correct
- Smooth natural movements
- Focus on satisfying visual AND AUDIO texture interaction
- 8 seconds exactly

━━━ CONTENT SAFETY ━━━
❌ NO violence or harm to animal
❌ NO dangerous situations
❌ NO disturbing content
✅ Safe, satisfying, relaxing ASMR content only
━━━━━━━━━━━━━━━━━━━━━━"""

    return prompt


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_animal_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Generate ASMR animal keyboard video clips via FastGen with parallel processing.
    
    Workflow:
    1. Generate ALL reference images for ALL keyboards FIRST (parallel)
    2. Generate ALL videos using the saved reference images (parallel)
    
    Returns:
        Tuple of (list of video paths, enriched scenario)
    """
    scenes = scenario.get("scenes", [])
    animal_type = scenario.get("animal", "cat")
    
    if not scenes:
        raise ValueError("[Mode7] No scenes to generate")
    
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 7")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: Generate ALL reference images FIRST (with keyboard base image)
    # ═══════════════════════════════════════════════════════════════════════
    logger.info(f"[Mode7] STEP 1: Generating {len(scenes)} reference images for ASMR video...")
    
    # Check if base keyboard image exists
    base_image = KEYBOARD_BASE_IMAGE if KEYBOARD_BASE_IMAGE.exists() else None
    if base_image:
        logger.info(f"[Mode7] Using keyboard base image: {base_image}")
    else:
        logger.warning(f"[Mode7] Keyboard base image not found at {KEYBOARD_BASE_IMAGE}")
    
    # Build prompts for all scenes with keyboard base image as reference
    prompts_with_refs: list[tuple[str, list[Path]]] = []
    scene_data = []
    
    for i, scene in enumerate(scenes):
        keyboard = scene.get("keyboard", "honey")
        
        # Build prompts
        image_prompt = _build_image_prompt(scene, animal_type, language)
        video_prompt = _build_video_prompt(scene, animal_type, language)
        
        # Use keyboard base image as reference for image generation
        # This ensures the keyboard structure (real keys) is preserved
        refs = [base_image] if base_image else []
        prompts_with_refs.append((image_prompt, refs))
        
        # Store data for video generation
        scene_data.append({
            "index": i,
            "video_prompt": video_prompt,
            "keyboard": keyboard,
        })
        
        logger.info(f"[Mode7] Scene {i+1}: {animal_type} + {keyboard} keyboard (with base ref)")
    
    # Generate ALL images in PARALLEL (same as mode6)
    logger.info(f"[Mode7] Generating {len(prompts_with_refs)} reference images in PARALLEL...")
    image_paths = await generate_images_with_references_fastgen(
        prompts_with_refs, 
        images_dir, 
        parallel=True,
    )
    
    if len(image_paths) < len(prompts_with_refs):
        logger.warning(f"[Mode7] Expected {len(prompts_with_refs)} images, got {len(image_paths)}")
    
    # Rename images to scene indices
    ref_image_paths: list[Path | None] = []
    for i, img_path in enumerate(image_paths):
        if img_path and Path(img_path).exists():
            new_path = images_dir / f"scene_{i:03d}_ref.png"
            Path(img_path).rename(new_path)
            ref_image_paths.append(new_path)
            logger.success(f"[Mode7] Scene {i+1} reference image: {new_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[Mode7] Scene {i+1}: Failed to generate reference image")
    
    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: Generate ALL videos using the reference images
    # ═══════════════════════════════════════════════════════════════════════
    logger.info(f"[Mode7] STEP 2: Generating {len(scenes)} ASMR videos in PARALLEL...")
    
    video_tasks = []
    for i, data in enumerate(scene_data):
        # Get reference image for this scene
        ref_image = ref_image_paths[i] if i < len(ref_image_paths) else None
        
        # Use generated reference image as reference for video
        all_references = []
        if ref_image and ref_image.exists():
            all_references.append(ref_image)
        
        task = _generate_single_scene_video(
            index=i,
            prompt=data["video_prompt"],
            reference_image_paths=all_references,
            output_dir=output_dir,
        )
        video_tasks.append(task)
    
    # Generate ALL videos in parallel
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)
    
    # Handle results
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[Mode7] Scene {i+1} video failed: {result}")
            valid_paths.append(None)
        else:
            valid_paths.append(result)
    
    # Enrich scenario with video paths and reference image paths
    enriched_scenes = []
    for i, scene in enumerate(scenes):
        enriched_scene = dict(scene)
        if i < len(valid_paths) and valid_paths[i]:
            enriched_scene["video_path"] = str(valid_paths[i])
        if i < len(ref_image_paths) and ref_image_paths[i]:
            enriched_scene["reference_image_path"] = str(ref_image_paths[i])
        enriched_scenes.append(enriched_scene)
    
    enriched_scenario = dict(scenario)
    enriched_scenario["scenes"] = enriched_scenes
    
    valid_count = sum(1 for p in valid_paths if p and Path(p).exists())
    ref_count = sum(1 for p in ref_image_paths if p and Path(p).exists())
    logger.success(f"[Mode7] Generated {ref_count}/{len(scenes)} reference images and {valid_count}/{len(scenes)} ASMR video clips")
    
    return valid_paths, enriched_scenario


async def _generate_single_scene_video(
    index: int,
    prompt: str,
    reference_image_paths: list[Path],
    output_dir: Path,
) -> Path | None:
    """Generate a single ASMR video with reference images."""
    
    try:
        result = await generate_single_video_multi_ref(
            index=index,
            prompt=prompt,
            output_dir=output_dir,
            reference_image_paths=reference_image_paths,
        )
        
        if result and Path(result).exists():
            logger.success(f"[Mode7] Scene {index+1} ASMR video saved: {result.name}")
            return result
        else:
            logger.error(f"[Mode7] Scene {index+1}: Video generation returned no result")
            return None
            
    except Exception as e:
        logger.error(f"[Mode7] Scene {index+1} generation failed: {e}")
        return None
