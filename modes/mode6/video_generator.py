"""
Mode 6 Video Generator — Generate cartoon drama videos via FastGen in parallel.

Each scene is generated as a video clip using ONLY the characters that appear in that scene.
Videos are generated in parallel (multiple browser windows).
Videos include AI-generated audio/voiceover from FastGen.

Prompt format follows PEROSNS/Example_prompt.md structure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_single_video_multi_ref
from config import settings


# Path to character images
PERSONS_DIR = Path(__file__).resolve().parent.parent.parent / "PEROSNS"

# Character visual descriptions from SOUL.md
CHARACTER_VISUALS = {
    "Брокколи": "огромный мускулистый брокколи, гипертрофированное тело бодибилдера, вены, большой торс, шрам на груди, в обтягивающих шортах",
    "Баклажан": "высокий стройный баклажан, слегка атлетичный, уверенное лицо, полуулыбка, золотая цепь, открытая одежда",
    "Морковь": "худой морковь, очки, немного сутулый, держит книгу",
    "Картошка": "полный картофель, неаккуратный, уставшие глаза, помятая одежда",
    "Помидор": "привлекательная томат-девушка, стройная фигура, выраженные формы, большие глаза, уверенная поза",
    "Огурец": "высокий стройный огурец, спортивный, повязка на голове",
    "Кукуруза": "кукуруза в деловом костюме, строгий взгляд, портфель",
    "Чеснок": "маленький чеснок с безумными глазами, странная улыбка",
    "Лук": "лук с большими слезящимися глазами, выразительное лицо",
    "Авокадо": "привлекательный авокадо, стильная одежда, уверенная поза, инфлюенсер",
}


def get_character_image_path(character_name: str) -> Path | None:
    """Get the image file path for a character by name."""
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        path = PERSONS_DIR / f"{character_name}{ext}"
        if path.exists():
            return path
    logger.warning(f"[Mode6] No image found for character: {character_name}")
    return None


def get_character_image_paths(character_names: list[str]) -> list[Path]:
    """Get image paths for specific characters."""
    images = []
    for char_name in character_names:
        path = get_character_image_path(char_name)
        if path:
            images.append(path)
        else:
            logger.warning(f"[Mode6] No image found for character: {char_name}")
    return images


def _build_video_prompt(scene: dict[str, Any], index: int, total: int, language: str = "ru") -> str:
    """
    Build a FastGen video prompt following Example_prompt.md format.
    Characters speak their own dialogue. No narrator. Language at the top.
    """
    characters = scene.get("characters", [])
    action = scene.get("action", "")
    emotion = scene.get("emotion", "drama")
    twist_level = scene.get("twist_level", 0)
    location = scene.get("location", "").strip()
    dialogue: list[dict] = scene.get("dialogue", [])

    # Language name
    language_names = {
        "ru": "Russian", "en": "English", "de": "German",
        "fr": "French", "es": "Spanish", "it": "Italian",
        "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    }
    voiceover_language = language_names.get(language.lower(), "Russian")

    # Build character descriptions
    char_descriptions = []
    for char in characters:
        visual = CHARACTER_VISUALS.get(char, f"{char} vegetable character")
        char_descriptions.append(f"{char} ({visual})")
    characters_block = "\n".join(f"{i+1}. {desc}" for i, desc in enumerate(char_descriptions))

    # Intensity
    intensity_note = ""
    if twist_level >= 8:
        intensity_note = "EXTREME DRAMATIC CLIMAX. Maximum emotional intensity. Shocking twist moment. "
    elif twist_level >= 5:
        intensity_note = "Building dramatic tension. Emotional conflict escalating. "
    elif twist_level >= 3:
        intensity_note = "Rising tension. Characters emotionally engaged. "

    # Voice tone per emotion
    emotion_tones = {
        "drama": "dramatic, emotional",
        "shock": "shocked, surprised",
        "romance": "romantic, soft, intimate",
        "conflict": "tense, confrontational",
        "comedy": "comedic, expressive",
        "betrayal": "hurt, betrayed",
        "chaos": "chaotic, frantic",
    }
    voice_tone = emotion_tones.get(emotion, "dramatic, emotional")

    # Location background
    location_desc = location if location else "neutral indoor/outdoor setting appropriate for the scene"

    # Build dialogue block with clear character attribution
    if dialogue:
        dialogue_lines = []
        total_words = 0
        for entry in dialogue:
            char = entry.get("character", "")
            line = entry.get("line", "").strip()
            # Remove dashes (Veo 3.1 bug)
            line = line.replace("—", " ").replace("-", " ").replace("–", " ")
            # Keep it short (5-15 words total per scene)
            words = line.split()
            if len(words) > 5:
                words = words[:5]  # Max 5 words per line
            line = " ".join(words)
            if char and line:
                # Clear attribution: character name + their exact line
                dialogue_lines.append(f'[{char}]: "{line}"')
                total_words += len(words)
        dialogue_block = "\n".join(dialogue_lines)
        # If too many words, simplify
        if total_words > 15:
            dialogue_block = dialogue_block + "\n\n[NOTE: Keep dialogue SHORT — maximum 5-10 words per character for 8-second video]"
    else:
        # Silent scene — emotional reactions only
        dialogue_block = "[SILENT SCENE] Characters show strong emotions through expressions, gasps, exclamations — NO dialogue, only visual storytelling."

    prompt = f"""⚠️ ALL DIALOGUE AND SPEECH MUST BE IN {voiceover_language.upper()} ONLY. THIS IS MANDATORY.

