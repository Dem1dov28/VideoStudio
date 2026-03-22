"""
Unified Prompt Builder v2 - Based on image-gen-expert and video skills.

Integrates:
- Image Generation Expert: Professional prompt engineering formula
- Video Processing: Platform-specific optimization
- KlingAI Image-to-Video: Motion-aware image prompts
- Video Generation: Cinematic shot composition
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm


class Scene(TypedDict):
    index: int
    image_prompt: str
    subtitle_text: str
    video_prompt: str | None  # For future image-to-video or text-to-video


@dataclass
class PromptConfig:
    """Configuration for prompt generation."""
    platform: Literal["youtube", "instagram", "tiktok", "twitter"] = "youtube"
    style_preset: Literal["cinematic", "photorealistic", "digital_art", "documentary"] = "cinematic"
    motion_intent: Literal["static", "subtle", "dynamic", "intense"] = "subtle"
    duration_seconds: int = 15


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE PROMPT SYSTEM - Based on image-gen-expert skill
# ═══════════════════════════════════════════════════════════════════════════════

IMAGE_PROMPT_FORMULA = """
[SUBJECT] + [STYLE] + [LIGHTING] + [COMPOSITION] + [MOOD/ATMOSPHERE] + [QUALITY] + [FORMAT]
"""

STYLE_PRESETS = {
    "cinematic": {
        "style": "cinematic film still, movie quality, anamorphic lens characteristics",
        "lighting": "cinematic lighting with dramatic shadows and highlights",
        "quality": "35mm film grain, cinematic color grading, shallow depth of field"
    },
    "photorealistic": {
        "style": "photorealistic, hyper-realistic, indistinguishable from photography",
        "lighting": "natural lighting, photorealistic shadows, accurate light physics",
        "quality": "8K UHD, DSLR quality, sharp focus, professional photography"
    },
    "digital_art": {
        "style": "digital art, concept art, highly detailed illustration",
        "lighting": "dramatic studio lighting, rim light, volumetric effects",
        "quality": "artstation trending, 8K resolution, hyper-detailed, masterpiece"
    },
    "documentary": {
        "style": "documentary photography, editorial style, National Geographic quality",
        "lighting": "natural documentary lighting, available light, authentic",
        "quality": "professional photojournalism, crisp detail, true-to-life colors"
    }
}

LIGHTING_TECHNIQUES = [
    "golden hour warm sunlight",
    "blue hour twilight",
    "dramatic chiaroscuro",
    "soft diffused overcast",
    "rim lighting silhouette",
    "volumetric god rays",
    "neon cyberpunk glow",
    "studio three-point lighting",
    "natural window light",
    "sunset backlight",
]

COMPOSITION_TECHNIQUES = [
    "rule of thirds",
    "centered symmetrical",
    "Dutch angle dynamic",
    "extreme close-up macro",
    "wide establishing shot",
    "low angle heroic",
    "high angle overview",
    "leading lines perspective",
    "frame within frame",
    "shallow depth of field bokeh",
]

# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO PROMPT SYSTEM - Based on video skills
# ═══════════════════════════════════════════════════════════════════════════════

VIDEO_PROMPT_FORMULA = """
[SHOT TYPE] + [SUBJECT ACTION] + [CAMERA MOTION] + [ENVIRONMENT] + [TEMPORAL ELEMENTS] + [TECHNICAL]
"""

SHOT_TYPES = [
    "extreme close-up (ECU)",
    "close-up (CU)",
    "medium close-up (MCU)",
    "medium shot (MS)",
    "medium wide shot (MWS)",
    "wide shot (WS)",
    "extreme wide shot (EWS)",
    "over-the-shoulder (OTS)",
    "point-of-view (POV)",
    "aerial drone shot",
    "tracking shot",
    "static tripod shot",
]

CAMERA_MOTIONS = {
    "static": ["locked-off tripod", "static frame", "fixed position"],
    "subtle": ["slow push in", "gentle pull back", "subtle dolly"],
    "dynamic": ["smooth tracking shot", "crane up", "steadicam movement"],
    "intense": ["rapid handheld", "whip pan", "aggressive zoom"]
}

TEMPORAL_ELEMENTS = [
    "slow motion 120fps",
    "real-time 24fps cinematic",
    "time-lapse accelerated",
    "freeze frame moment",
    "motion blur streaks",
    "staccato rhythmic cuts",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM-SPECIFIC PROMPT ADAPTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORM_ADAPTATIONS = {
    "youtube": {
        "aspect_ratio": "16:9",
        "resolution": "1920x1080",
        "style_note": "High production value, clear subject, professional framing",
        "duration_range": "15-60 seconds optimal",
    },
    "instagram": {
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "style_note": "Vertical composition, subject centered, mobile-optimized",
        "duration_range": "15-30 seconds for Stories, up to 90s for Reels",
    },
    "tiktok": {
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "style_note": "Hook in first 1 second, fast-paced, trending visual style",
        "duration_range": "15-60 seconds optimal",
    },
    "twitter": {
        "aspect_ratio": "16:9",
        "resolution": "1280x720",
        "style_note": "News-worthy, concise, immediate impact",
        "duration_range": "up to 2:20",
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT - Unified Image + Video
# ═══════════════════════════════════════════════════════════════════════════════

_UNIFIED_SYSTEM_PROMPT = """You are an expert creative director specializing in AI-generated visual content for social media.

