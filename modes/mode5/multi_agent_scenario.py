"""
Mode 5 Multi-Agent Scenario Writer — LangGraph orchestration.

Архитектура:
  1. StructureAgent — создаёт структуру глав и подглав (8–15 глав)
  2. ContentAgent — пишет текст по каждой подглаве отдельно, с контекстом предыдущих
  3. CoherenceAgent — проверяет связь между главами и при необходимости вносит правки

Использует LangChain: StateGraph, RunnablePassthrough, LCEL, chat prompts.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from utils.llm import make_llm

from modes.mode5.scenario_writer import LongFormSegment, LongFormScenario

# ─── State Schema для LangGraph ──────────────────────────────────────────────

class SubchapterItem(TypedDict):
    id: str
    title: str
    summary: str
    needs_new_image: bool


class ChapterItem(TypedDict):
    id: int
    title: str
    subchapters: list[SubchapterItem]


class ScenarioOutline(TypedDict):
    title: str
    chapters: list[ChapterItem]


class ScenarioGraphState(TypedDict, total=False):
    topic: str
    language: str
    outline: ScenarioOutline
    segments: list[LongFormSegment]
    subchapter_index: int
    flat_subchapters: list[tuple[int, SubchapterItem]]  # (chapter_idx, subchapter)
    coherence_issues: list[str]
    coherence_fixed: bool
    control: dict | None  # pipeline_control: pause/cancel


# ─── Prompts ──────────────────────────────────────────────────────────────────

# Target: ~6 HOURS = ~54000 words @ 150 wpm. 300–360 segments × 150–180 words each.
# Format: история для сна — длинная, спокойная, с частой сменой картинок.

STRUCTURE_SYSTEM = """You are an EXPERT documentary structure architect.
Your task: create a LOGICAL, COHERENT structure for a ~6 HOUR educational/sleep story video.

CRITICAL: Total runtime target = 6 HOURS (~54000 words). This is a "history for sleep" format.
- 18–22 chapters, each with 6–8 subchapters (MUST have 120–160 subchapters total)
- Each subchapter = 2–4 segments × 150–200 words each
- needs_new_image: true for first subchapter of each chapter AND every 2nd subchapter (≈60–80 image points)
- Output ONLY valid JSON, no markdown or extra text."""

STRUCTURE_OUTPUT_FORMAT = """{
  "title": "Video title",
  "chapters": [
    {
      "id": 1,
      "title": "Chapter title",
      "subchapters": [
        {"id": "1.1", "title": "Subchapter title", "summary": "1–2 sentences what it covers", "needs_new_image": true},
        {"id": "1.2", "title": "...", "summary": "...", "needs_new_image": false},
        {"id": "1.3", "title": "...", "summary": "...", "needs_new_image": true},
        {"id": "1.4", "title": "...", "summary": "...", "needs_new_image": false}
      ]
    }
  ]
}"""

CONTENT_SYSTEM = """You are an EXPERT documentary scriptwriter for a "history for sleep" video.
Write narration for ONE subchapter. Target: ~6 HOURS total (~54000 words). Calm, immersive tone.

RULES:
- Each subchapter = 3–5 segments. Each segment = 150–200 words (2–4 paragraphs).
- Total per subchapter: 450–800 words. Be substantial and detailed.
- Calm, meditative documentary tone — story for falling asleep
- Plain text only, no HTML/Markdown. Historical accuracy: NO invented facts
- image_prompt: English, [Subject]+[Style]+[Lighting]+"horizontal 16:9 landscape, 4K photorealistic"
- Use image_prompt ONLY where needs_new_image=true (first segment of subchapter)."""

COHERENCE_SYSTEM = """You are a COHERENCE CHECKER for long-form documentary scripts.
Check: smooth transitions, no contradictions, references to previous content are correct.
If issues found: return JSON with "issues" (list of strings) and "suggestions" (list of fix descriptions).
If OK: return {"issues": [], "suggestions": []}."""


# ─── Structure Agent ──────────────────────────────────────────────────────────

async def structure_agent(state: ScenarioGraphState) -> dict[str, Any]:
    """Создаёт структуру глав и подглав."""
    topic = state["topic"]
    language = state.get("language", "ru")
    lang_note = "Russian" if language.lower() == "ru" else "English"

    llm = make_llm(temperature=0.3)
    prompt = ChatPromptTemplate.from_messages([
        ("system", STRUCTURE_SYSTEM),
        ("human", """Create structure for a ~1 hour documentary on topic: {topic}
Narration language: {lang_note}

Output format (strict JSON):
{format}

