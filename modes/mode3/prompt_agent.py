"""
Mode 3 Prompt Agent — детальное описание дома и локации, промпты для фото и видео.

Два режима:
1) Из текстового описания — генерирует идеальные промпты для FastGen (дом ДО и ПОСЛЕ)
2) Из двух картинок — анализирует через vision LLM, генерирует 5 промптов для видео
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from modes.mode3.constants import NUM_RESTORATION_CLIPS
from modes.mode3.phase_templates import build_video_prompts
from utils.llm import make_llm

# Vision model for image analysis
VISION_MODEL = settings.openrouter_vision_model

# Text model for prompt generation (from topic)
TEXT_MODEL = settings.openrouter_model

_IMAGE_PROMPT_SYSTEM = """Ты — эксперт по архитектурной фотографии и фотореалистичной AI-генерации.

Ты получаешь ТИП ДОМА с локацией (напр. «Сруб у озера в Карелии — сосновый лес»). Дома сильно различаются: сруб ≠ викторианский ≠ вилла. Локации тоже: озеро ≠ прерия ≠ горы. Опиши КОНКРЕТНО этот тип и эту локацию.

## ЛОКАЦИЯ — ФИКСИРОВАНА (КРИТИЧНО):
- В ОБОИХ промптах (before и after) опиши ОДИН И ТОТ ЖЕ пейзаж: те же деревья/горы/воду/небо.
- Локация НЕ МЕНЯЕТСЯ от кадра к кадру: статичная камера, один пейзаж, один ракурс. Только дом ремонтируется — окружение остаётся.
- Красивые детали: отражение в воде, облака, тени от деревьев, дальний план. Добавь атмосферу, но всё это — постоянно.

## ПРАВИЛА ФОТОРЕАЛИЗМА (строго соблюдай):
- Добавляй естественные дефекты: пыль на подоконниках, паутина в углах, выгоревшая краска, трещины в штукатурке
- Текстуры: видимая структура дерева (слои, сучки), ржавчина на металле, мох между камнями, осыпающаяся облицовка
- Освещение: естественный свет, мягкие тени, никакого пересвета — как на реальном фото
- Избегай слов: perfect, ideal, flawless, stylized — используй: worn, aged, weathered, authentic
- В конце image prompt добавляй: shot on Canon EOS R5, 35mm lens, RAW photograph, 8K, no AI artifacts, lifelike, hyperrealistic

## РАЗМЕР И ПЛАНИРОВКА (ОБЯЗАТЕЛЬНО):
- Дом ВСЕГДА маленький, компактный (small, compact)
- Внутри ОДНА комната — студия, open plan, без перегородок

## image_prompt_before — дом ДО снаружи (ЭКСТРЕМАЛЬНО разрушен):
- SMALL compact house. wide shot, full building visible. Начни с ЛОКАЦИИ (пейзаж): forest / lake / mountains / prairie / coast
- МАКСИМАЛЬНОЕ разрушение: крыша провалена на 50%+, дыры, видны стропила
- Окна: выбиты, заколочены, пустые проёмы, битое стекло
- Стены: трещины, обвалившаяся штукатурка, плесень, мох
- Двери: сорваны или отсутствуют
- Окружение: заросший двор, бурьян, развалившийся забор
- severely demolished, half-collapsed roof, in ruins, crumbling, decades of neglect

## image_prompt_before_interior — интерьер ТОГО ЖЕ дома ДО (разрушен):
- Это внутренность дома из image_prompt_before. ТОТ ЖЕ дом — те же окна (видны изнутри), та же дверь. ONE room, studio, open plan.
- Обвалившиеся балки, мусор, пыль, руины. Планировка ФИКСИРОВАНА: одна комната, без перегородок.

## image_prompt_after — тот же дом ПОСЛЕ (детально, для финального показа):
- Тот же wide shot, тот же ракурс, ТА ЖЕ ЛОКАЦИЯ
- ПОДРОБНО опиши: крыша (форма, материал, цвет), стены (свежая краска/штукатурка), окна (стекло, рамы), дверь (отполированная), двор (чистый, без мусора), подоконники, карнизы, водостоки
- Каждая деталь видна, фотореалистично. Этот образ используется для финального фрагмента «готовый дом снаружи»

