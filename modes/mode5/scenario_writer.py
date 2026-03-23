"""
Mode 5 Scenario Writer — длинный сценарий (~1 час) для образовательного/документального видео.

Структура: блоки (абзацы). Для каждого блока с логической сменой визуала — image_prompt.
Озвучка — на русском или английском. Субтитров нет.
"""

from __future__ import annotations

import json
import re
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm

# Целевая длина: ~1 час озвучки. 150 слов/мин ≈ 9000 слов. Сегмент ~120–180 слов (45–90 сек).
# Итого: ~50–75 сегментов. Смена картинки: каждые 3–7 сегментов (новая сцена/концепция).
_TARGET_WORDS = 8500  # чуть меньше часа
_MIN_SEGMENTS = 40
_MAX_SEGMENTS = 80


class LongFormSegment(TypedDict):
    index: int
    narration_text: str  # текст для озвучки
    image_prompt: str | None  # если не None — сгенерировать новое изображение для этого блока


class LongFormScenario(TypedDict):
    title: str
    segments: list[LongFormSegment]


def _long_form_system(language: str) -> str:
    lang_note = "Russian" if language.lower() == "ru" else "English"
    return f"""You are an EXPERT documentary scriptwriter for "history for sleep" format.
Your task: write a HIGH-QUALITY script for a ~6 HOUR voiceover video (target ~54000 words) on the given topic.
Narration language: {lang_note}.

═══ СТРУКТУРА: ГЛАВЫ И ЦЕЛОСТНОСТЬ ═══
• Организуй сценарий в ЦЕЛОСТНУЮ СТРУКТУРУ из 18–22 связанных ГЛАВ.
• Каждая глава = логический блок с чёткой темой, 15–25 сегментов внутри.
• Главы должны плавно переходить друг в друга: конец одной → завязка следующей.
• Хронология (если применимо): соблюдай порядок событий, не перескакивай.
• Никаких «мы вернёмся к этому позже» — всё должно идти последовательно и связно.

═══ ИСТОРИЧЕСКАЯ ТОЧНОСТЬ (КРИТИЧНО для истории, биографий, событий) ═══
• НИЧЕГО НЕ ВЫДУМЫВАЙ. Только проверяемые исторические факты.
• Не выдумывай даты, имена, цитаты, детали событий.
• Если факт спорен — формулируй осторожно: «по данным источников», «историки полагают», «согласно древним хроникам».
• Избегай мифов и популярных заблуждений. Приоритет: достоверность.
• Даты, имена, цифры — только те, что можно проверить. Если не уверен — опусти или укажи «около», «приблизительно».

═══ ФОРМАТ ВЫВОДА ═══
Разбивай на SEGMENTS. Каждый сегмент = 2–4 абзаца (150–200 слов).
image_prompt — при смене визуала: новая сцена/локация, смена эпохи, новый персонаж.
Новое изображение каждые 4–6 сегментов (≈60–80 image points для 6-часового видео).

Output JSON:
{{
  "title": "Video title",
  "segments": [
    {{
      "index": 1,
      "narration_text": "Full paragraph(s) to be read aloud...",
      "image_prompt": "English prompt for image" // or null to reuse previous
    }},
    ...
  ]
}}

IMAGE PROMPT (image-gen-expert): [Subject] + [Style] + [Lighting] + [Composition]. Be specific. Add "horizontal 16:9 landscape, 4K photorealistic".

NARRATION: Plain text only (no HTML, Markdown, URLs). Documentary tone. Each segment ends with a complete sentence.
"""


async def run_long_form_scenario_writer(
    topic: str,
    language: str = "ru",
    use_multi_agent: bool = True,
    control: dict | None = None,
) -> LongFormScenario:
    """Генерирует длинный сценарий с сегментами и точками смены изображений.

    use_multi_agent: если True (по умолчанию) — мультиагентная цепочка LangGraph:
        StructureAgent → ContentAgent (на каждую подглаву) → CoherenceAgent
    """
    if use_multi_agent:
        try:
            from modes.mode5.multi_agent_scenario import run_multi_agent_scenario
            result = await run_multi_agent_scenario(topic=topic, language=language, control=control)
            seg_count = len(result.get("segments", []))
            if seg_count < 40:
                logger.warning(f"[Mode5] Multi-agent produced only {seg_count} segments (target 50-75). Consider re-running.")
            return result
        except Exception as e:
            logger.warning(f"[Mode5] Multi-agent failed, fallback to single LLM: {e}")
    llm = make_llm()
    lang_instruction = "Write narration in Russian." if language.lower() == "ru" else "Write narration in English."
    system = _long_form_system(language)

    msg = HumanMessage(
        content=f"Write a HIGH-QUALITY ~1 hour long-form video script on the topic:\n\n{topic}\n\n"
        f"{lang_instruction}\n\n"
        f"СТРУКТУРА: Разбей на 8–15 связанных глав с целостным повествованием. "
        f"Каждая глава — логический блок, сегменты внутри главы плавно переходят друг в друга.\n\n"
        f"ИСТОРИЧЕСКАЯ ТОЧНОСТЬ: Если тема связана с историей, событиями, биографиями — "
        f"НИЧЕГО НЕ ВЫДУМЫВАЙ. Только проверяемые факты. Спорное — формулируй осторожно.\n\n"
        f"Output valid JSON: 'title', 'segments'. MINIMUM 50 segments for 1-hour video (target 55–75). "
        f"First segment MUST have image_prompt. New image every 4–6 segments (each new chapter = new image)."
    )

    response = await llm.ainvoke([SystemMessage(content=system), msg])
    text = response.content if hasattr(response, "content") else str(response)
    text = text.strip()

    # Extract JSON from possible markdown
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"[Mode5] JSON parse error: {e}\nRaw: {text[:500]}...")
        raise ValueError(f"Failed to parse scenario JSON: {e}")

    title = data.get("title") or topic
    segments_raw = data.get("segments") or []

    segments: list[LongFormSegment] = []
    for i, s in enumerate(segments_raw):
        if isinstance(s, dict):
            narration = (s.get("narration_text") or s.get("text") or "").strip()
            if not narration:
                continue
            img_prompt = s.get("image_prompt")
            if img_prompt is not None:
                img_prompt = str(img_prompt).strip() or None
            segments.append({
                "index": len(segments) + 1,
                "narration_text": narration,
                "image_prompt": img_prompt,
            })

    if not segments:
        raise ValueError("Scenario has no valid segments")

    # Ensure first segment has image
    if not segments[0].get("image_prompt"):
        segments[0]["image_prompt"] = (
            f"Documentary style illustration of {topic}, "
            "cinematic lighting, horizontal 16:9 landscape, 4K photorealistic"
        )

    logger.success(f"[Mode5] Scenario: {len(segments)} segments, "
                  f"{sum(1 for s in segments if s.get('image_prompt'))} image points")
    return {"title": title, "segments": segments}