Target: 18–22 chapters, 120–160 subchapters total. MINIMUM 120 for 6-hour video.
Each subchapter = 3–5 segments (150–200 words each). First subchapter of each chapter + every 2nd subchapter: needs_new_image: true.""")
    ])

    chain = prompt | llm | StrOutputParser()
    response = await chain.ainvoke({
        "topic": topic,
        "lang_note": lang_note,
        "format": STRUCTURE_OUTPUT_FORMAT,
    })

    text = response.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"[StructureAgent] JSON parse error: {e}")
        raise ValueError(f"StructureAgent failed to parse JSON: {e}")

    outline: ScenarioOutline = {
        "title": data.get("title") or topic,
        "chapters": [],
    }
    for ch_idx, ch in enumerate(data.get("chapters") or []):
        subchapters = []
        for sc_idx, sc in enumerate(ch.get("subchapters") or []):
            # First subchapter of each chapter + every 2nd subchapter = new image
            needs_img = bool(sc.get("needs_new_image") or sc_idx == 0 or sc_idx % 2 == 0)
            subchapters.append({
                "id": str(sc.get("id", "")),
                "title": str(sc.get("title", "")),
                "summary": str(sc.get("summary", "")),
                "needs_new_image": needs_img,
            })
        outline["chapters"].append({
            "id": int(ch.get("id", 0)),
            "title": str(ch.get("title", "")),
            "subchapters": subchapters,
        })

    flat: list[tuple[int, SubchapterItem]] = []
    for ci, ch in enumerate(outline["chapters"]):
        for sc in ch["subchapters"]:
            flat.append((ci, sc))

    if not flat:
        raise ValueError("StructureAgent produced no subchapters")

    logger.success(f"[StructureAgent] {len(outline['chapters'])} chapters, {len(flat)} subchapters")
    return {
        "outline": outline,
        "segments": [],
        "subchapter_index": 0,
        "flat_subchapters": flat,
    }


# ─── Content Agent (per subchapter) ────────────────────────────────────────────

async def content_agent(state: ScenarioGraphState) -> dict[str, Any]:
    """Пишет текст для одной подглавы с контекстом предыдущих."""
    topic = state["topic"]
    language = state.get("language", "ru")
    outline = state["outline"]
    segments = list(state.get("segments") or [])
    subchapter_index = state.get("subchapter_index", 0)
    flat = state.get("flat_subchapters") or []

    if subchapter_index >= len(flat):
        return {"subchapter_index": subchapter_index}

    ci, subchapter = flat[subchapter_index]
    chapter = outline["chapters"][ci]
    lang_note = "Russian" if language.lower() == "ru" else "English"

    prev_text = ""
    for s in segments[-20:]:  # последние 20 сегментов как контекст
        prev_text += (s.get("narration_text") or "") + "\n\n"

    llm = make_llm(temperature=0.4)
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONTENT_SYSTEM),
        ("human", """Topic: {topic}
Full outline (chapters/subchapters): {outline_json}

Current subchapter to write:
- Chapter {ch_title}: {sub_id} — {sub_title}
- Summary: {sub_summary}
- Needs new image: {needs_image}

Previous narration (for continuity, end naturally):
{prev_text}

Write 3–5 segments for this subchapter (150–200 words EACH — 6-hour sleep story, be substantial). Output JSON:
{{
  "segments": [
    {{ "narration_text": "...", "image_prompt": "..." or null }},
    ...
  ]
}}