## ЗАМОРОЗКА АРХИТЕКТУРЫ (КРИТИЧНО — этажность и структура НИКОГДА не меняются):
В image_prompt_before ФИКСИРУЕШЬ и ПОВТОРЯЕШЬ в каждом video_prompt: число этажей (one-story / two-story / three-story), количество окон, положение двери.
В image_prompts 2–5: reference = последний кадр предыдущего видео. Первый кадр нового видео = ТОЧНО этот reference. Структура здания в reference задана — не меняй этажность, окна, дверь. Только ремонт и улучшение.

## location_description (ОБЯЗАТЕЛЬНО — единый «паспорт» дома для ВСЕХ 5 клипов):
Одно детальное описание, которое повторяется везде. ВСЕГДА: small one-story compact house. ВКЛЮЧИ: тип крыши (gable/hipped), материал стен, количество окон и их расположение, позиция двери. Напр: «small one-story wooden house, gable roof, 2 windows left of door, 1 window right, door centered, timber walls». Этот дом ОДИН И ТОТ ЖЕ во всех кадрах видео.

## video_prompts — НЕ ГЕНЕРИРУЙ. Верни пустой массив [].
video_prompts будут собраны автоматически из location_description.

Формат: ТОЛЬКО JSON:
{"image_prompt_before": "...", "image_prompt_before_interior": "...", "image_prompt_after": "...", "image_prompt_mid_exterior": "...", "image_prompt_mid_interior": "...", "image_prompt_after_interior": "...", "location_description": "...", "video_prompts": []}

image_prompt_before, before_interior, after — 150–250 слов. mid_exterior, mid_interior, after_interior — 80–120 слов (img2img prompts)."""


def _parse_json_response(text: str, required_keys: tuple) -> dict:
    """Parse LLM JSON response, strip markdown if needed."""
    raw = text.strip()
    for pattern in (r"```(?:json)?\s*(.*?)\s*```", r"(\{[\s\S]*\})"):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            break
    data = json.loads(raw)
    for k in required_keys:
        if k not in data:
            raise ValueError(f"Prompt agent missing key: {k}")
    return data


async def run_image_prompt_agent(house_type: str) -> dict:
    """
    По типу дома генерирует максимально детальные промпты для фотореалистичной генерации.

    house_type: короткая метка типа, напр. «Деревянный сруб в лесу», «Кирпичный дом у реки».

    Returns:
        {
            "image_prompt_before": str,
            "image_prompt_after": str,
            "video_prompts": [str, ...]
        }
    """
    llm = make_llm(temperature=0.3, model=TEXT_MODEL)
    msg = HumanMessage(content=(
        f"Тип дома и локация: {house_type!r}\n\n"
        "Опиши КОНКРЕТНО этот тип и красивую локацию. "
        "image_prompt_before: дом разрушен снаружи (text2img). "
        "image_prompt_before_interior: интерьер разрушен (text2img). "
        "image_prompt_after: дом полностью восстановлен снаружи (финал). "
        "image_prompt_mid_exterior: для img2img — частичный ремонт (крыша, стены, без окон). "
        "image_prompt_mid_interior: для img2img — частичный ремонт внутри. "
        "image_prompt_after_interior: для img2img — интерьер полностью восстановлен. "
        "location_description: этажность, ТИП КРЫШИ, окна, дверь. video_prompts: []. Верни ТОЛЬКО JSON."
    ))
    resp = await llm.ainvoke([SystemMessage(content=_IMAGE_PROMPT_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)

    required = ("image_prompt_before", "image_prompt_before_interior", "image_prompt_after",
                "image_prompt_mid_exterior", "image_prompt_mid_interior", "image_prompt_after_interior",
                "location_description", "video_prompts")
    data = _parse_json_response(text, required)

    loc = (data.get("location_description") or "").strip() or "same building, same floors, same windows"
    data["video_prompts"] = build_video_prompts(loc)

    suffix = ", vertical 9:16 portrait, shot on Canon EOS R5, 8K photograph, no AI artifacts, hyperrealistic, lifelike"
    img2img_suffix = ", 9:16 portrait, photorealistic, same building"
    for key in ("image_prompt_before", "image_prompt_before_interior", "image_prompt_after"):
        if suffix.lower() not in (data[key] or "").lower():
            data[key] = (data[key] or "").rstrip(" .,") + suffix
    for key in ("image_prompt_mid_exterior", "image_prompt_mid_interior", "image_prompt_after_interior"):
        if (data.get(key) or "").strip() and img2img_suffix.lower() not in (data[key] or "").lower():
            data[key] = (data[key] or "").rstrip(" .,") + img2img_suffix

    logger.success(f"[Mode3 Image Prompt] Generated prompts for: {house_type[:50]}...")
    return data


def _image_to_base64_url(path: str | Path) -> str:
    """Encode image to data URL for vision API."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    data = p.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    ext = p.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"


