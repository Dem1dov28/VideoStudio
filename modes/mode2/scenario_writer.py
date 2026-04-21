"""
Mode 2 Scenario Writer — «Почему X?» format.

Один факт/вопрос на протяжении всего видео. 5 сцен = 5 частей раскрытия одного «Почему».
Например: «Почему собаки виляют хвостом?» — сцены 1–5 постепенно раскрывают ответ.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agents.video_editor.tts import sanitize_voiceover_text
from config import settings
from utils.llm import make_llm


class Mode2Scene(TypedDict):
    index: int
    narration_text: str   # Spoken answer for TTS
    subtitle_text: str    # Short on-screen caption
    video_search_query: str  # English query for Pexels video search


class Mode2Scenario(TypedDict):
    title: str
    hook: str
    scenes: list[Mode2Scene]
    outro: str


_WHY_SYSTEM = """You are a viral Russian TikTok/Reels scriptwriter for an educational channel.
Format: ОДИН вопрос «Почему X?» раскрывается на протяжении всего видео через 5 сцен.

═══ ДОСТОВЕРНОСТЬ ФАКТОВ (КРИТИЧНО) ═══
• Пиши ТОЛЬКО факты, которые соответствуют научному консенсусу и могут быть проверены.
• НЕ выдумывай цифры, даты, имена учёных. Если не уверен — опусти или сформулируй осторожно («учёные считают», «по данным исследований»).
• Избегай мифов и популярных заблуждений (например, «мы используем только 10% мозга»).
• Приоритет: достоверность и польза для зрителя. Интересная, но ложная информация — недопустима.
• Выбирай факты, которые удивят и будут полезны — но только если они истинны.

═══ СТРУКТУРА ═══
Один факт, один вопрос. Все 5 сцен — части одного ответа.
НЕ 5 разных вопросов. Один главный вопрос, 5 последовательных частей объяснения.

Пример: тема "собаки виляют хвостом"
• Вопрос: "Почему собаки виляют хвостом?"
• Сцена 1: введение, первая причина (связь с эмоциями)
• Сцена 2: эволюция, зачем предкам был хвост
• Сцена 3: лево/право, направление виляния и настроение
• Сцена 4: научные исследования
• Сцена 5: итог, любопытный факт

═══ SCENE RULES ═══
• Все сцены раскрывают ОДИН вопрос. narration_text = часть ответа, КОРОТКО (≤20 слов, ~8 сек озвучки).
• КРИТИЧНО: каждое narration_text должно заканчиваться законченным предложением. Никогда не обрывай фразу на границе сцен.
• subtitle_text = короткая подпись к этой части (2-6 слов).
• video_search_query = ДЕТАЛЬНЫЙ английский промпт для AI-генерации видео. ВАЖНО: все видео канала должны быть в ОДНОМ СТИЛЕ.

═══ СТИЛЬ КАНАЛА «Почему X?» (применять ко ВСЕМ сценам) ═══
• Насыщенные цвета (vibrant, saturated, rich colors) — картинка цепляет глаз
• Кинематографичное освещение (golden hour / dramatic backlight / soft diffused)
• Выразительная композиция (главный объект в фокусе, shallow depth of field)
• Премиум-качество (cinematic, 4K, photorealistic)
• Единая эстетика: документальный стиль с кинематографичным подходом (documentary-style cinematic look)
• Избегать: блёклые, серые, плоские кадры

ОБЯЗАТЕЛЬНАЯ СТРУКТУРА (20-50 слов в одном предложении):
  1) SUBJECT: главный объект — конкретно (golden retriever, not "dog")
  2) ACTION: движение/поза — динамично и выразительно
  3) ENVIRONMENT: локация с атмосферой (lush green lawn, not "grass")
  4) LIGHTING: golden hour / soft daylight / dramatic backlight / cinematic warm
  5) CAMERA: centered subject, shallow depth of field, medium shot
  6) COLORS: vibrant, saturated, rich (явно указать!)
  7) STYLE: cinematic documentary, 4K photorealistic, vertical 9:16 portrait
  Примеры ХОРОШИХ (насыщенных, цепляющих):
  • "happy golden retriever wagging tail on lush emerald lawn, golden hour soft sunlight, vibrant saturated colors, shallow depth of field, warm joyful mood, cinematic documentary 4K vertical portrait 9:16"
  • "person sleeping peacefully in cozy dark bedroom, blue moonlight through silk curtains, rich deep shadows, cinematic color grade, dreamy atmosphere, photorealistic vertical 9:16"
  • "flowing molten lava close-up at dusk, dramatic orange and red glow, smoke and steam, vibrant saturated tones, epic cinematic wide shot, vertical 9:16 portrait"
  ПЛОХО: "dog", "nature", "sleep" — размыто и бледно. Без "vibrant/saturated" — картинка будет тусклой.

