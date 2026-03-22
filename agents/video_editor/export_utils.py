"""
Platform-specific video export utilities.
Based on video-processing-editing skill best practices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PlatformExportSettings:
    """Export settings optimized for specific platforms."""
    name: str
    resolution: tuple[int, int]
    fps: int
    video_bitrate: str
    audio_bitrate: str
    max_duration: int | None
    crf: int
    preset: str
    profile: str | None
    level: str | None
    pix_fmt: str
    color_space: str
    faststart: bool
    maxrate: str | None
    bufsize: str | None


# Platform-optimized export presets from video-processing-editing skill
PLATFORM_PRESETS: dict[str, PlatformExportSettings] = {
    "youtube": PlatformExportSettings(
        name="YouTube (1080p)",
        resolution=(1920, 1080),
        fps=30,
        video_bitrate="8000k",
        audio_bitrate="192k",
        max_duration=None,
        crf=18,
        preset="slow",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "youtube_4k": PlatformExportSettings(
        name="YouTube (4K)",
        resolution=(3840, 2160),
        fps=60,
        video_bitrate="40000k",
        audio_bitrate="256k",
        max_duration=None,
        crf=18,
        preset="slow",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "instagram_story": PlatformExportSettings(
        name="Instagram Story (9:16)",
        resolution=(1080, 1920),
        fps=30,
        video_bitrate="5000k",
        audio_bitrate="128k",
        max_duration=15,
        crf=23,
        preset="medium",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "instagram_reel": PlatformExportSettings(
        name="Instagram Reel (9:16)",
        resolution=(1080, 1920),
        fps=30,
        video_bitrate="8000k",
        audio_bitrate="128k",
        max_duration=90,
        crf=23,
        preset="medium",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "instagram_feed": PlatformExportSettings(
        name="Instagram Feed (1:1)",
        resolution=(1080, 1080),
        fps=30,
        video_bitrate="5000k",
        audio_bitrate="128k",
        max_duration=60,
        crf=23,
        preset="medium",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "tiktok": PlatformExportSettings(
        name="TikTok (9:16)",
        resolution=(1080, 1920),
        fps=30,
        video_bitrate="4000k",
        audio_bitrate="128k",
        max_duration=600,
        crf=23,
        preset="medium",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
    "twitter": PlatformExportSettings(
        name="Twitter/X (16:9)",
        resolution=(1280, 720),
        fps=30,
        video_bitrate="5000k",
        audio_bitrate="128k",
        max_duration=140,
        crf=23,
        preset="medium",
        profile=None,
        level=None,
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate="5000k",
        bufsize="10000k",
    ),
    "web": PlatformExportSettings(
        name="Web Optimized",
        resolution=(1920, 1080),
        fps=30,
        video_bitrate="4000k",
        audio_bitrate="128k",
        max_duration=None,
        crf=23,
        preset="medium",
        profile="baseline",
        level="3.0",
        pix_fmt="yuv420p",
        color_space="bt709",
        faststart=True,
        maxrate=None,
        bufsize=None,
    ),
}


def get_platform_settings(
    platform: Literal["youtube", "youtube_4k", "instagram_story", "instagram_reel", 
                      "instagram_feed", "tiktok", "twitter", "web"]
) -> PlatformExportSettings:
    """Get export settings for a specific platform."""
    if platform not in PLATFORM_PRESETS:
        raise ValueError(f"Unknown platform: {platform}. Available: {list(PLATFORM_PRESETS.keys())}")
    return PLATFORM_PRESETS[platform]


def get_ffmpeg_params(settings: PlatformExportSettings) -> list[str]:
    """Generate FFmpeg command-line parameters from settings."""
    params = [
        "-c:v", "libx264",
        "-preset", settings.preset,
        "-crf", str(settings.crf),
        "-b:v", settings.video_bitrate,
        "-s", f"{settings.resolution[0]}x{settings.resolution[1]}",
        "-r", str(settings.fps),
        "-pix_fmt", settings.pix_fmt,
        "-color_primaries", settings.color_space,
        "-color_trc", settings.color_space,
        "-colorspace", settings.color_space,
        "-c:a", "aac",
        "-b:a", settings.audio_bitrate,
        "-ar", "48000",
    ]
    
    if settings.faststart:
        params.extend(["-movflags", "+faststart"])
    
    if settings.profile:
        params.extend(["-profile:v", settings.profile])
    
    if settings.level:
        params.extend(["-level", settings.level])
    
    if settings.maxrate:
        params.extend(["-maxrate", settings.maxrate])
    
    if settings.bufsize:
        params.extend(["-bufsize", settings.bufsize])
    
    if settings.max_duration:
        params.extend(["-t", str(settings.max_duration)])
    
    return params


def recommend_platform(width: int, height: int, duration: float) -> str:
    """Recommend best platform based on video characteristics."""
    aspect_ratio = width / height
    
    # Vertical video (9:16)
    if aspect_ratio < 0.6:
        if duration <= 15:
            return "instagram_story"
        elif duration <= 90:
            return "instagram_reel"
        else:
            return "tiktok"
    
    # Square video (1:1)
    elif 0.9 <= aspect_ratio <= 1.1:
        return "instagram_feed"
    
    # Horizontal video (16:9)
    else:
        if duration <= 140:
            return "twitter"
        else:
            return "youtube"


# Quality presets for different use cases
QUALITY_PRESETS = {
    "draft": {"crf": 28, "preset": "ultrafast"},      # Fast encoding, lower quality
    "medium": {"crf": 23, "preset": "medium"},        # Balanced
    "high": {"crf": 18, "preset": "slow"},            # Best quality, slower
    "archive": {"crf": 15, "preset": "veryslow"},     # Archival quality
}


def get_quality_settings(quality: Literal["draft", "medium", "high", "archive"]) -> dict:
    """Get quality-specific encoding settings."""
    return QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