═══ IMAGE PROMPT ENGINEERING (image-gen-expert) ═══

STRUCTURE: [Subject] + [Style] + [Lighting] + [Composition] + [Mood] + [Quality] + [Format]

**SUBJECT** - Be extremely specific:
- Instead of "a dog" → "a majestic Siberian husky with piercing blue eyes"
- Include: subject + action + environment details
- Add material/texture details: "weathered leather", "polished chrome", "lush velvet"

**STYLE** - Choose ONE per scene:
- cinematic: "cinematic film still, 35mm anamorphic, shallow depth of field"
- photorealistic: "photorealistic, 8K UHD, DSLR quality, sharp focus"
- digital_art: "digital art, concept art, artstation trending, masterpiece"
- documentary: "documentary photography, National Geographic, editorial"

**LIGHTING** - Specific techniques:
- golden hour: "warm golden hour sunlight, long shadows, rim lighting"
- dramatic: "dramatic chiaroscuro, strong contrast, cinematic shadows"
- studio: "professional three-point lighting, soft key light, fill light"
- natural: "soft diffused natural light, overcast sky, even illumination"
- atmospheric: "volumetric fog, god rays, atmospheric haze"

**COMPOSITION** - Camera framing:
- extreme_closeup: "extreme close-up macro, shallow depth of field"
- wide: "wide establishing shot, epic scale, environmental context"
- dutch: "Dutch angle, dynamic tilt, tension"
- centered: "centered symmetrical composition, formal balance"

**MOOD/ATMOSPHERE** - Emotional impact:
- "mysterious and intriguing"
- "energetic and vibrant"
- "serene and peaceful"
- "dramatic and intense"

**QUALITY MODIFIERS** - Always include:
"ultra detailed, 8K UHD, professional photography, award-winning, hyper-detailed textures, crisp focus"

**FORMAT** - REQUIRED ending:
"vertical 9:16 portrait format, subject centered, no text, no watermark, no UI elements"

═══ VIDEO PROMPT ENGINEERING (video skills) ═══

For each scene, also consider VIDEO MOTION:

**SHOT TYPE**: extreme close-up, close-up, medium, wide, establishing
**CAMERA MOTION**: 
- static: "locked-off tripod, stable frame"
- subtle: "slow cinematic push in, gentle dolly"
- dynamic: "smooth tracking shot, crane movement"
- intense: "handheld documentary style, energetic movement"

**TEMPORAL ELEMENTS**:
- "slow motion fluid movement"
- "real-time natural motion"
- "time-lapse accelerated"
- "freeze frame dramatic moment"

═══ SCROLL-STOPPING PRINCIPLES ═══

1. FIRST 1.3 SECONDS: Hook with unexpected visual
2. PATTERN INTERRUPT: Break visual expectations
3. EMOTIONAL TRIGGER: Color psychology (warm=excitement, cool=calm)
4. CURIOSITY GAP: Partial reveal, viewer must watch to understand
5. MOTION IMPLICATION: Even static images suggest movement

═══ NEGATIVE PROMPTS (Always Avoid) ═══
- No text, letters, words, watermarks, signatures
- No blurry, distorted, low quality, artifacts
- No cluttered, messy, chaotic compositions
- No duplicate elements, repetitive patterns
- No cropped faces, cut-off limbs
- No unnatural proportions, deformed features

═══ OUTPUT FORMAT ═══
Return JSON array with scenes:
[
  {
    "index": 1,
    "image_prompt": "Complete image generation prompt following formula",
    "video_prompt": "Video motion description (camera + temporal)",
    "subtitle_text": "Russian subtitle (max 10 words)"
  }
]