_SYSTEM = """Ты — эксперт по описанию зданий для AI-генерации видео.

Проанализируй две фотографии: ДО реставрации и ПОСЛЕ. Создай:

1) **location_description** — small compact house, one-story, ONE room (studio layout). ТИП КРЫШИ (gable/hipped), окна, дверь.

2) **photo_prompts** — start (дом ДО снаружи), end (дом ПОСЛЕ). Локация одинаковая.

3) **image_prompt_before_interior** — ONE room, studio layout, ruined: балки, мусор, пыль. Small compact room. На английском.

4) **video_prompts** — верни пустой массив []."""


async def run_prompt_agent(
    start_image_path: str | Path,
    end_image_path: str | Path,
) -> dict:
    """
    Анализирует две картинки и возвращает промпты для генерации.

    Returns:
        {
            "location_description": str,
            "photo_prompts": {"start": str, "end": str},
            "video_prompts": [str, ...]  # 3 этапа
        }
    """
    start_url = _image_to_base64_url(start_image_path)
    end_url = _image_to_base64_url(end_image_path)

    llm = make_llm(temperature=0.3, model=VISION_MODEL)

    msg = HumanMessage(content=[
        {"type": "text", "text": (
            "Проанализируй две фотографии: ДО и ПОСЛЕ реставрации. Обе — ОДИН И ТОТ ЖЕ дом.\n"
            "Фото ДО — разрушенный снаружи. image_prompt_before_interior: опиши интерьер ДО (руины внутри) на английском.\n"
            "video_prompts: []. Верни ТОЛЬКО JSON:\n"
            '{"location_description": "...", "photo_prompts": {"start": "...", "end": "..."}, "image_prompt_before_interior": "ruined interior...", "video_prompts": []}'
        )},
        {"type": "image_url", "image_url": {"url": start_url}},
        {"type": "text", "text": "--- Вторая картинка (ПОСЛЕ реставрации):"},
        {"type": "image_url", "image_url": {"url": end_url}},
    ])

    messages = [SystemMessage(content=_SYSTEM), msg]
    resp = await llm.ainvoke(messages)
    text = resp.content if hasattr(resp, "content") else str(resp)

    # Parse JSON (strip markdown fences if present)
    raw = text.strip()
    for pattern in (r"```(?:json)?\s*(.*?)\s*```", r"(\{[\s\S]*\})"):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            break

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[Mode3 Prompt] JSON parse error: {e}\nRaw: {raw[:500]}")
        raise ValueError(f"Prompt agent returned invalid JSON: {e}")

    required = ("location_description", "photo_prompts", "image_prompt_before_interior", "video_prompts")
    for k in required:
        if k not in data:
            raise ValueError(f"Prompt agent missing key: {k}")

    loc = (data.get("location_description") or "").strip() or "same building, same floors, same windows"
    data["video_prompts"] = build_video_prompts(loc)

    logger.success(f"[Mode3 Prompt] Built {NUM_RESTORATION_CLIPS} prompts from templates, location: {loc[:80]}...")
    return data