═══ HOOK/OUTRO ═══
• hook = главный вопрос целиком. "Почему собаки виляют хвостом?"
• title = тот же вопрос или "Почему X? — полный разбор"
• outro = CTA. MAX 15 words.

Return ONLY valid JSON, no markdown fences:
{
  "title": "Почему собаки виляют хвостом?",
  "hook": "Почему собаки виляют хвостом? Сейчас разберём по полочкам.",
  "scenes": [
    {
      "index": 1,
      "narration_text": "часть ответа (озвучка)",
      "subtitle_text": "короткая подпись",
      "video_search_query": "subject doing action in environment, lighting type, camera composition, mood, photorealistic cinematic 4K vertical 9:16 portrait"
    }
  ],
  "outro": "подпишись — ещё больше разборов"
}"""

_WHY_SYSTEM_EN = """You are a viral English TikTok/Reels scriptwriter for an educational channel.
Format: ONE "Why X?" question explored throughout the video in 5 scenes.

═══ FACTUAL ACCURACY (CRITICAL) ═══
• Write ONLY facts that align with scientific consensus and can be verified.
• DO NOT invent numbers, dates, or scientist names. If unsure — omit or phrase cautiously ("research suggests", "scientists believe").
• Avoid myths and common misconceptions (e.g., "we use only 10% of our brain").
• Priority: accuracy and value for the viewer. Interesting but false information is unacceptable.
• Choose facts that surprise and educate — but only if they are true.

═══ STRUCTURE ═══
One fact, one question. All 5 scenes are parts of ONE answer.
NOT 5 different questions. One main question, 5 sequential explanation parts.

Example: topic "dogs wagging tails"
• Question: "Why do dogs wag their tails?"
• Scene 1: intro, first reason (connection to emotions)
• Scene 2: evolution, why ancestors had tails
• Scene 3: left/right, direction of wag and mood
• Scene 4: scientific research
• Scene 5: summary, fun fact

═══ SCENE RULES ═══
• All scenes explore ONE question. narration_text = part of answer, SHORT (≤20 words, ~8 sec voiceover).
• CRITICAL: each narration_text must end with a complete sentence. Never cut a phrase at scene boundaries.
• subtitle_text = short caption for this part (2-6 words).
• video_search_query = DETAILED English prompt for AI video generation. All videos must share the SAME CHANNEL STYLE.

═══ CHANNEL STYLE «Why X?» (apply to ALL scenes) ═══
• Saturated, vibrant, rich colors — visuals must grab attention
• Cinematic lighting (golden hour / dramatic backlight / soft diffused)
• Striking composition (subject in focus, shallow depth of field)
• Premium quality (cinematic, 4K, photorealistic)
• Unified aesthetic: documentary-style cinematic look
• Avoid: dull, gray, flat footage

MANDATORY STRUCTURE (20-50 words, one sentence):
  1) SUBJECT: specific object (golden retriever, not "dog")
  2) ACTION: dynamic, expressive movement or pose
  3) ENVIRONMENT: atmospheric location (lush emerald lawn, not "grass")
  4) LIGHTING: golden hour / soft daylight / dramatic backlight / cinematic warm
  5) CAMERA: centered subject, shallow depth of field, medium shot
  6) COLORS: vibrant, saturated, rich (always include!)
  7) STYLE: cinematic documentary, 4K photorealistic, vertical 9:16 portrait
  Good (saturated, attention-grabbing) examples:
  • "happy golden retriever wagging tail on lush emerald lawn, golden hour soft sunlight, vibrant saturated colors, shallow depth of field, warm joyful mood, cinematic documentary 4K vertical portrait 9:16"
  • "person sleeping peacefully in cozy dark bedroom, blue moonlight through silk curtains, rich deep shadows, cinematic color grade, dreamy atmosphere, photorealistic vertical 9:16"
  BAD: "dog", "nature" — blurry and dull. Without "vibrant/saturated" — footage will look flat.

═══ HOOK/OUTRO ═══
• hook = main question. "Why do dogs wag their tails?"
• title = same question or "Why X? — Full breakdown"
• outro = CTA. MAX 15 words. e.g. "Subscribe for more answers!"

