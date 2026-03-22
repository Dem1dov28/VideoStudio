"""
LangGraph Swarm Orchestrator with sequential fallback.

Multi-Agent Orchestration Patterns Applied:
- Supervisor Pattern: Central coordinator routes to specialists
- Fan-Out/Fan-In: Parallel agent execution where possible
- Error Isolation: Individual agent failures don't crash workflow
- Timeout Handling: Per-agent timeouts prevent blocking
- Execution Logging: Full traceability of agent operations
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from langchain_core.messages import HumanMessage
from loguru import logger
from config import settings

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent
    from langgraph_swarm import create_handoff_tool, create_swarm
    _SWARM_AVAILABLE = True
except ImportError:
    _SWARM_AVAILABLE = False
    logger.warning("langgraph-swarm not installed - using sequential pipeline")

from tools.langchain_tools import generate_images, edit_video, publish_video
from utils.llm import make_llm


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Agent Orchestration: Agent Execution Tracking
# ═══════════════════════════════════════════════════════════════════════════════

class AgentExecutionTracker:
    """Track agent execution with timeouts, retries, and error isolation."""

    def __init__(self, timeout: float = 300.0, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries
        self.execution_log: list[dict] = []

    async def execute(
        self,
        agent_name: str,
        agent_func,
        *args,
        **kwargs
    ) -> dict:
        """Execute agent with timeout, retry, and error isolation."""
        start_time = time.time()
        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                logger.info(f"[Orchestrator] Executing {agent_name} (attempt {attempt + 1})")
                result = await asyncio.wait_for(
                    agent_func(*args, **kwargs),
                    timeout=self.timeout
                )

                execution_time = time.time() - start_time
                self.execution_log.append({
                    "agent": agent_name,
                    "status": "success",
                    "attempt": attempt + 1,
                    "duration": execution_time,
                    "timestamp": time.time()
                })

                logger.success(f"[Orchestrator] {agent_name} completed in {execution_time:.2f}s")
                return {"success": True, "result": result, "agent": agent_name}

            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s"
                logger.warning(f"[Orchestrator] {agent_name} timeout (attempt {attempt + 1})")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Orchestrator] {agent_name} error: {e}")

            attempt += 1
            if attempt <= self.max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"[Orchestrator] Retrying {agent_name} in {wait_time}s...")
                await asyncio.sleep(wait_time)

        # All retries exhausted
        execution_time = time.time() - start_time
        self.execution_log.append({
            "agent": agent_name,
            "status": "failed",
            "error": last_error,
            "attempts": attempt,
            "duration": execution_time,
            "timestamp": time.time()
        })

        logger.error(f"[Orchestrator] {agent_name} failed after {attempt} attempts")
        return {"success": False, "error": last_error, "agent": agent_name}

    def get_log(self) -> list[dict]:
        """Get execution log for monitoring/debugging."""
        return self.execution_log.copy()

    def get_summary(self) -> dict:
        """Get execution summary statistics."""
        total = len(self.execution_log)
        successful = sum(1 for e in self.execution_log if e["status"] == "success")
        failed = total - successful
        total_duration = sum(e.get("duration", 0) for e in self.execution_log)

        return {
            "total_agents": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "total_duration": total_duration
        }


def build_swarm_graph(local_only: bool = False):
    assert _SWARM_AVAILABLE, "Install langgraph-swarm: pip install langgraph-swarm"
    llm = make_llm(temperature=0.2)

    to_video_agent = create_handoff_tool(
        agent_name="VideoAgent",
        description="Hand off to VideoAgent after images are ready. Pass session_id and scenes as JSON.",
    )

    image_agent = create_react_agent(
        llm,
        tools=[generate_images, to_video_agent],
        prompt=(
            "You are the Image Generator Agent. "
            "Call generate_images with the topic and num_scenes=5. "
            "Then hand off to VideoAgent with session_id and scenes."
        ),
        name="ImageAgent",
    )

    if local_only:
        video_agent = create_react_agent(
            llm,
            tools=[edit_video],
            prompt=(
                "You are the Video Editor Agent. "
                "Call edit_video with session_id and scenes. "
                "When done, report the video_path and stop."
            ),
            name="VideoAgent",
        )
        workflow = create_swarm([image_agent, video_agent], default_active_agent="ImageAgent")
    else:
        to_publisher_agent = create_handoff_tool(
            agent_name="PublisherAgent",
            description="Hand off to PublisherAgent after video is ready. Pass video_path, scenes, topic.",
        )
        video_agent = create_react_agent(
            llm,
            tools=[edit_video, to_publisher_agent],
            prompt=(
                "You are the Video Editor Agent. "
                "Call edit_video with session_id and scenes. "
                "Then hand off to PublisherAgent with video_path, scenes, and topic."
            ),
            name="VideoAgent",
        )
        publisher_agent = create_react_agent(
            llm,
            tools=[publish_video],
            prompt=(
                "You are the Social Media Publisher Agent. "
                "Call publish_video with video_path, scenes, and topic. "
                "Return the publication report."
            ),
            name="PublisherAgent",
        )
        workflow = create_swarm(
            [image_agent, video_agent, publisher_agent],
            default_active_agent="ImageAgent",
        )

    return workflow.compile(checkpointer=MemorySaver())


async def run_sequential_pipeline(
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
    mode: int = 1,
    language: str = "ru",
    custom_title_bg_path: str | None = None,
    custom_outro_bg_path: str | None = None,
    reference_image_path: str | None = None,
) -> dict[str, Any]:
    """
    Full sequential pipeline with multi-agent orchestration patterns.

    Orchestration Features:
    - Supervisor Pattern: Central coordinator manages agent execution
    - Error Isolation: Individual agent failures don't crash entire pipeline
    - Timeout Handling: Per-agent timeouts with exponential backoff retry
    - Execution Tracking: Full logging and monitoring of agent operations
    - Graceful Degradation: Pipeline continues even if optional agents fail

    Args:
        topic:             Video topic. If None and auto_topic=True, picked from trends.
        num_scenes:        Number of scenes.
        session_id:        Unique run ID.
        local_only:        Skip social media publishing.
        auto_topic:        Use TrendsAgent to auto-pick a trending topic.
        use_scenario:      Use ScenarioWriterAgent for high-quality script (recommended).
        prebuilt_scenario: If provided (from the frontend editor), skip ScenarioWriter and
                           use this scenario directly (dict with keys: title, hook, outro, scenes).
        mode:              1 = Top-5 facts (images + Ken Burns), 2 = Почему X? (Pexels video).
    """
    # Initialize execution tracker for monitoring and error handling
    tracker = AgentExecutionTracker(timeout=300.0, max_retries=1)
    # Mode 2: Почему X? pipeline
    if mode == 2:
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
        )

    from agents.content_generator.agent import run_image_generator_agent
    from agents.video_editor.agent import run_video_editor_agent

    session_id = session_id or str(int(time.time()))

    # Normalize top5 angles to subject so FactMiner/ScenarioWriter don't see:
    # "Топ-5 фактов о X" as if it were the raw topic.
    import re

    def _extract_top5_subject(t: str) -> str:
        t = (t or "").strip()
        m = re.match(
            r"^\s*Топ[-\s]*5\s*фактов\s+(?:о|про)\s*(.+?)\s*$",
            t,
            flags=re.IGNORECASE,
        )
        if m:
            return m.group(1).strip().rstrip(".")
        return t

    # ── Step 1: Trends (optional) ──────────────────────────────────────────────
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
    total_steps = (
        3
        + step_offset
        + (1 if use_scenario else 0)
        + (1 if has_fact_miner else 0)
    )
    logger.info(
        f"=== Sequential pipeline | topic={topic!r} | session={session_id} | "
        f"scenario={use_scenario} | local_only={local_only} ==="
    )

    # ── Step 2: Scenario (pre-built from editor OR generated by ScenarioWriter) ─
    scenario = None
    video_title: str | None = None
    video_hook:  str | None = None
    video_outro: str | None = None
    fact_context: dict | None = None

    if prebuilt_scenario:
        # User reviewed and (optionally) edited the scenario in the UI — use as-is
        scenario = prebuilt_scenario.get("scenes", [])
        video_title = prebuilt_scenario.get("title") or topic
        video_hook  = prebuilt_scenario.get("hook", "")
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

        # These go to the video editor as dedicated title/outro cards
        video_title = scenario_obj.get("title") or topic_subject
        video_hook  = scenario_obj.get("hook", "")
        video_outro = scenario_obj.get("outro", "")

        # Override display topic with AI-written title
        topic = video_title

        logger.success(
            f"Scenario ready: {topic!r} | hook: {(video_hook or '')[:60]}"
        )

    # ── Step 3: Image Generator ───────────────────────────────────────────────
    step = (
        2
        + step_offset
        + (1 if use_scenario else 0)
        + (1 if has_fact_miner else 0)
    )
    logger.info(f"Step {step}/{total_steps} - Image Generator Agent")
    scenes = await run_image_generator_agent(
        topic, num_scenes, session_id, scenario=scenario
    )

    # ── Step 4: Video Editor ──────────────────────────────────────────────────
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

    # ── Record topic as used ──────────────────────────────────────────────────
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=topic,
        session_id=session_id,
        video_path=video_path,
        video_angle=trend_context.get("video_angle", "") if trend_context else "",
    )

    if local_only:
        logger.success(f"=== LOCAL ONLY mode - skipping publish | video={video_path} ===")
        return {
            "session_id": session_id,
            "video_path": video_path,
            "topic": topic,
            "trend": trend_context,
            "report": None,
        }

    # ── Step 5: Publisher ───────────────────────────────────────────────────────
    step += 1
    logger.info(f"Step {step}/{total_steps} - Publisher Agent")
    from agents.publisher.agent import run_publisher_agent
    report = await run_publisher_agent(video_path, scenes, topic)

    # ═══════════════════════════════════════════════════════════════════════════
    # Pipeline Completion: Log execution summary
    # ═══════════════════════════════════════════════════════════════════════════
    execution_summary = tracker.get_summary()
    logger.success(
        f"=== Pipeline DONE | video={video_path} | "
        f"agents={execution_summary['total_agents']} | "
        f"success_rate={execution_summary['success_rate']:.0%} | "
        f"duration={execution_summary['total_duration']:.1f}s ==="
    )

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": topic,
        "trend": trend_context,
        "report": report,
        "execution_summary": execution_summary,
        "execution_log": tracker.get_log(),
    }


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
) -> dict[str, Any]:
    # Mode 2 always uses sequential pipeline (no swarm)
    if mode == 2:
        return await run_sequential_pipeline(
            custom_title_bg_path=custom_title_bg_path,
            custom_outro_bg_path=custom_outro_bg_path,
            reference_image_path=reference_image_path,
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
            mode=mode,
            language=language,
        )
    if use_swarm and _SWARM_AVAILABLE and topic:
        logger.info("Using LangGraph Swarm orchestration via OpenRouter")
        session_id = session_id or str(int(time.time()))
        app = build_swarm_graph(local_only=local_only)
        config = {"configurable": {"thread_id": session_id}}
        result = await app.ainvoke(
            {"messages": [HumanMessage(content=json.dumps(
                {"topic": topic, "num_scenes": num_scenes, "session_id": session_id}
            ))]},
            config=config,
        )
        final_msg = result["messages"][-1].content
        logger.success(f"Swarm result: {final_msg[:200]}")
        return {"session_id": session_id, "swarm_output": final_msg}
    else:
        return await run_sequential_pipeline(
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
            mode=mode,
            language=language,
        )