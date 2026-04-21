"""
Mode 1 Pipeline — Top-5 facts (Trends → FactMiner → Scenario → Images → Video → Publisher).

Sequential multi-agent flow with checkpoint support.
"""

from __future__ import annotations

import re
import time
from typing import Any

from loguru import logger

from config import settings
from orchestrator.tracker import AgentExecutionTracker


async def run_mode1_pipeline(
    topic: str | None = None,
    num_scenes: int = 5,
    session_id: str | None = None,
    local_only: bool = False,
    auto_topic: bool = False,
    use_scenario: bool = True,
    show_subtitles: bool = True,
    use_fact_check: bool = True,
    fact_check_strict: bool = False,
    prebuilt_scenario: dict | None = None,
    language: str = "ru",
    custom_title_bg_path: str | None = None,
    custom_outro_bg_path: str | None = None,
    reference_image_path: str | None = None,
    control: dict | None = None,
) -> dict[str, Any]:
    """Mode 1: Top-5 facts — full sequential pipeline."""
    from pipeline_control import checkpoint

    tracker = AgentExecutionTracker(timeout=300.0, max_retries=1)
    session_id = session_id or str(int(time.time()))

    def _extract_top5_subject(t: str) -> str:
        t = (t or "").strip()
        m = re.match(r"^\s*Топ[-\s]*5\s*фактов\s+(?:о|про)\s*(.+?)\s*$", t, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(".")
        return t

    # Step 1: Trends (optional)
    await checkpoint(control)
    trend_context = None
    if not prebuilt_scenario and (auto_topic or topic is None):
        logger.info("Step 1 - Trends Analyzer Agent")
        from agents.trends_analyzer.agent import run_trends_agent
        trends = await run_trends_agent(top_n=1)
        trend_context = trends[0]
        topic = trend_context.get("topic") or trend_context.get("video_angle") or ""
        logger.success(f"Auto-selected topic: {topic!r}")
    else:
        logger.info(f"Topic: {topic!r}")

    topic_subject = _extract_top5_subject(topic)
    step_offset = 1 if (auto_topic and not prebuilt_scenario) else 0
    has_fact_miner = bool(use_scenario and (not prebuilt_scenario) and settings.use_fact_miner)
    total_steps = 3 + step_offset + (1 if use_scenario else 0) + (1 if has_fact_miner else 0)
    logger.info(f"=== Mode 1 | topic={topic!r} | session={session_id} | scenario={use_scenario} ===")

    from agents.content_generator.agent import run_image_generator_agent
    from agents.video_editor.agent import run_video_editor_agent

    scenario = None
    video_title: str | None = None
    video_hook: str | None = None
    video_outro: str | None = None
    fact_context: dict | None = None

    if prebuilt_scenario:
        scenario = prebuilt_scenario.get("scenes", [])
        video_title = prebuilt_scenario.get("title") or topic
        video_hook = prebuilt_scenario.get("hook", "")
        video_outro = prebuilt_scenario.get("outro", "")
        topic = video_title or topic
        logger.success(f"Using pre-built scenario: {topic!r} | {len(scenario)} scenes")

    elif use_scenario:
        if has_fact_miner:
            step = 1 + step_offset
            logger.info(f"Step {step}/{total_steps} - Fact Miner Agent")
            from agents.fact_miner.agent import run_fact_miner_agent
            fact_context = await run_fact_miner_agent(
                topic=topic_subject or "",
                num_scenes=num_scenes,
                trend_context=trend_context,
            )

        step = 1 + step_offset + (1 if has_fact_miner else 0)
        logger.info(f"Step {step}/{total_steps} - Scenario Writer Agent")
        from agents.scenario_writer.agent import run_scenario_writer_agent
        scenario_obj = await run_scenario_writer_agent(
            topic_subject,
            num_scenes=num_scenes,
            trend_context=trend_context,
            fact_context=fact_context,
        )
        scenario = scenario_obj["scenes"]
        video_title = scenario_obj.get("title") or topic_subject
        video_hook = scenario_obj.get("hook", "")
        video_outro = scenario_obj.get("outro", "")
        topic = video_title
        logger.success(f"Scenario ready: {topic!r} | hook: {(video_hook or '')[:60]}")

    await checkpoint(control)
    step = 2 + step_offset + (1 if use_scenario else 0) + (1 if has_fact_miner else 0)
    logger.info(f"Step {step}/{total_steps} - Image Generator Agent")
    scenes = await run_image_generator_agent(topic, num_scenes, session_id, scenario=scenario)

    await checkpoint(control)
    step += 1
    logger.info(f"Step {step}/{total_steps} - Video Editor Agent")
    video_path = await run_video_editor_agent(
        scenes,
        session_id=session_id,
        title=video_title,
        hook=video_hook,
        outro=video_outro,
        topic=topic,
        show_subtitles=show_subtitles,
    )

    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=topic,
        session_id=session_id,
        video_path=video_path,
        video_angle=trend_context.get("video_angle", "") if trend_context else "",
    )

    if local_only:
        logger.success(f"=== LOCAL ONLY | video={video_path} ===")
        return {
            "session_id": session_id,
            "video_path": video_path,
            "topic": topic,
            "trend": trend_context,
            "report": None,
        }

    step += 1
    logger.info(f"Step {step}/{total_steps} - Publisher Agent")
    from agents.publisher.agent import run_publisher_agent
    report = await run_publisher_agent(video_path, scenes, topic)

    summary = tracker.get_summary()
    logger.success(
        f"=== Pipeline DONE | video={video_path} | "
        f"success_rate={summary['success_rate']:.0%} | duration={summary['total_duration']:.1f}s ==="
    )
    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": topic,
        "trend": trend_context,
        "report": report,
        "execution_summary": summary,
        "execution_log": tracker.get_log(),
    }