EXAMPLE:
{
  "index": 1,
  "image_prompt": "A weathered astronaut helmet reflecting vibrant purple nebula clouds, cinematic film still, 35mm anamorphic lens, dramatic rim lighting from distant stars, extreme close-up macro composition, mysterious and awe-inspiring mood, ultra detailed 8K UHD, professional photography, hyper-detailed metallic textures with scratches, vertical 9:16 portrait format, subject centered, no text, no watermark",
  "video_prompt": "Slow cinematic push in, subtle rotation around helmet, god rays intensifying, 24fps cinematic motion",
  "subtitle_text": "Космос полон тайн"
}
"""


def build_scenes_v2(
    topic: str,
    num_scenes: int = 5,
    config: PromptConfig | None = None
) -> list[Scene]:
    """
    Generate scenes using unified image + video prompt system.
    
    Args:
        topic: Video topic
        num_scenes: Number of scenes to generate
        config: Prompt configuration for platform/style
    
    Returns:
        List of scenes with image_prompt, video_prompt, and subtitle_text
    """
    config = config or PromptConfig()
    
    # Get platform-specific guidance
    platform_guide = PLATFORM_ADAPTATIONS.get(config.platform, PLATFORM_ADAPTATIONS["youtube"])
    style_guide = STYLE_PRESETS.get(config.style_preset, STYLE_PRESETS["cinematic"])
    motion_guide = CAMERA_MOTIONS.get(config.motion_intent, CAMERA_MOTIONS["subtle"])
    
    llm = make_llm(temperature=0.75)
    
    user_content = f"""Topic: {topic}
Number of scenes: {num_scenes}
Subtitle language: Russian

PLATFORM CONTEXT:
- Platform: {config.platform}
- Aspect Ratio: {platform_guide['aspect_ratio']}
- Resolution: {platform_guide['resolution']}
- Style Note: {platform_guide['style_note']}
- Duration: {config.duration_seconds}s ({platform_guide['duration_range']})

STYLE PRESET: {config.style_preset}
- Style: {style_guide['style']}
- Lighting: {style_guide['lighting']}
- Quality: {style_guide['quality']}

MOTION INTENT: {config.motion_intent}
- Camera motions to use: {', '.join(motion_guide)}

Create {num_scenes} visually stunning scenes that tell a compelling story about "{topic}".
Each scene should work both as a static image AND suggest motion for potential video generation.
"""

    messages = [
        SystemMessage(content=_UNIFIED_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    
    logger.info(f"[PromptBuilderV2] Generating {num_scenes} scenes for: {topic}")
    response = llm.invoke(messages)
    raw = response.content.strip()
    
    try:
        scenes: list[Scene] = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            scenes = json.loads(raw[start:end])
        else:
            raise ValueError(f"Could not parse scenes JSON: {raw[:200]}")
    
    logger.success(f"[PromptBuilderV2] Generated {len(scenes)} scenes")
    return scenes


def enhance_prompt_for_video(image_prompt: str, motion_type: str = "subtle") -> str:
    """
    Enhance an existing image prompt for video generation.
    Based on KlingAI image-to-video skill.
    """
    motion_keywords = {
        "static": "locked-off tripod, stable composition, timeless frozen moment",
        "subtle": "gentle ambient motion, subtle breathing, alive with soft movement",
        "dynamic": "fluid motion, energetic movement, cinematic action",
        "intense": "rapid intense motion, dramatic action, high energy"
    }
    
    motion = motion_keywords.get(motion_type, motion_keywords["subtle"])
    
    # Add motion implications to existing prompt
    video_prompt = f"{image_prompt}, {motion}, temporal coherence, smooth motion flow"
    
    return video_prompt


def validate_prompt_quality(prompt: str) -> dict:
    """
    Validate prompt quality based on image-gen-expert best practices.
    """
    checks = {
        "has_subject": any(word in prompt.lower() for word in ["a ", "an ", "the "]),
        "has_style": any(word in prompt.lower() for word in ["cinematic", "photorealistic", "digital art", "style of"]),
        "has_lighting": any(word in prompt.lower() for word in ["lighting", "light", "shadow", "glow", "sunlight"]),
        "has_quality": any(word in prompt.lower() for word in ["8k", "detailed", "professional", "high quality"]),
        "has_format": "vertical" in prompt.lower() and "9:16" in prompt,
        "no_text": "no text" in prompt.lower() or "no letters" in prompt.lower(),
        "length_ok": 100 < len(prompt) < 500,
    }
    
    score = sum(checks.values()) / len(checks)
    
    return {
        "valid": score >= 0.7,
        "score": round(score, 2),
        "checks": checks,
        "suggestions": _get_suggestions(checks)
    }


def _get_suggestions(checks: dict) -> list[str]:
    """Generate improvement suggestions based on failed checks."""
    suggestions = []
    
    if not checks["has_subject"]:
        suggestions.append("Add specific subject description (e.g., 'a majestic lion' not just 'lion')")
    if not checks["has_style"]:
        suggestions.append("Include style keywords (cinematic, photorealistic, digital art)")
    if not checks["has_lighting"]:
        suggestions.append("Add lighting description (golden hour, dramatic, studio)")
    if not checks["has_quality"]:
        suggestions.append("Include quality modifiers (8K, ultra detailed, professional)")
    if not checks["has_format"]:
        suggestions.append("Add format specification (vertical 9:16 portrait)")
    if not checks["no_text"]:
        suggestions.append("Add negative prompt for text (no text, no watermark)")
    if not checks["length_ok"]:
        suggestions.append("Prompt length should be 100-500 characters")
    
    return suggestions


# Backwards compatibility
build_scenes = build_scenes_v2