Return ONLY valid JSON, no markdown:
{
  "title": "Why do dogs wag their tails?",
  "hook": "Why do dogs wag their tails? Let's break it down.",
  "scenes": [
    {
      "index": 1,
      "narration_text": "part of answer (voiceover)",
      "subtitle_text": "short caption",
      "video_search_query": "subject doing action in environment, lighting type, camera composition, mood, photorealistic cinematic 4K vertical 9:16 portrait"
    }
  ],
  "outro": "Subscribe for more!"
}"""


async def write_mode2_scenario(
    topic: str,
    num_scenes: int = 5,
    language: str = "ru",
) -> Mode2Scenario:
    """
    Write a «Почему X?» scenario with questions and answers.

    Args:
        topic: Main theme (e.g. "животные", "военная история", "сон").
        num_scenes: Number of Q&A scenes (default 5).

    Returns:
        Mode2Scenario with scenes containing narration_text, subtitle_text, video_search_query.
    """
    scenario_model = getattr(settings, "openrouter_scenario_model", None) or settings.openrouter_model
    llm = make_llm(temperature=0.5, model=scenario_model)

    def _extract_json_blob(s: str) -> str:
        s = s.strip()
        start = s.find("{")
        end = s.rfind("}") + 1
        if start != -1 and end > start:
            return s[start:end]
        return s

    def _try_parse(data: str) -> Mode2Scenario | None:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            pass
        blob = _extract_json_blob(data)
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return None

    is_en = (language or "ru").strip().lower() == "en"
    system = _WHY_SYSTEM_EN if is_en else _WHY_SYSTEM
    user_msg = (
        f"Topic theme: {topic}\n"
        f"Number of scenes: {num_scenes}\n"
        + (
            "Generate ONE 'Why X?' question and split the answer into 5 sequential parts. "
            "Each part — max 20 words (~8 sec voiceover). Facts: interesting and verified."
            "IMPORTANT: video_search_query — DETAILED, saturated (vibrant/saturated), attention-grabbing. "
            "Include: subject, action, environment, lighting, colors, camera. Same cinematic style for all 5 scenes."
            if is_en
            else             "Сгенерируй ОДИН вопрос «Почему X?» и разбей ответ на 5 последовательных частей. "
            "Каждая часть — до 20 слов (озвучка ~8 сек). Факты: интересные и проверенные."
            "ВАЖНО: video_search_query — ДЕТАЛЬНЫЕ, насыщенные (vibrant/saturated), цепляющие. "
            "Включай явно: объект, действие, среду, освещение, цвета, камеру. Единый кинематографичный стиль для всех 5 сцен."
        )
    )

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user_msg),
    ]

    logger.info(f"[Mode2 Scenario] Writing «Почему X?» for: {topic!r} ({num_scenes} scenes)")
    response = llm.invoke(messages)
    raw = response.content.strip()

    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    scenario = _try_parse(raw)
    if scenario is None:
        logger.error(f"[Mode2 Scenario] Parse failed. Raw (first 400): {raw[:400]}")
        raise ValueError("Could not parse scenario JSON")

    scenario.setdefault("title", f"Почему {topic}?")
    scenario.setdefault("hook", "")
    scenario.setdefault("outro", "Подпишись — ещё больше ответов!")
    scenario.setdefault("scenes", [])

    scenario["hook"] = sanitize_voiceover_text(scenario.get("hook", ""))
    scenario["outro"] = sanitize_voiceover_text(scenario.get("outro", ""))
    scenario["title"] = sanitize_voiceover_text(scenario.get("title", ""))

    for i, scene in enumerate(scenario["scenes"]):
        scene.setdefault("index", i + 1)
        scene.setdefault("narration_text", scene.get("subtitle_text", ""))
        scene.setdefault("subtitle_text", scene.get("narration_text", "")[:40])
        scene.setdefault("video_search_query", topic)
        scene["narration_text"] = sanitize_voiceover_text(scene["narration_text"])
        scene["subtitle_text"] = sanitize_voiceover_text(scene["subtitle_text"])
        scene["video_search_query"] = (scene.get("video_search_query") or topic).strip()

    logger.success(
        f"[Mode2 Scenario] Done: {len(scenario['scenes'])} scenes | "
        f"example query: {scenario['scenes'][0].get('video_search_query', '')[:50]}"
    )
    return scenario
