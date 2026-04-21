"""
Mode 6 Prompt Agent — генерирует кинематографичный промпт для расслабляющего видео.

Категории: дождь, огонь, океан, лес, звёзды, кофейня, снегопад, ручей, закат...
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm

_SYSTEM = """Ты эксперт по визуальному контенту для релаксации и ASMR.

Генерируешь ОДИН детальный промпт для AI video-to-video (Veo, Runway, fast-gen.ai).

Правила:
- Только визуал: без людей, без текста, без озвучки (звук будет от FastGen или тишина)
- Медленное, плавное движение камеры (subtle pan, slight zoom, gentle motion)
- Расслабляющая атмосфера: мягкий свет, спокойные цвета
- Детали: материалы (вода, огонь, листва), освещение, текстуры
- Формат: 9:16 portrait, cinematic, 4K, photorealistic

Верни ТОЛЬКО JSON:
{
  "video_prompt": "детальный промпт 80–150 слов на английском"
}
"""

RELAX_PRESETS: dict[str, str] = {
    "rain": "Дождь за окном — капли на стекле, размытый город/сад",
    "fireplace": "Горящий камин — пламя, тёплый свет, уют",
    "ocean": "Океанские волны — закат или рассвет, песок, спокойное море",
    "forest": "Лес — тропинка, солнечные лучи сквозь листву, птицы",
    "stars": "Звёздное небо — Млечный путь, тихая ночь",
    "cafe": "Кофейня — пар от чашки, уютный интерьер, дождь за окном",
    "aquarium": "Аквариум — рыбки, пузырьки, подводный свет",
    "snowfall": "Снегопад — тихий вечер, фонари, пушистый снег",
    "creek": "Лесной ручей — журчащая вода, камни, мох",
    "sunset": "Закат над водой или полем — золотой час, облака",
    "waves": "Волны на берегу — пенка, камни, расслабляющий ритм",
    "storm": "Гроза за окном — молнии, дождь, безопасный уют внутри",
}


async def run_relax_prompt_agent(
    category_id: str,
    custom_description: str | None = None,
) -> dict[str, Any]:
    """
    Генерирует промпт для расслабляющего видео.

    Args:
        category_id: id из RELAX_PRESETS (rain, fireplace, ocean...) или "custom"
        custom_description: пользовательское описание (если category_id == "custom")

    Returns:
        {"video_prompt": str}
    """
    if category_id == "custom" and custom_description and custom_description.strip():
        user_input = custom_description.strip()
    else:
        user_input = RELAX_PRESETS.get(category_id, RELAX_PRESETS["rain"])

    llm = make_llm(temperature=0.5, model=settings.openrouter_model)
    msg = HumanMessage(
        content=f"Создай расслабляющее видео. Тема: {user_input}\n\nВерни ТОЛЬКО JSON с video_prompt."
    )

    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)

    from utils.json_parse import parse_json_safe
    data = parse_json_safe(text)
    prompt = (data.get("video_prompt") or "").strip()
    if not prompt:
        raise ValueError("Prompt agent returned empty video_prompt")

    # Добавляем технические параметры
    suffix = ", 9:16 portrait, cinematic 4K, photorealistic, slow motion, calming atmosphere, no people, no text"
    if not prompt.lower().endswith(("portrait", "9:16")):
        prompt = prompt.rstrip(" .,") + suffix

    logger.success(f"[Mode6 Prompt] Generated relax prompt: {prompt[:60]}...")
    return {"video_prompt": prompt}
