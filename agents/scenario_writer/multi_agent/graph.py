"""
Multi-agent scenario writer — OutlineAgent → SceneAgent (x5).

LangGraph workflow for Top-5 facts format.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from utils.llm import make_llm

from agents.scenario_writer.types import Scenario, ScenarioScene
from agents.scenario_writer.multi_agent.prompts import OUTLINE_SYSTEM, SCENE_SYSTEM
from agents.video_editor.tts import sanitize_voiceover_text


class OutlineItem(TypedDict):
    index: int
    summary: str


class ScenarioGraphState(TypedDict, total=False):
    topic: str
    num_scenes: int
    trend_context: dict | None
    fact_context: dict | None
    outline: dict
    scenes: list[ScenarioScene]
    scene_index: int
    hook: str
    outro: str
    title: str


def _extract_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else text


async def outline_agent(state: ScenarioGraphState) -> dict:
    """Create structure: title, hook, 5 fact summaries, outro."""
    topic = state["topic"]
    num_scenes = state.get("num_scenes", 5)
    trend = state.get("trend_context") or {}
    fact = state.get("fact_context")

    llm = make_llm(temperature=0.5)
    prompt = ChatPromptTemplate.from_messages([
        ("system", OUTLINE_SYSTEM),
        ("human", """Topic: {topic}
Scenes: {num_scenes}
Angle: {angle}
Why trending: {why}

{fact_context}

Output JSON only.""")
    ])
    chain = prompt | llm | StrOutputParser()
    raw = await chain.ainvoke({
        "topic": topic,
        "num_scenes": num_scenes,
        "angle": trend.get("video_angle", ""),
        "why": trend.get("why_trending", ""),
        "fact_context": f"Fact context (use key_points per scene):\n{json.dumps(fact, ensure_ascii=False)[:2000]}" if fact else "",
    })

    data = json.loads(_extract_json(raw))
    logger.info("[OutlineAgent] Structure ready")
    return {
        "outline": data,
        "title": data.get("title", topic),
        "hook": data.get("hook_preview", ""),
        "outro": data.get("outro_preview", "Подпишись — будет ещё круче."),
        "scenes": [],
        "scene_index": 0,
    }


async def scene_agent(state: ScenarioGraphState) -> dict:
    """Write one scene (narration, subtitle, image_prompt)."""
    topic = state["topic"]
    outline = state.get("outline") or {}
    scenes = list(state.get("scenes") or [])
    scene_index = state.get("scene_index", 0)
    fact_context = state.get("fact_context")
    num_scenes = state.get("num_scenes", 5)

    if scene_index >= num_scenes:
        return {"scene_index": scene_index}

    facts = outline.get("facts") or []
    fact_summary = ""
    if scene_index < len(facts) and isinstance(facts[scene_index], dict):
        fact_summary = str(facts[scene_index].get("summary", ""))

    prev_text = "\n".join(
        f"Scene {i+1}: {s.get('narration_text', '')}"
        for i, s in enumerate(scenes[-5:])
    )
    fact_scene = None
    if fact_context and fact_context.get("scenes") and scene_index < len(fact_context["scenes"]):
        fact_scene = fact_context["scenes"][scene_index]

    llm = make_llm(temperature=0.6)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SCENE_SYSTEM),
        ("human", """Topic: {topic}
Scene {idx} of {total}. Fact summary: {summary}

Previous scenes:
{prev}

{fact_points}

Output JSON: {{"narration_text": "...", "subtitle_text": "Факт {idx} ...", "image_prompt": "..."}}""")
    ])
    chain = prompt | llm | StrOutputParser()
    fact_points = ""
    if fact_scene:
        fact_points = f"Use these key_points: {json.dumps(fact_scene.get('key_points', []), ensure_ascii=False)}"

    raw = await chain.ainvoke({
        "topic": topic,
        "idx": scene_index + 1,
        "total": num_scenes,
        "summary": fact_summary,
        "prev": prev_text or "(first scene)",
        "fact_points": fact_points,
    })

    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        data = {"narration_text": fact_summary, "subtitle_text": f"Факт {scene_index + 1}", "image_prompt": f"{topic}, vertical 9:16, 4K"}

    nr = sanitize_voiceover_text(data.get("narration_text", ""))
    st = sanitize_voiceover_text(data.get("subtitle_text", f"Факт {scene_index + 1}"))
    ip = data.get("image_prompt", f"{topic}, cinematic, vertical 9:16 portrait, 4K photorealistic")
    if "vertical" not in ip.lower():
        ip += ", vertical 9:16 portrait, 4K photorealistic"

    scenes.append({
        "index": scene_index + 1,
        "narration_text": nr,
        "subtitle_text": st,
        "image_prompt": ip,
        "video_prompt": "",
    })
    logger.info(f"[SceneAgent] Scene {scene_index + 1}/{num_scenes} done")
    return {"scenes": scenes, "scene_index": scene_index + 1}


def _route_after_scene(state: ScenarioGraphState) -> Literal["scene", "finalize"]:
    idx = state.get("scene_index", 0)
    total = state.get("num_scenes", 5)
    return "scene" if idx < total else "finalize"


async def finalize_agent(state: ScenarioGraphState) -> dict:
    """Assemble final Scenario with hook/outro."""
    return {}


def _build_graph():
    from langgraph.graph import StateGraph, START, END

    class State(TypedDict, total=False):
        topic: str
        num_scenes: int
        trend_context: dict | None
        fact_context: dict | None
        outline: dict
        scenes: list[ScenarioScene]
        scene_index: int
        hook: str
        outro: str
        title: str

    graph = StateGraph(State)
    graph.add_node("outline", outline_agent)
    graph.add_node("scene", scene_agent)
    graph.add_node("finalize", finalize_agent)

    graph.add_edge(START, "outline")
    graph.add_edge("outline", "scene")
    graph.add_conditional_edges("scene", _route_after_scene, {"scene": "scene", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_multi_agent_scenario(
    topic: str,
    num_scenes: int = 5,
    trend_context: dict | None = None,
    fact_context: dict | None = None,
) -> Scenario:
    """Run multi-agent Top-5 scenario writer."""
    graph = _build_graph()
    initial: ScenarioGraphState = {
        "topic": topic,
        "num_scenes": num_scenes,
        "trend_context": trend_context,
        "fact_context": fact_context,
    }
    result = await graph.ainvoke(initial)
    scenario: Scenario = {
        "title": sanitize_voiceover_text(result.get("title", topic)),
        "hook": sanitize_voiceover_text(result.get("hook", "")),
        "scenes": result.get("scenes", []),
        "outro": sanitize_voiceover_text(result.get("outro", "")),
    }
    for i, s in enumerate(scenario["scenes"]):
        s["index"] = i + 1
    logger.success(f"[MultiAgent Scenario] {len(scenario['scenes'])} scenes")
    return scenario
