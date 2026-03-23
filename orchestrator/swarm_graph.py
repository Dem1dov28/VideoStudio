"""
LangGraph Swarm — ImageAgent → VideoAgent → PublisherAgent.

Handoff-based multi-agent workflow for Mode 1 (when use_swarm=True).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage
from loguru import logger

from config import settings
from tools.langchain_tools import generate_images, edit_video, publish_video
from utils.llm import make_llm

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent
    from langgraph_swarm import create_handoff_tool, create_swarm
    _SWARM_AVAILABLE = True
except ImportError:
    _SWARM_AVAILABLE = False
    logger.warning("langgraph-swarm not installed - using sequential pipeline")


def build_swarm_graph(local_only: bool = False) -> Any:
    """Build LangGraph Swarm: ImageAgent → VideoAgent [→ PublisherAgent]."""
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


async def run_swarm_pipeline(
    topic: str,
    num_scenes: int = 5,
    session_id: str | None = None,
    local_only: bool = False,
) -> dict[str, Any]:
    """Run LangGraph Swarm pipeline (Mode 1 with use_swarm=True)."""
    import time
    session_id = session_id or str(int(time.time()))
    app = build_swarm_graph(local_only=local_only)
    config = {"configurable": {"thread_id": session_id}}
    result = await app.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=json.dumps({
                        "topic": topic,
                        "num_scenes": num_scenes,
                        "session_id": session_id,
                    })
                )
            ]
        },
        config=config,
    )
    final_msg = result["messages"][-1].content
    logger.success(f"Swarm result: {final_msg[:200]}")
    return {"session_id": session_id, "swarm_output": final_msg}
