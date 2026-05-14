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
Mode 10: Beach cleanup timelapse (логика как mode 8)
Mode 11: Monument deconstruction timelapse
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from orchestrator.pipelines.mode1 import run_mode1_pipeline
from orchestrator.swarm_graph import _SWARM_AVAILABLE, run_swarm_pipeline


async def _run_pipeline_wrapped(
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
    mode4_show_author_on_video: bool = True,
    mode4_video_header_title: str | None = None,
    mode4_subtitle_style: str = "karaoke",
    mode4_multiclip: bool = False,
    mode4_segments: list[str] | None = None,
    mode4_skip_final_assembly: bool = True,
    mode4_location_hint: str | None = None,
    mode5_script_text: str | None = None,
    mode5_language: str | None = None,
    mode5_chunk_seconds: int = 300,
    mode5_segment_seconds: int = 15,
    mode5_skip_final_assembly: bool = True,
    mode5_skip_chunk_previews: bool = False,
    mode5_max_parallel_images: int = 10,
    mode5_image_backend: str | None = None,
    mode5_video_header_title: str | None = None,
    mode5_bible_mode: bool = False,
    mode5_sub_mode: str = "manual",
    mode5_test_run: bool = False,
    mode5_test_duration_sec: int = 300,
    mode6_num_characters: int = 3,
    mode7_keyboards: list[str] | None = None,
    mode7_animal_type: str | None = None,
    mode8_house_style: str | None = None,
    mode8_location: str | None = None,
    mode8_num_stages: int = 5,
    mode8_num_floors: int = 2,
    mode9_vehicle_type: str | None = None,
    mode9_location: str | None = None,
    mode9_num_stages: int = 5,
    mode10_beach_type: str | None = None,
    mode10_coast_setting: str | None = None,
    mode10_num_stages: int = 5,
    mode11_structure_type: str | None = None,
    mode11_num_stages: int = 5,
    mode13_audio_path: str | None = None,
    mode13_voice_preset: str = "studio",
    mode13_language: str | None = None,
    mode13_show_subtitles: bool = True,
    mode13_skip_final_assembly: bool = True,
    mode13_chunk_seconds: int = 300,
    mode13_segment_seconds: int = 30,
    mode13_video_header_title: str | None = None,
    mode13_voice_gain_db: float = 0.0,
    mode13_voice_tempo_scale: float = 1.0,
    mode13_voice_pitch_semitones: float = 0.0,
    mode13_voice_ai_cleanup: float = 0.0,
    mode13_voice_noise_suppression: float = 50.0,
    mode13_voice_level_normalize: float = 50.0,
    mode13_voice_highpass_hz: int | None = None,
    mode13_voice_deesser: float = 0.0,
    mode13_voice_clarity: float = 0.0,
    mode13_voice_mud_cut: float = 0.0,
    mode13_voice_compression: float = 0.0,
    control: dict | None = None,
) -> dict[str, Any]:
    """Internal pipeline runner with session context."""
    from pipeline_control import checkpoint

    # Mode 13: аудио → смена тембра → слайды 30 с → превью по 5 мин
    if mode == 13:
        ap = (mode13_audio_path or "").strip()
        if not ap:
            raise ValueError("Mode 13: укажите путь к загруженному аудиофайлу")
        await checkpoint(control)
        from modes.mode13.pipeline import run_mode13_pipeline

        vp = (mode13_voice_preset or "studio").strip().lower()
        if vp not in ("original", "studio", "calm", "natural", "soft", "medium", "strong"):
            vp = "studio"
        lang = (mode13_language or "").strip() or None
        vht = (mode13_video_header_title or "").strip() or None
        return await run_mode13_pipeline(
            session_id=session_id,
            audio_path=ap,
            voice_preset=vp,
            voice_gain_db=float(mode13_voice_gain_db or 0.0),
            voice_tempo_scale=float(mode13_voice_tempo_scale or 1.0),
            voice_pitch_semitones=float(mode13_voice_pitch_semitones or 0.0),
            voice_ai_cleanup=float(mode13_voice_ai_cleanup or 0.0),
            voice_noise_suppression=float(mode13_voice_noise_suppression),
            voice_level_normalize=float(mode13_voice_level_normalize),
            voice_highpass_hz=(
                int(mode13_voice_highpass_hz)
                if mode13_voice_highpass_hz is not None
                and 40 <= int(mode13_voice_highpass_hz) <= 200
                else None
            ),
            voice_deesser=float(mode13_voice_deesser or 0.0),
            voice_clarity=float(mode13_voice_clarity or 0.0),
            voice_mud_cut=float(mode13_voice_mud_cut or 0.0),
            voice_compression=float(mode13_voice_compression or 0.0),
            language=lang,
            show_subtitles=bool(mode13_show_subtitles),
            skip_final_assembly=bool(mode13_skip_final_assembly),
            chunk_seconds=int(mode13_chunk_seconds or 300),
            segment_seconds=int(mode13_segment_seconds or 30),
            video_header_title=vht,
            control=control,
        )

    # Mode 10: Beach cleanup timelapse
    if mode == 10:
        await checkpoint(control)
        from modes.mode10.pipeline import run_mode10_pipeline
        return await run_mode10_pipeline(
            session_id=session_id,
            local_only=local_only,
            beach_type=mode10_beach_type,
            coast_setting=mode10_coast_setting,
            num_stages=mode10_num_stages,
            language=language or "ru",
            control=control,
        )

    # Mode 11: Monument Deconstruction Timelapse
    if mode == 11:
        await checkpoint(control)
        from modes.mode11.pipeline import run_mode11_pipeline
        return await run_mode11_pipeline(
            session_id=session_id,
            local_only=local_only,
            structure_type=mode11_structure_type,
            language=language or "ru",
            num_stages=mode11_num_stages,
            control=control,
        )

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
            num_floors=mode8_num_floors,
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

    # Mode 5: Manual long-form text -> ElevenLabs -> reviewable previews
    if mode == 5:
        txt = str(mode5_script_text or "").strip()
        if not txt:
            raise ValueError("Mode 5: укажите текст для озвучки")
        sub5 = (mode5_sub_mode or "manual").strip().lower()
        if sub5 not in ("manual", "bible", "facts50", "outline", "book_night", "unwritten_chapter"):
            sub5 = "manual"
        if sub5 == "manual" and mode5_bible_mode:
            sub5 = "bible"
        if sub5 not in ("facts50", "outline", "book_night", "unwritten_chapter") and len(txt) < 80:
            raise ValueError("Mode 5: вставьте полноценный текст для озвучки")
        if sub5 == "outline":
            from modes.mode5.outline_generator import MIN_OUTLINE_BRIEF_CHARS

            if len(txt) < MIN_OUTLINE_BRIEF_CHARS:
                raise ValueError(
                    f"Mode 5: для «плана из описания» введите краткое описание сюжета (от {MIN_OUTLINE_BRIEF_CHARS} символов), "
                    "не только название ролика."
                )
        elif sub5 in ("facts50", "book_night", "unwritten_chapter") and len(txt) < 8:
            raise ValueError(
                "Mode 5: для «77 фактов», «книга на ночь» или «The Unwritten Chapter» введите тему/название (от 8 символов)"
            )
        await checkpoint(control)
        from modes.mode5.pipeline import run_mode5_pipeline
        return await run_mode5_pipeline(
            script_text=txt,
            session_id=session_id,
            language=(mode5_language or language or "ru"),
            skip_final_assembly=bool(mode5_skip_final_assembly),
            skip_chunk_previews=bool(mode5_skip_chunk_previews),
            chunk_seconds=int(mode5_chunk_seconds or 300),
            segment_seconds=int(mode5_segment_seconds or 15),
            max_parallel_images=int(mode5_max_parallel_images or 10),
            image_backend=mode5_image_backend,
            video_header_title=(mode5_video_header_title or "").strip() or None,
            bible_mode=bool(mode5_bible_mode),
            sub_mode=sub5,
            test_run=bool(mode5_test_run),
            test_duration_sec=int(mode5_test_duration_sec or 300),
            control=control,
        )

    # Mode 4: Цитата + фото
    if mode == 4 and mode4_quote and mode4_photo_path:
        await checkpoint(control)
        from modes.mode4.pipeline import run_mode4_pipeline
        return await run_mode4_pipeline(
            quote=mode4_quote.strip(),
            person_name=(mode4_person_name or "").strip(),
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
            show_author_on_video=bool(mode4_show_author_on_video),
            video_header_title=(mode4_video_header_title or "").strip() or None,
            subtitle_style=mode4_subtitle_style or "karaoke",
            multiclip=bool(mode4_multiclip),
            multiclip_segments=(
                [str(s).strip() for s in (mode4_segments or []) if str(s).strip()]
                if mode4_segments
                else None
            ),
            skip_final_assembly_multiclip=bool(mode4_skip_final_assembly),
            location_steering_hint=(mode4_location_hint or "").strip() or None,
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
    mode4_show_author_on_video: bool = True,
    mode4_video_header_title: str | None = None,
    mode4_subtitle_style: str = "karaoke",
    mode4_multiclip: bool = False,
    mode4_segments: list[str] | None = None,
    mode4_skip_final_assembly: bool = True,
    mode4_location_hint: str | None = None,
    mode5_script_text: str | None = None,
    mode5_language: str | None = None,
    mode5_chunk_seconds: int = 300,
    mode5_segment_seconds: int = 15,
    mode5_skip_final_assembly: bool = True,
    mode5_skip_chunk_previews: bool = False,
    mode5_max_parallel_images: int = 10,
    mode5_image_backend: str | None = None,
    mode5_video_header_title: str | None = None,
    mode5_bible_mode: bool = False,
    mode5_sub_mode: str = "manual",
    mode5_test_run: bool = False,
    mode5_test_duration_sec: int = 300,
    mode6_num_characters: int = 3,
    mode7_keyboards: list[str] | None = None,
    mode7_animal_type: str | None = None,
    mode8_house_style: str | None = None,
    mode8_location: str | None = None,
    mode8_num_stages: int = 5,
    mode8_num_floors: int = 2,
    mode9_vehicle_type: str | None = None,
    mode9_location: str | None = None,
    mode9_num_stages: int = 5,
    mode10_beach_type: str | None = None,
    mode10_coast_setting: str | None = None,
    mode10_num_stages: int = 5,
    mode11_structure_type: str | None = None,
    mode11_num_stages: int = 5,
    mode13_audio_path: str | None = None,
    mode13_voice_preset: str = "studio",
    mode13_language: str | None = None,
    mode13_show_subtitles: bool = True,
    mode13_skip_final_assembly: bool = True,
    mode13_chunk_seconds: int = 300,
    mode13_segment_seconds: int = 30,
    mode13_video_header_title: str | None = None,
    mode13_voice_gain_db: float = 0.0,
    mode13_voice_tempo_scale: float = 1.0,
    mode13_voice_pitch_semitones: float = 0.0,
    mode13_voice_ai_cleanup: float = 0.0,
    mode13_voice_noise_suppression: float = 50.0,
    mode13_voice_level_normalize: float = 50.0,
    mode13_voice_highpass_hz: int | None = None,
    mode13_voice_deesser: float = 0.0,
    mode13_voice_clarity: float = 0.0,
    mode13_voice_mud_cut: float = 0.0,
    mode13_voice_compression: float = 0.0,
    control: dict | None = None,
) -> dict[str, Any]:
    """Route to the appropriate pipeline by mode with session context."""
    # Use contextual logger binding per request to avoid global logger races.
    session_id = session_id or str(int(time.time() * 1000))
    with logger.contextualize(session_id=session_id):
        return await _run_pipeline_wrapped(
            topic=topic,
            num_scenes=num_scenes,
            use_swarm=use_swarm,
            session_id=session_id,
            local_only=local_only,
            auto_topic=auto_topic,
            use_scenario=use_scenario,
            show_subtitles=show_subtitles,
            use_fact_check=use_fact_check,
            fact_check_strict=fact_check_strict,
            prebuilt_scenario=prebuilt_scenario,
            mode=mode,
            language=language,
            custom_title_bg_path=custom_title_bg_path,
            custom_outro_bg_path=custom_outro_bg_path,
            reference_image_path=reference_image_path,
            mode3_start_image_path=mode3_start_image_path,
            mode3_end_image_path=mode3_end_image_path,
            mode3_topic=mode3_topic,
            mode4_quote=mode4_quote,
            mode4_person_name=mode4_person_name,
            mode4_photo_path=mode4_photo_path,
            mode4_only_lang=mode4_only_lang,
            mode4_show_author_on_video=mode4_show_author_on_video,
            mode4_video_header_title=mode4_video_header_title,
            mode4_subtitle_style=mode4_subtitle_style,
            mode4_multiclip=mode4_multiclip,
            mode4_segments=mode4_segments,
            mode4_skip_final_assembly=mode4_skip_final_assembly,
            mode4_location_hint=mode4_location_hint,
            mode5_script_text=mode5_script_text,
            mode5_language=mode5_language,
            mode5_chunk_seconds=mode5_chunk_seconds,
            mode5_segment_seconds=mode5_segment_seconds,
            mode5_skip_final_assembly=mode5_skip_final_assembly,
            mode5_skip_chunk_previews=mode5_skip_chunk_previews,
            mode5_max_parallel_images=mode5_max_parallel_images,
            mode5_image_backend=mode5_image_backend,
            mode5_video_header_title=mode5_video_header_title,
            mode5_bible_mode=mode5_bible_mode,
            mode5_sub_mode=mode5_sub_mode,
            mode5_test_run=mode5_test_run,
            mode5_test_duration_sec=mode5_test_duration_sec,
            mode6_num_characters=mode6_num_characters,
            mode7_keyboards=mode7_keyboards,
            mode7_animal_type=mode7_animal_type,
            mode8_house_style=mode8_house_style,
            mode8_location=mode8_location,
            mode8_num_stages=mode8_num_stages,
            mode8_num_floors=mode8_num_floors,
            mode9_vehicle_type=mode9_vehicle_type,
            mode9_location=mode9_location,
            mode9_num_stages=mode9_num_stages,
            mode10_beach_type=mode10_beach_type,
            mode10_coast_setting=mode10_coast_setting,
            mode10_num_stages=mode10_num_stages,
            mode11_structure_type=mode11_structure_type,
            mode11_num_stages=mode11_num_stages,
            mode13_audio_path=mode13_audio_path,
            mode13_voice_preset=mode13_voice_preset,
            mode13_language=mode13_language,
            mode13_show_subtitles=mode13_show_subtitles,
            mode13_skip_final_assembly=mode13_skip_final_assembly,
            mode13_chunk_seconds=mode13_chunk_seconds,
            mode13_segment_seconds=mode13_segment_seconds,
            mode13_video_header_title=mode13_video_header_title,
            mode13_voice_gain_db=mode13_voice_gain_db,
            mode13_voice_tempo_scale=mode13_voice_tempo_scale,
            mode13_voice_pitch_semitones=mode13_voice_pitch_semitones,
            mode13_voice_ai_cleanup=mode13_voice_ai_cleanup,
            mode13_voice_noise_suppression=mode13_voice_noise_suppression,
            mode13_voice_level_normalize=mode13_voice_level_normalize,
            mode13_voice_highpass_hz=mode13_voice_highpass_hz,
            mode13_voice_deesser=mode13_voice_deesser,
            mode13_voice_clarity=mode13_voice_clarity,
            mode13_voice_mud_cut=mode13_voice_mud_cut,
            mode13_voice_compression=mode13_voice_compression,
            control=control,
        )