Language: {lang_note}. Plain text only. First segment of subchapter with needs_new_image=true MUST have image_prompt.""")
    ])

    chain = prompt | llm | StrOutputParser()
    response = await chain.ainvoke({
        "topic": topic,
        "outline_json": json.dumps(outline, ensure_ascii=False, indent=2),
        "ch_title": chapter["title"],
        "sub_id": subchapter["id"],
        "sub_title": subchapter["title"],
        "sub_summary": subchapter["summary"],
        "needs_image": subchapter["needs_new_image"],
        "prev_text": prev_text[-3000:] if prev_text else "(beginning of video)",
        "lang_note": lang_note,
    })

    text = response.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"[ContentAgent] sub {subchapter['id']} JSON parse error: {e}, using raw")
        img = f"Documentary scene for {subchapter['title']}, cinematic, horizontal 16:9 landscape, 4K photorealistic" if subchapter.get("needs_new_image") else None
        data = {"segments": [{"narration_text": text, "image_prompt": img}]}

    new_segments = data.get("segments") or []
    for i, s in enumerate(new_segments):
        nt = (s.get("narration_text") or s.get("text") or "").strip()
        if not nt:
            continue
        img = s.get("image_prompt")
        if img is not None:
            img = str(img).strip() or None
        if subchapter.get("needs_new_image") and i == 0 and not img:
            img = f"Documentary scene for {subchapter['title']}, cinematic, horizontal 16:9 landscape, 4K photorealistic"
        segments.append({
            "index": len(segments) + 1,
            "narration_text": nt,
            "image_prompt": img,
        })

    logger.info(f"[ContentAgent] sub {subchapter['id']}: +{len([s for s in new_segments if (s.get('narration_text') or s.get('text', '')).strip()])} segments")

    # Checkpoint for pause/cancel after each subchapter
    control = state.get("control")
    if control:
        from pipeline_control import checkpoint
        await checkpoint(control)

    return {"segments": segments, "subchapter_index": subchapter_index + 1}


def _route_after_content(state: ScenarioGraphState) -> Literal["content", "coherence"]:
    """Маршрутизация: ещё подглавы → content, иначе → coherence."""
    idx = state.get("subchapter_index", 0)
    flat = state.get("flat_subchapters") or []
    if idx < len(flat):
        return "content"
    return "coherence"


# ─── Coherence Agent ──────────────────────────────────────────────────────────

async def coherence_agent(state: ScenarioGraphState) -> dict[str, Any]:
    """Проверяет связность и при необходимости предлагает правки."""
    outline = state["outline"]
    segments = state.get("segments") or []
    if not segments:
        return {"coherence_issues": [], "coherence_fixed": True}

    full_text = "\n\n".join(s.get("narration_text", "") for s in segments)
    outline_json = json.dumps(outline, ensure_ascii=False, indent=2)

    llm = make_llm(temperature=0.1)
    # Use expected_format variable to avoid brace-escaping issues in template
    expected_format = '{"issues": ["..."], "suggestions": ["..."]}'
    prompt = ChatPromptTemplate.from_messages([
        ("system", COHERENCE_SYSTEM),
        ("human", """Full script outline: {outline}

Full narration (segments concatenated): {script}

Check: smooth transitions between chapters? No contradictions? References correct?
Output JSON: {expected_format}"""),
    ])

    chain = prompt | llm | StrOutputParser()
    response = await chain.ainvoke({
        "outline": outline_json,
        "script": full_text[:12000],
        "expected_format": expected_format,
    })

    text = response.strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"coherence_issues": [], "coherence_fixed": True}

    issues = data.get("issues") or []
    suggestions = data.get("suggestions") or []

    if issues:
        logger.warning(f"[CoherenceAgent] Found {len(issues)} issues: {issues[:2]}...")
    else:
        logger.success("[CoherenceAgent] No coherence issues")

    return {
        "coherence_issues": issues,
        "coherence_fixed": len(issues) == 0,
    }


# ─── LangGraph Workflow ────────────────────────────────────────────────────────

def _build_scenario_graph():
    from langgraph.graph import StateGraph, START, END

    # State: используем dict-совместимую схему
    class State(TypedDict, total=False):
        topic: str
        language: str
        outline: ScenarioOutline
        segments: list[LongFormSegment]
        subchapter_index: int
        flat_subchapters: list[tuple[int, SubchapterItem]]
        coherence_issues: list[str]
        coherence_fixed: bool
        control: dict | None

    graph = StateGraph(State)

    graph.add_node("structure", structure_agent)
    graph.add_node("content", content_agent)
    graph.add_node("coherence", coherence_agent)

    graph.add_edge(START, "structure")
    graph.add_edge("structure", "content")
    graph.add_conditional_edges("content", _route_after_content, {"content": "content", "coherence": "coherence"})
    graph.add_edge("coherence", END)

    return graph.compile()


async def run_multi_agent_scenario(
    topic: str,
    language: str = "ru",
    control: dict | None = None,
) -> LongFormScenario:
    """
    Запускает мультиагентный сценарист:
    StructureAgent → ContentAgent (на каждую подглаву) → CoherenceAgent
    """
    graph = _build_scenario_graph()

    initial: ScenarioGraphState = {
        "topic": topic,
        "language": language,
        "control": control,
    }

    result = await graph.ainvoke(initial)
    segments: list[LongFormSegment] = result.get("segments") or []
    outline = result.get("outline") or {}
    title = outline.get("title") or topic

    if not segments:
        raise ValueError("Multi-agent scenario produced no segments")

    for i, s in enumerate(segments):
        s["index"] = i + 1

    if not segments[0].get("image_prompt"):
        segments[0]["image_prompt"] = (
            f"Documentary style illustration of {topic}, "
            "cinematic lighting, horizontal 16:9 landscape, 4K photorealistic"
        )

    logger.success(f"[Mode5 Multi-Agent] Scenario: {len(segments)} segments, "
                  f"{sum(1 for s in segments if s.get('image_prompt'))} image points")
    return {"title": title, "segments": segments}
