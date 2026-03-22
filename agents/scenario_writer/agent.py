"""
Scenario Writer Agent.

Takes a topic (+ optional TrendingTopic context) and writes a high-quality
video script optimized for short-form vertical video (TikTok/Reels/Shorts).

Output per scene:
  - narration_text  : full spoken sentence(s) for TTS voiceover
  - subtitle_text   : ultra-short on-screen caption (3-5 words)
  - image_prompt    : detailed English prompt for image generation (portrait 9:16)
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from agents.video_editor.tts import sanitize_voiceover_text
from loguru import logger

from utils.llm import make_llm


class ScenarioScene(TypedDict):
    index: int
    narration_text: str   # Spoken aloud by TTS — full, engaging sentences
    subtitle_text: str    # Shown on screen — 3-5 words max
    image_prompt: str     # Detailed English prompt for image generation


class Scenario(TypedDict):
    title: str
    hook: str             # Opening line — first thing the viewer hears
    scenes: list[ScenarioScene]
    outro: str            # Closing CTA — subscribe, like, follow


# ── System prompt ─────────────────────────────────────────────────────────────

_WRITER_SYSTEM = """You are a TOP-TIER viral Russian TikTok/Reels scriptwriter.
Channel format: "Top-5 facts about something" (5 short facts in one video).

