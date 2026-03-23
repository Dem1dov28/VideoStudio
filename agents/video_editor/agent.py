"""Video Editor Agent."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from loguru import logger

from agents.content_generator.agent import EnrichedScene
from agents.video_editor.moviepy_editor import SceneData, assemble_video
from agents.video_editor.tts import synthesize_all
from config import settings


async def run_video_editor_agent(
    scenes: list[EnrichedScene],
    session_id: str | None = None,
    title: str | None = None,
    hook: str | None = None,
    outro: str | None = None,
    topic: str | None = None,
    show_subtitles: bool = True,
) -> str:
    """
    Synthesize voiceovers, then assemble the final video.

    Args:
        scenes:     Enriched scene list from ImageGeneratorAgent.
        session_id: Unique run identifier (used for output paths).
        title:      Video title shown on the title card (from ScenarioWriter).
        hook:       Opening hook line shown on the title card + first-scene banner.
        outro:      Closing CTA shown on the outro card.
        topic:      Original topic string — passed to AI music generator.

    Returns:
        Absolute path to the rendered mp4 file.
    """
    session_id = session_id or str(int(time.time()))
    audio_dir = settings.audio_dir / session_id
    video_dir = settings.videos_dir / session_id
    video_dir.mkdir(parents=True, exist_ok=True)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)

    narration_texts = [
        s.get("narration_text") or s["subtitle_text"]
        for s in scenes
    ]

    outro_bg_image_path = None
    try:
        if scenes and isinstance(scenes[0], dict):
            outro_bg_image_path = scenes[0].get("outro_bg_image_path")
    except Exception:
        outro_bg_image_path = None

    import re

    def _hook_to_first_slide_text(h: str, fallback: str) -> str:
        h = (h or "").strip()
        # Typical hook: "Топ-5 фактов о <subject>"
        m = re.match(
            r"^\s*Топ[-\s]*5\s*фактов\s+(?:о|про)\s*(.+?)\s*[.:!?\-–—,;]*\s*$",
            h,
            flags=re.IGNORECASE,
        )
        if m:
            subj = m.group(1).strip()
            if subj:
                return f"5 интересных фактов о {subj}"
        return fallback or h

    title_narration = _hook_to_first_slide_text(hook or "", title or "")
    outro_narration = (outro or "").strip()

    tts_texts: list[str] = []
    title_audio_idx: int | None = None
    if title_narration:
        title_audio_idx = len(tts_texts)
        tts_texts.append(title_narration)

    scene_audio_start_idx = len(tts_texts)
    tts_texts.extend(narration_texts)

    outro_audio_idx: int | None = None
    if outro_narration:
        outro_audio_idx = len(tts_texts)
        tts_texts.append(outro_narration)

    logger.info(f"[VideoAgent] Synthesizing {len(tts_texts)} voiceover clips …")
    audio_paths, _, _ = await synthesize_all(tts_texts, audio_dir)

    title_audio_path = (
        str(audio_paths[title_audio_idx]) if title_audio_idx is not None and title_audio_idx < len(audio_paths) else None
    )
    outro_audio_path = (
        str(audio_paths[outro_audio_idx]) if outro_audio_idx is not None and outro_audio_idx < len(audio_paths) else None
    )

    scene_data = [
        SceneData(
            image_path=scene["image_path"],
            # Subtitles must match what we actually voiceover (fact-checker can
            # correct narration_text without changing subtitle_text).
            subtitle_text=narration_texts[i] if show_subtitles else "",
            audio_path=str(audio_paths[scene_audio_start_idx + i])
            if scene_audio_start_idx + i < len(audio_paths)
            else None,
        )
        for i, scene in enumerate(scenes)
    ]

    output_path = settings.videos_dir / f"video_{session_id}.mp4"
    loop = asyncio.get_event_loop()

    import functools
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_video,
            scene_data,
            output_path,
            title=title_narration,
            hook="",
            outro=outro,
            topic=topic or title,
            title_audio_path=title_audio_path,
            outro_audio_path=outro_audio_path,
            title_subtitle_text=title_narration if show_subtitles else None,
            outro_subtitle_text=outro if show_subtitles else None,
            outro_bg_image_path=outro_bg_image_path,
        ),
    )

    return str(output_path.resolve())
