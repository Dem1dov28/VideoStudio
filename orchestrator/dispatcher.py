"""
Pipeline Dispatcher — routes by mode to appropriate pipeline.

Mode 1: Top-5 facts (swarm or sequential)
Mode 2: Почему X?
Mode 3: Восстановление домов
Mode 4: Цитата + фото
Mode 5: Длинные видео (~1 час)
Mode 6: Viral Cartoon Drama
Mode 7: Animal Keyboard Videos
Mode 8: House Building Timelapse
Mode 9: Vehicle Assembly Timelapse
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from orchestrator.pipelines.mode1 import run_mode1_pipeline
from orchestrator.swarm_graph import _SWARM_AVAILABLE, run_swarm_pipeline


async def run_pipeline(
    topic: str | None = None,
    num_scenes: int = 5,
    use_swarm: bool = True,
    session_id: str | None = None,
    local_only: bool = False,
    auto_topic: bool = False,
    use_scenario: bool = True,
    show_subtitles: bool = True,
    use_fact_check: bool = True,
    fact_check_strict: bool = False,
    prebuilt_scenario: dict | None = None,
    mode: int = 1,
    language: str = "ru",
    custom_title_bg_path: str | None = None,
    custom_outro_bg_path: str | None = None,
    reference_image_path: str | None = None,
    mode3_start_image_path: str | None = None,
    mode3_end_image_path: str | None = None,
    mode3_topic: str | None = None,
    mode4_quote: str | None = None,
    mode4_person_name: str | None = None,
    mode4_photo_path: str | None = None,
    mode4_only_lang: str | None = None,
    mode6_num_characters: int = 3,
    mode7_keyboards: list[str] | None = None,
    mode7_animal_type: str | None = None,
    mode8_house_style: str | None = None,
    mode8_location: str | None = None,
    mode8_num_stages: int = 5,
    mode9_vehicle_type: str | None = None,
    mode9_location: str | None = None,
    mode9_num_stages: int = 5,
    control: dict | None = None,
) -> dict[str, Any]:
    """Route to the appropriate pipeline by mode."""
    from pipeline_control import checkpoint

    # Mode 9: Vehicle Assembly Timelapse
    if mode == 9:
        await checkpoint(control)
        from modes.mode9.pipeline import run_mode9_pipeline
        return await run_mode9_pipeline(
            session_id=session_id,
            local_only=local_only,
            vehicle_type=mode9_vehicle_type,
            location=mode9_location,
            num_stages=mode9_num_stages,
            language=language or "ru",
            control=control,
        )

    # Mode 8: House Building Timelapse
    if mode == 8:
        await checkpoint(control)
        from modes.mode8.pipeline import run_mode8_pipeline
        return await run_mode8_pipeline(
            session_id=session_id,
            local_only=local_only,
            house_style=mode8_house_style,
            location=mode8_location,
            num_stages=mode8_num_stages,
            language=language or "ru",
            control=control,
        )

    # Mode 7: Animal Keyboard Videos
    if mode == 7:
        await checkpoint(control)
        from modes.mode7.pipeline import run_mode7_pipeline
        return await run_mode7_pipeline(
            session_id=session_id,
            local_only=local_only,
            keyboards=mode7_keyboards,
            animal_type=mode7_animal_type,
            language=language or "ru",
            control=control,
        )

    # Mode 6: Viral Cartoon Drama
    if mode == 6:
        await checkpoint(control)
        from modes.mode6.pipeline import run_mode6_pipeline
        return await run_mode6_pipeline(
            session_id=session_id,
            local_only=local_only,
            num_scenes=num_scenes,
            num_characters=mode6_num_characters,
            language=language or "ru",
            control=control,
        )

    # Mode 5: Длинные видео
    if mode == 5 and topic and str(topic).strip():
        await checkpoint(control)
        from modes.mode5.pipeline import run_mode5_pipeline
        return await run_mode5_pipeline(
            topic=topic.strip(),
            session_id=session_id,
            local_only=local_only,
            language=language or "ru",
            control=control,
        )

    # Mode 4: Цитата + фото
    if mode == 4 and mode4_quote and mode4_person_name and mode4_photo_path:
        await checkpoint(control)
        from modes.mode4.pipeline import run_mode4_pipeline
        return await run_mode4_pipeline(
            quote=mode4_quote.strip(),
            person_name=mode4_person_name.strip(),
            photo_path=mode4_photo_path,
            session_id=session_id,
            language="both",
            show_subtitles=show_subtitles,
            control=control,
            only_lang=(
                (mode4_only_lang or "").strip().lower()
                if (mode4_only_lang or "").strip().lower() in ("ru", "en")
                else None
            ),
        )

    # Mode 3: Восстановление домов
    if mode == 3:
        has_images = bool(mode3_start_image_path and mode3_end_image_path)
        has_topic = bool(mode3_topic and str(mode3_topic).strip())
        if has_images:
            await checkpoint(control)
            from modes.mode3.pipeline import run_mode3_pipeline
            return await run_mode3_pipeline(
                start_image_path=mode3_start_image_path,
                end_image_path=mode3_end_image_path,
                session_id=session_id,
                local_only=local_only,
                control=control,
            )
        if has_topic:
            await checkpoint(control)
            from modes.mode3.pipeline import run_mode3_pipeline_from_topic
            return await run_mode3_pipeline_from_topic(
                topic=str(mode3_topic).strip(),
                session_id=session_id,
                local_only=local_only,
                control=control,
            )
        raise ValueError("Mode 3 requires (mode3_start_image_path + mode3_end_image_path) or mode3_topic")

    # Mode 2: Почему X?
    if mode == 2:
        await checkpoint(control)
        from modes.mode2.pipeline import run_mode2_pipeline
        topic = topic or ("interesting facts" if language == "en" else "интересные факты")
        if auto_topic:
            from agents.trends_analyzer.agent import run_trends_agent_mode2
            trends = await run_trends_agent_mode2(top_n=1)
            trend_context = trends[0]
            topic = trend_context.get("video_angle") or trend_context.get("topic") or topic
        return await run_mode2_pipeline(
            topic=topic,
            num_scenes=num_scenes,
            session_id=session_id,
            local_only=local_only,
            show_subtitles=show_subtitles,
            prebuilt_scenario=prebuilt_scenario,
            language=language,
            custom_title_bg_path=custom_title_bg_path,
            custom_outro_bg_path=custom_outro_bg_path,
            reference_image_path=reference_image_path,
            control=control,
        )

    # Mode 1: Top-5 — Swarm or Sequential
    if use_swarm and _SWARM_AVAILABLE and topic:
        logger.info("Using LangGraph Swarm orchestration")
        return await run_swarm_pipeline(
            topic=topic,
            num_scenes=num_scenes,
            session_id=session_id,
            local_only=local_only,
        )

    await checkpoint(control)
    return await run_mode1_pipeline(
        topic=topic,
        num_scenes=num_scenes,
        session_id=session_id,
        local_only=local_only,
        auto_topic=auto_topic,
        use_scenario=use_scenario,
        show_subtitles=show_subtitles,
        use_fact_check=use_fact_check,
        fact_check_strict=fact_check_strict,
        prebuilt_scenario=prebuilt_scenario,
        language=language,
        custom_title_bg_path=custom_title_bg_path,
        custom_outro_bg_path=custom_outro_bg_path,
        reference_image_path=reference_image_path,
        control=control,
    )