Create a single 8-second vertical video scene (9:16). Stylized 3D cartoon, Pixar-quality rendering, vibrant colors, cinematic soft lighting, smooth animation.

{intensity_note}
CHARACTERS IN THIS SCENE:
{characters_block}

━━━ REFERENCE IMAGES — ABSOLUTE RULE ━━━
The uploaded reference images define EXACTLY how each character looks.
YOU MUST:
- Keep EXACT body shape — vegetable/cartoon body, NOT human body
- Keep EXACT colors — do not change any colors
- Keep EXACT proportions — same silhouette as in reference
- Characters are CARTOON VEGETABLES with expressive faces — NEVER transform into humans
- NO human hair, NO human hands, NO realistic human features
- If reference shows a broccoli body — it stays a broccoli body throughout

CHARACTER TRANSFORMATION IS STRICTLY FORBIDDEN.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRAMING:
Full body visible. Vertical 9:16. Centered composition. No cropping of characters.

CHARACTER POSITIONING (IMPORTANT):
- Position characters clearly in frame: left side, center, right side
- Do NOT place all characters in the same spot
- If 1 character: center OR slightly off-center for dynamic composition
- If 2 characters: facing each other OR side by side with clear separation
- If 3 characters: triangular arrangement OR foreground/background depth
- Characters should have spatial awareness of each other

BACKGROUND: {location_desc}

ACTION (visual only — what characters DO, their gestures and movements):
{action}

CHARACTER POSES (IMPORTANT — VARIETY REQUIRED):
- Each character must have a DISTINCT, UNIQUE pose matching their emotion
- DO NOT have all characters standing still in the same neutral pose
- Use varied poses: sitting, leaning, kneeling, stepping forward, arms crossed, pointing, gesturing, turning away
- Poses must reflect the emotional state and character personality
- Example dramatic poses: slumped shoulders (defeat), chest out (confidence), hand on hip (attitude), covering face (shame)
- Characters should MOVE during the scene — shift weight, gesture, turn heads

EMOTION: {emotion} — exaggerated facial expressions and body language.

CAMERA: Medium full-body shot. Single continuous shot. Subtle slow zoom or pan. No cuts.

━━━ CHARACTER DIALOGUE ({voiceover_language.upper()}) ━━━
There is NO narrator. NO voiceover describing the scene.

⚠️ DIALOGUE RULES (CRITICAL FOR VIDEO QUALITY):
1. SHORT TEXT: Maximum 5-15 words TOTAL per scene (8 seconds = very short)
2. NO DASHES: Never use "—" or "-" in dialogue (causes audio glitches in Veo 3.1)
3. CLEAR ATTRIBUTION: Each line [Character]: "text" — ONLY that character speaks it
4. DISTINCT VOICES: Each character has a UNIQUE voice matching their personality
5. EMOTIONAL: Speech is emotional, impactful, 1-2 short sentences max
6. SILENT SCENES OK: Some scenes can have NO dialogue — only visual storytelling (hugs, kisses, shocked expressions)

IMPORTANT: Each line is spoken ONLY by the character named in [brackets].
The voice MUST match the character — different characters have different voices.
DO NOT mix up dialogue between characters.

CHARACTERS SPEAK THEIR OWN LINES ALOUD in {voiceover_language}:

{dialogue_block}

Voice tone: {voice_tone}. Each character has a DISTINCT voice matching their personality.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT:
- Characters remain VEGETABLES — no human transformation ever
- Expressions must be exaggerated for viral impact
- Keep animation smooth and readable
- Focus on emotional contrast between characters

━━━ CONTENT SAFETY (MANDATORY) ━━━
This is a family-friendly cartoon. The following are STRICTLY FORBIDDEN:

❌ VIOLENCE: No weapons, no blood, no fighting with intent to harm, no physical abuse, no hitting, punching, kicking that causes injury
❌ INAPPROPRIATE CONTENT: No sexual content, no nudity, no explicit romantic physical contact beyond hugging/holding hands
❌ DANGEROUS ACTIONS: No characters in dangerous situations (falling from heights, near fire, in traffic), no self-harm, no dangerous stunts
❌ SUBSTANCE USE: No alcohol, drugs, smoking, or any substance abuse
❌ HATE SPEECH: No discriminatory language or actions based on race, gender, religion, etc.
❌ SCARY CONTENT: No horror elements, no disturbing imagery, no jump scares
❌ ILLEGAL ACTIVITIES: No crime, theft, vandalism, or illegal behavior

ALLOWED (cartoon-appropriate):
✅ Dramatic emotional confrontations (shouting, arguing)
✅ Cartoon slapstick comedy (silly falls, comedic mishaps without injury)
✅ Romantic drama (flirting, heartbreak, jealousy — but not explicit)
✅ Absurd transformations (vegetable to vegetable, funny mutations)
✅ Comedy pratfalls and cartoon logic

If a scene contains forbidden content, SIMPLIFY it to focus on emotions and dialogue instead.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    return prompt


async def generate_cartoon_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Generate cartoon drama video clips via FastGen in PARALLEL.
    
    For EACH scene, uploads ONLY the characters that appear in that specific scene.
    Maximum 3 reference images per video (FastGen limit).
    All videos are generated simultaneously in separate browser windows.
    
    Returns:
        Tuple of (list of video paths, enriched scenario with video paths)
    """
    scenes = scenario.get("scenes", [])
    
    if not scenes:
        raise ValueError("[Mode6] No scenes to generate")
    
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set — required for Mode 6")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare data for each scene: prompt + character images
    scene_data = []
    for i, scene in enumerate(scenes):
        # Get characters for THIS specific scene
        scene_characters = scene.get("characters", [])[:3]  # Max 3 for FastGen
        
        # Get image paths for these characters
        character_images = get_character_image_paths(scene_characters)
        
        if not character_images:
            logger.warning(f"[Mode6] Scene {i+1}: No character images found for {scene_characters}!")
            # Try to get any available character as fallback
            fallback_char = scenario.get("characters", [])
            if fallback_char:
                character_images = get_character_image_paths(fallback_char[:1])
        
        # Build prompt for this scene
        prompt = _build_video_prompt(scene, i, len(scenes), language)
        
        scene_data.append({
            "index": i,
            "prompt": prompt,
            "characters": scene_characters,
            "character_images": character_images,
        })
        
        logger.info(f"[Mode6] Scene {i+1}: characters={scene_characters}, images={[p.name for p in character_images]}")
    
    # Generate ALL videos in PARALLEL with their specific character references
    logger.info(f"[Mode6] Generating {len(scenes)} videos in PARALLEL with scene-specific references...")
    
    # Use asyncio.gather to run all generations in parallel
    tasks = []
    for data in scene_data:
        task = _generate_single_scene_video(
            data["index"],
            data["prompt"],
            data["character_images"],
            output_dir,
        )
        tasks.append(task)
    
    video_paths = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle results and exceptions
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[Mode6] Scene {i+1} failed: {result}")
            valid_paths.append(None)
        else:
            valid_paths.append(result)
    
    # Enrich scenario with video paths
    enriched_scenes = []
    for i, scene in enumerate(scenes):
        enriched_scene = dict(scene)
        if i < len(valid_paths) and valid_paths[i]:
            enriched_scene["video_path"] = str(valid_paths[i])
        enriched_scenes.append(enriched_scene)
    
    enriched_scenario = dict(scenario)
    enriched_scenario["scenes"] = enriched_scenes
    
    valid_count = sum(1 for p in valid_paths if p and Path(p).exists())
    logger.success(f"[Mode6] Generated {valid_count}/{len(scenes)} video clips in parallel")
    
    return valid_paths, enriched_scenario


async def _generate_single_scene_video(
    index: int,
    prompt: str,
    character_images: list[Path],
    output_dir: Path,
) -> Path | None:
    """Generate a single video with specific character references."""
    
    try:
        # Generate single video with its specific references
        result = await generate_single_video_multi_ref(
            index=index,
            prompt=prompt,
            output_dir=output_dir,
            reference_image_paths=character_images,
        )
        
        if result and Path(result).exists():
            logger.success(f"[Mode6] Scene {index+1} video saved: {result.name}")
            return result
        else:
            logger.error(f"[Mode6] Scene {index+1}: Video generation returned no result")
            return None
            
    except Exception as e:
        logger.error(f"[Mode6] Scene {index+1} generation failed: {e}")
        return None
