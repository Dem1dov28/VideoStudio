"""
Video Prompt Builder - Based on video skills (video-processing-editing, klingai-image-to-video, video-generation)

Creates optimized prompts for:
1. Image-to-Video (KlingAI-style)
2. Text-to-Video (Veo/Sora-style)
3. Video editing/transitions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class VideoPrompt:
    """Structured video generation prompt."""
    shot_type: str
    subject_action: str
    camera_motion: str
    environment: str
    temporal_elements: str
    technical_specs: str
    full_prompt: str


# ═══════════════════════════════════════════════════════════════════════════════
# SHOT TYPES - Cinematic vocabulary
# ═══════════════════════════════════════════════════════════════════════════════

SHOT_TYPES = {
    "extreme_close_up": "extreme close-up (ECU), intimate detail, shallow depth of field",
    "close_up": "close-up (CU), facial expression focus, emotional intensity",
    "medium_close_up": "medium close-up (MCU), head and shoulders, personal connection",
    "medium_shot": "medium shot (MS), waist up, conversational framing",
    "medium_wide": "medium wide shot (MWS), full body with environment",
    "wide_shot": "wide shot (WS), full environment, establishing context",
    "extreme_wide": "extreme wide shot (EWS), epic scale, landscape emphasis",
    "over_shoulder": "over-the-shoulder (OTS), dialogue framing, spatial relationship",
    "pov": "point-of-view (POV), subjective camera, immersive experience",
    "aerial": "aerial drone shot, bird's eye view, sweeping perspective",
    "tracking": "tracking shot, following movement, dynamic energy",
    "static": "static tripod shot, stable frame, contemplative mood",
}

# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA MOTIONS - From subtle to intense
# ═══════════════════════════════════════════════════════════════════════════════

CAMERA_MOTIONS = {
    "static": [
        "locked-off tripod, perfectly stable",
        "static frame, timeless composition",
        "fixed camera position, observational",
    ],
    "subtle": [
        "slow cinematic push in, intimate approach",
        "gentle pull back, revealing context",
        "subtle dolly movement, smooth tracking",
        "slow zoom, gradual emphasis",
    ],
    "dynamic": [
        "smooth tracking shot, following subject",
        "crane up, elevating perspective",
        "steadicam movement, fluid motion",
        "arc shot, circling subject",
    ],
    "intense": [
        "rapid handheld, documentary urgency",
        "whip pan, energetic transition",
        "aggressive zoom, dramatic emphasis",
        "shaky cam, visceral intensity",
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL ELEMENTS - Time and motion
# ═══════════════════════════════════════════════════════════════════════════════

TEMPORAL_EFFECTS = {
    "slow_motion": "slow motion 120fps, fluid graceful movement, time stretched",
    "real_time": "real-time 24fps cinematic, natural motion, film standard",
    "time_lapse": "time-lapse accelerated, compressed time, dynamic clouds/stars",
    "freeze_frame": "freeze frame dramatic moment, suspended in time",
    "motion_blur": "motion blur streaks, speed impression, dynamic energy",
    "staccato": "staccato rhythmic cuts, edited pace, energetic timing",
}

# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

ENVIRONMENTS = {
    "urban": "urban cityscape, architectural geometry, human presence",
    "nature": "natural landscape, organic forms, environmental beauty",
    "interior": "interior space, architectural details, intimate setting",
    "abstract": "abstract environment, conceptual space, artistic interpretation",
    "studio": "studio environment, controlled lighting, professional setup",
    "outdoor": "outdoor location, natural lighting, environmental context",
}

# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM-SPECIFIC VIDEO REQUIREMENTS
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORM_VIDEO_SPECS = {
    "youtube": {
        "aspect_ratio": "16:9",
        "resolution": "1920x1080",
        "fps": "30fps or 60fps",
        "duration_tip": "15-60 seconds optimal for Shorts",
        "style": "high production value, clear narrative",
    },
    "instagram_story": {
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "fps": "30fps",
        "duration_tip": "up to 15 seconds",
        "style": "vertical composition, immediate hook",
    },
    "instagram_reel": {
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "fps": "30fps",
        "duration_tip": "up to 90 seconds",
        "style": "trending audio sync, fast-paced",
    },
    "tiktok": {
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "fps": "30fps or 60fps",
        "duration_tip": "15-60 seconds optimal",
        "style": "hook in 1 second, trending effects",
    },
    "twitter": {
        "aspect_ratio": "16:9",
        "resolution": "1280x720",
        "fps": "30fps",
        "duration_tip": "up to 2:20",
        "style": "news-worthy, concise impact",
    },
}


class VideoPromptBuilder:
    """Build professional video generation prompts."""

    def __init__(self, platform: str = "youtube"):
        self.platform = platform
        self.specs = PLATFORM_VIDEO_SPECS.get(platform, PLATFORM_VIDEO_SPECS["youtube"])

    def build_image_to_video_prompt(
        self,
        base_image_description: str,
        motion_intensity: Literal["static", "subtle", "dynamic", "intense"] = "subtle",
        camera_motion: str | None = None,
        duration_seconds: int = 5,
    ) -> str:
        """
        Build prompt for image-to-video generation (KlingAI-style).
        
        Args:
            base_image_description: The static image prompt
            motion_intensity: Level of motion
            camera_motion: Specific camera movement
            duration_seconds: Video length
        """
        motions = CAMERA_MOTIONS.get(motion_intensity, CAMERA_MOTIONS["subtle"])
        selected_motion = camera_motion or motions[0]
        
        prompt_parts = [
            base_image_description,
            f"{selected_motion}, temporal coherence",
            f"smooth {duration_seconds}-second motion sequence",
            "maintain subject consistency throughout",
            "cinematic motion blur where appropriate",
        ]
        
        return ", ".join(prompt_parts)

    def build_text_to_video_prompt(
        self,
        subject: str,
        action: str,
        shot_type: str = "medium_shot",
        motion_style: Literal["static", "subtle", "dynamic", "intense"] = "subtle",
        environment: str = "natural",
        temporal_effect: str = "real_time",
    ) -> VideoPrompt:
        """
        Build complete text-to-video prompt (Veo/Sora-style).
        
        Args:
            subject: Main subject description
            action: What the subject is doing
            shot_type: Camera framing
            motion_style: Camera movement intensity
            environment: Setting/location
            temporal_effect: Time manipulation
        """
        shot = SHOT_TYPES.get(shot_type, SHOT_TYPES["medium_shot"])
        motions = CAMERA_MOTIONS.get(motion_style, CAMERA_MOTIONS["subtle"])
        motion = motions[0]
        env = ENVIRONMENTS.get(environment, ENVIRONMENTS["natural"])
        temporal = TEMPORAL_EFFECTS.get(temporal_effect, TEMPORAL_EFFECTS["real_time"])
        
        technical = (
            f"{self.specs['aspect_ratio']} aspect ratio, "
            f"{self.specs['resolution']}, "
            f"{self.specs['fps']}, "
            f"professional cinematography"
        )
        
        full_prompt = (
            f"{shot}, {subject} {action}, "
            f"{motion}, {env}, "
            f"{temporal}, {technical}"
        )
        
        return VideoPrompt(
            shot_type=shot,
            subject_action=f"{subject} {action}",
            camera_motion=motion,
            environment=env,
            temporal_elements=temporal,
            technical_specs=technical,
            full_prompt=full_prompt,
        )

    def build_transition_prompt(
        self,
        from_scene: str,
        to_scene: str,
        transition_type: Literal["fade", "dissolve", "wipe", "slide", "zoom"] = "fade",
        duration: float = 1.0,
    ) -> str:
        """
        Build prompt for AI-generated transition between scenes.
        
        Args:
            from_scene: Description of outgoing scene
            to_scene: Description of incoming scene
            transition_type: Style of transition
            duration: Transition length in seconds
        """
        transitions = {
            "fade": f"smooth crossfade transition, {duration}s dissolve",
            "dissolve": f"film dissolve, {duration}s gradual transition",
            "wipe": f"directional wipe transition, {duration}s clean edge",
            "slide": f"sliding transition, {duration}s lateral movement",
            "zoom": f"zoom transition, {duration}s scale change",
        }
        
        transition_desc = transitions.get(transition_type, transitions["fade"])
        
        return (
            f"Transition from '{from_scene}' to '{to_scene}'. "
            f"{transition_desc}. "
            f"Maintain visual continuity, smooth motion flow."
        )

    def enhance_for_platform(self, base_prompt: str) -> str:
        """
        Enhance prompt with platform-specific optimizations.
        
        Args:
            base_prompt: Original video prompt
        """
        platform_notes = {
            "youtube": "high production value, clear narrative arc, professional cinematography",
            "instagram_story": "vertical 9:16, immediate visual hook, mobile-optimized framing",
            "instagram_reel": "trending style, fast-paced cuts, audio-reactive potential",
            "tiktok": "viral potential, hook in first frame, trending visual effects",
            "twitter": "news-worthy, concise storytelling, immediate impact",
        }
        
        note = platform_notes.get(self.platform, platform_notes["youtube"])
        
        return f"{base_prompt}, {note}"


def create_video_from_image_prompt(
    image_prompt: str,
    motion_type: Literal["static", "subtle", "dynamic", "intense"] = "subtle",
    platform: str = "youtube",
) -> dict:
    """
    Create complete video generation package from image prompt.
    
    Returns dict with:
    - image_prompt: Original/enhanced
    - video_prompt: Motion description
    - technical_specs: Platform requirements
    """
    builder = VideoPromptBuilder(platform)
    
    video_prompt = builder.build_image_to_video_prompt(
        base_image_description=image_prompt,
        motion_intensity=motion_type,
    )
    
    return {
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
        "platform": platform,
        "technical_specs": builder.specs,
        "motion_type": motion_type,
    }


# Quick reference for common video styles
VIDEO_STYLE_PRESETS = {
    "cinematic_b_roll": {
        "shot_type": "wide_shot",
        "motion": "subtle",
        "temporal": "real_time",
        "description": "smooth cinematic B-roll, professional documentary style",
    },
    "product_showcase": {
        "shot_type": "medium_close_up",
        "motion": "subtle",
        "temporal": "slow_motion",
        "description": "elegant product reveal, premium quality showcase",
    },
    "action_sequence": {
        "shot_type": "medium_wide",
        "motion": "dynamic",
        "temporal": "real_time",
        "description": "dynamic action coverage, energetic movement",
    },
    "emotional_moment": {
        "shot_type": "close_up",
        "motion": "static",
        "temporal": "slow_motion",
        "description": "intimate emotional beat, time stands still",
    },
    "establishing_shot": {
        "shot_type": "extreme_wide",
        "motion": "subtle",
        "temporal": "time_lapse",
        "description": "epic establishing shot, compressed time",
    },
}