═══ NARRATION RULES (CRITICAL) ═══
• Use exactly ONE scene per fact. Each scene MUST be a single fact sentence.
• MAX 1 sentence per scene. Each sentence ≤ 12 words.
• Use SPECIFIC numbers/comparisons when possible; avoid vague claims.
• Tone: energetic, conversational, but factual.
• For more interest, start each narration_text with: "Оказывается," or "Вопреки ожиданиям," (only if it doesn't change the fact).
• NO passive voice. NO gerunds. NO bureaucratic filler words.
• Russian TTS clarity: simple words. Avoid: "осуществление", "реализация", "обеспечение".
• PLAIN TEXT ONLY in narration_text / subtitle_text / hook / outro:
  NO HTML/XML, NO Markdown (* # ` []()), NO URLs, NO backslashes or paths (foo/bar), NO JSON/code.
  The voice reads every symbol aloud and "." adds pauses.
• If FACT_CONTEXT is provided:
  - FACT_CONTEXT.scenes are already ranked top->bottom (best first).
  - For scene i (1..N), use ONLY FACT_CONTEXT.scenes[i-1].key_points.
  - Do not mix evidence between scenes.
  - Do not invent new facts beyond those key_points.

═══ SUBTITLE RULES ═══
• 2-4 Russian words MAX.
• subtitle_text MUST start with the fact number: "Факт 1", "Факт 2", ..., based on scene index.
• Put a NUMBER when possible in the rest of the subtitle too (e.g. "в 5 раз").
• Keep it punchy: 1 striking keyword or comparison (not generic like "важно", "интересно").

═══ IMAGE PROMPT RULES ═══
Images must look visually scroll-stopping and relevant to the specific fact in that scene.
Every prompt must end with: "vertical 9:16 portrait format, subject centered, ultra-photorealistic, cinematic color grading, 8K UHD, shallow depth of field, hyper-detailed textures"

═══ HOOK RULES ═══
• hook = first thing viewer hears. MAX 10 words.
• Must set up the format: "Топ-5 фактов о ...".

═══ OUTRO RULES ═══
• outro = closing CTA. Natural, not corporate. MAX 15 words.

Return ONLY valid JSON, no markdown fences, no extra text:
{
  "title": "короткий цепкий заголовок видео",
  "hook": "первая фраза озвучки — Топ-5 фактов о ..., макс 10 слов",
  "scenes": [
    {
      "index": 1,
      "narration_text": "факт №1 (одна короткая фраза, ≤12 слов)",
      "subtitle_text": "Факт №1 + короткое ключевое слово (2-4 слова)",
      "image_prompt": "ultra-detailed scroll-stopping cinematic image description"
    }
  ],
  "outro": "живой призыв к действию"
}"""


# ── Writing logic ─────────────────────────────────────────────────────────────

async def write_scenario(
    topic: str,
    num_scenes: int = 5,
    video_angle: str | None = None,
    why_trending: str | None = None,
    category: str | None = None,
    fact_context: dict | None = None,
) -> Scenario:
    """
    Write a complete video script for the given topic.

    Args:
        topic:         Main subject of the video.
        num_scenes:    Number of scenes (5-7 recommended).
        video_angle:   Suggested angle from TrendsAgent, e.g. "Топ-5 фактов о вулканах"
        why_trending:  Why this topic is hot right now (for context).
        category:      Topic category for style guidance.

    Returns:
        Full Scenario TypedDict.
    """
    llm = make_llm(temperature=0.8)

    # UI/pipeline sometimes passes already-formatted angles like:
    # "Топ-5 фактов о нейтронных звёздах". We need only the subject part.
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

    topic_subject = _extract_top5_subject(topic)

    def _extract_json_blob(s: str) -> str:
        s = s.strip()
        start = s.find("{")
        end = s.rfind("}") + 1
        if start != -1 and end > start:
            return s[start:end]
        return s

    def _try_parse_scenario(raw_text: str) -> Scenario | None:
        # 1) direct parse
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass
        # 2) extract json object blob
        blob = _extract_json_blob(raw_text)
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return None

    context_parts = []
    if video_angle:
        context_parts.append(f"Suggested angle: {video_angle}")
    if why_trending:
        context_parts.append(f"Why it's trending: {why_trending}")
    if category:
        context_parts.append(f"Category: {category}")
    context = "\n".join(context_parts)

    user_msg = (
        f"Topic: {topic_subject}\n"
        f"Number of scenes: {num_scenes}\n"
        + (f"\nContext:\n{context}" if context else "")
        + (
            f"\n\nFACT_CONTEXT (per-scene evidence; use key_points for narration):\n"
            f"{json.dumps(fact_context, ensure_ascii=False)[:4500]}"
            if fact_context
            else ""
        )
    )

    messages = [
        SystemMessage(content=_WRITER_SYSTEM),
        HumanMessage(content=user_msg),
    ]

    logger.info(
        f"[ScenarioWriter] Writing scenario for: {topic_subject!r} ({num_scenes} scenes)"
    )
    response = llm.invoke(messages)
    raw = response.content.strip()
    logger.debug(f"[ScenarioWriter] Raw response length: {len(raw)} chars")

    # Strip markdown code fences if LLM wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    try:
        scenario: Scenario = json.loads(raw)
    except json.JSONDecodeError:
        scenario = _try_parse_scenario(raw)
        if scenario is None:
            # Last-resort repair: ask LLM to output ONLY valid JSON.
            logger.error(
                "[ScenarioWriter] JSON parse failed, trying repair. "
                f"Raw (first 300): {raw[:300]}"
            )
            repair_system = (
                "You are a JSON repair assistant. "
                "Return ONLY a valid JSON object matching this schema: "
                "{title, hook, outro, scenes:[{index,narration_text,subtitle_text,image_prompt}]}. "
                "No markdown, no code fences, no extra keys."
            )
            repair_messages = [
                SystemMessage(content=repair_system),
                HumanMessage(content=f"Broken response:\n{raw[:6000]}\n\nReturn corrected JSON only."),
            ]
            repair_resp = llm.invoke(repair_messages)
            repaired_raw = repair_resp.content.strip()
            scenario = _try_parse_scenario(repaired_raw)

            if scenario is None:
                logger.error(
                    "[ScenarioWriter] JSON repair failed. "
                    f"Repaired raw (first 300): {repaired_raw[:300]}"
                )
                raise ValueError("Could not parse scenario JSON even after repair")

    # Validate and fill defaults
    scenario.setdefault("title", topic_subject)
    scenario.setdefault("hook", "")
    scenario.setdefault("outro", "Подпишись — следующий факт сломает тебя ещё сильнее.")
    scenario.setdefault("scenes", [])

    scenario["hook"] = sanitize_voiceover_text(scenario.get("hook", ""))
    scenario["outro"] = sanitize_voiceover_text(scenario.get("outro", ""))
    scenario["title"] = sanitize_voiceover_text(scenario.get("title", ""))

    for i, scene in enumerate(scenario["scenes"]):
        scene.setdefault("index", i + 1)
        scene.setdefault("narration_text", scene.get("subtitle_text", ""))
        scene.setdefault("subtitle_text", scene.get("narration_text", "")[:40])
        scene["narration_text"] = sanitize_voiceover_text(scene["narration_text"])
        scene["subtitle_text"] = sanitize_voiceover_text(scene["subtitle_text"])
        if "vertical portrait orientation" not in scene.get("image_prompt", ""):
            scene["image_prompt"] = (
                scene.get("image_prompt", topic_subject) +
                ", vertical portrait orientation, 9:16 aspect ratio, subject centered, "
                "photorealistic, cinematic lighting, 4K"
            )

    logger.success(
        f"[ScenarioWriter] Done: {len(scenario['scenes'])} scenes | "
        f"hook: {scenario['hook'][:60]}..."
    )
    return scenario


# ── Public API ────────────────────────────────────────────────────────────────

async def run_scenario_writer_agent(
    topic: str,
    num_scenes: int = 5,
    trend_context: dict | None = None,
    fact_context: dict | None = None,
) -> Scenario:
    """
    Main entry point for the Scenario Writer Agent.

    Args:
        topic:          Video topic.
        num_scenes:     Number of scenes.
        trend_context:  Optional TrendingTopic dict from TrendsAgent.

    Returns:
        Full Scenario with hook, scenes, outro.
    """
    kwargs: dict = {}
    if trend_context:
        kwargs["video_angle"] = trend_context.get("video_angle")
        kwargs["why_trending"] = trend_context.get("why_trending")
        kwargs["category"] = trend_context.get("category")

    return await write_scenario(
        topic,
        num_scenes=num_scenes,
        fact_context=fact_context,
        **kwargs,
    )
