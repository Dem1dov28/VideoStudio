"""LangChain Tool wrappers for each agent."""

from __future__ import annotations

import json
import time

from langchain_core.tools import tool
from loguru import logger


@tool
async def generate_images(input_json: str) -> str:
    """Generate images for a video topic.
    Input JSON: {topic, num_scenes (opt), session_id (opt)}
    Returns JSON with session_id and scenes list."""
    from agents.content_generator.agent import run_image_generator_agent
    data = json.loads(input_json)
    topic = data["topic"]
    num_scenes = data.get("num_scenes", 5)
    session_id = data.get("session_id", str(int(time.time())))
    scenes = await run_image_generator_agent(topic, num_scenes, session_id)
    return json.dumps({"session_id": session_id, "scenes": scenes})


@tool
async def edit_video(input_json: str) -> str:
    """Assemble video from generated scenes.
    Input JSON: {session_id, scenes}
    Returns JSON with video_path."""
    from agents.video_editor.agent import run_video_editor_agent
    data = json.loads(input_json)
    session_id = data["session_id"]
    scenes = data["scenes"]
    video_path = await run_video_editor_agent(scenes, session_id)
    return json.dumps({"session_id": session_id, "video_path": video_path})


@tool
async def publish_video(input_json: str) -> str:
    """Publish video to social media platforms.
    Input JSON: {video_path, scenes, topic, schedule_at (opt ISO8601)}
    Returns publication report JSON."""
    from agents.publisher.agent import run_publisher_agent
    from datetime import datetime
    data = json.loads(input_json)
    schedule_at = None
    if data.get("schedule_at"):
        schedule_at = datetime.fromisoformat(data["schedule_at"])
    report = await run_publisher_agent(
        data["video_path"], data["scenes"], data["topic"], schedule_at
    )
    return json.dumps(report, ensure_ascii=False)


ALL_TOOLS = [generate_images, edit_video, publish_video]