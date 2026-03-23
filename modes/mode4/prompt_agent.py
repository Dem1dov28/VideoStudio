"""
Mode 4 Prompt Agent — на основе фото личности и цитаты генерирует:
- video_prompt: кинематографичный промпт для генерации видео (в стиле Достоевского)
- voice_description: описание голоса (для справки)
- script_ru: цитата на русском (для субтитров)
- script_en: перевод цитаты на английский (если bilingual)
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm

VISION_MODEL = settings.openrouter_vision_model

_SYSTEM = """Ты — эксперт по кинематографичной AI-генерации и исторической достоверности.

По фото личности, её имени и цитате создаёшь ДЕТАЛЬНЫЙ промпт для video-to-video генерации (Veo, Runway, fast-gen.ai).

## ИСТОРИЧЕСКАЯ ТОЧНОСТЬ (критично):
- Определи эпоху персонажа по имени (античность, средневековье, XIX век, и т.д.)
- Всё в промпте должно соответствовать эпохе: одежда, архитектура, предметы, освещение, материалы
- Никаких анахронизмов: например, философ Древнего Рима — тога, мрамор, масляные светильники; писатель XIX века — сюртук, газовые фонари, гранитная набережная

## ДЕТАЛЬНОСТЬ video_prompt (150–250 слов):
Пиши развёрнуто, на английском. Структура:

1. ПЕРСОНАЖ (подробно): внешность, возраст, тип лица, волосы, борода; одежда — материал, цвет, детали кроя; поза, осанка; выражение лица — взгляд, складки, характер.
2. ОКРУЖЕНИЕ (подробно): точная локация (сад, кабинет, набережная), архитектура эпохи, материалы (мрамор, дерево, камень); предметы вокруг (скамья, книги, колонны); природа — деревья, небо, время суток.
3. ОСВЕЩЕНИЕ И АТМОСФЕРА: время дня, тип света (закат, газовые фонари, свечи), тени, воздух, настроение.
4. ДВИЖЕНИЕ: walks slowly, stops, turns, faces the camera.
5. РЕЧЬ: He begins speaking in [Russian/English], his voice [детальное описание тембра], saying: "[точная цитата]". Expression: [глубокое описание].
6. Технические: wide-to-medium shot, Cinematic quality, photorealistic, 8K, vertical 9:16 portrait, shallow depth of field.

Имя в промпте НЕ писать. Описывать по роли и внешности («philosopher in a Roman garden», «Russian writer on an embankment»).

Верни ТОЛЬКО JSON:
{
  "video_prompt": "подробный промпт 150–250 слов",
  "video_prompt_ru": "промпт с 'speaking in Russian' (только если bilingual)",
  "video_prompt_en": "промпт с 'speaking in English' (только если bilingual)",
  "voice_description": "...",
  "script_ru": "цитата дословно",
  "script_en": "перевод (если bilingual ИЛИ subtitle_lang=en)",
  "detected_lang": "ru|en|de|fr|es|... (если auto_detect — ISO 639-1 код языка цитаты)"
}
При auto_detect: определи язык цитаты, верни detected_lang. Субтитры = цитата как есть. script_ru/script_en — устаревшие при auto_detect."""


def _image_to_base64_url(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    data = p.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    ext = p.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"


def _parse_json_response(text: str) -> dict:
    raw = text.strip()
    for pattern in (r"```(?:json)?\s*(.*?)\s*```", r"(\{[\s\S]*\})"):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            break
    return json.loads(raw)


async def run_quote_prompt_agent(
    photo_path: str | Path,
    quote: str,
    person_name: str = "",
    bilingual: bool = False,
    subtitle_lang: str = "ru",
    auto_detect_lang: bool = False,
) -> dict:
    """
    Анализирует фото личности и цитату, возвращает промпты для видео.

    Args:
        photo_path: путь к фото личности
        quote: цитата (на любом языке при auto_detect_lang)
        person_name: имя личности (для контекста, в промпт не включать!)
        bilingual: если True — 2 фрагмента (RU + EN)
        subtitle_lang: "ru" | "en" — язык субтитров при одном фрагменте
        auto_detect_lang: если True — определить язык цитаты, субтитры = цитата как есть

    Returns:
        {
            "video_prompt": str,
            "voice_description": str,
            "script_ru": str,
            "script_en": str,
            "detected_lang": str  # при auto_detect_lang: ru, en, de, fr и т.д.
        }
    """
    img_url = _image_to_base64_url(photo_path)
    llm = make_llm(temperature=0.3, model=VISION_MODEL)

    auto_hint = (
        "\n\nauto_detect_lang: True — ОПРЕДЕЛИ язык цитаты (ru, en, de, fr, es, it, pl, ...). "
        "Верни detected_lang. video_prompt: укажи 'speaking in [Language]' по определённому языку. "
        "Субтитры = цитата без изменений."
    ) if auto_detect_lang else ""

    msg = HumanMessage(content=[
        {"type": "text", "text": (
            f"Имя личности (НЕ писать в промпте! Используй для эпохи и исторической точности): {person_name}\n\n"
            f"Цитата (вставить в video_prompt в кавычках): {quote}\n\n"
            f"bilingual: {bilingual}\n"
            f"subtitle_lang: {subtitle_lang}\n"
            f"auto_detect_lang: {auto_detect_lang}\n"
            "video_prompt: 150–250 слов. ДЕТАЛЬНО опиши персонажа (внешность, одежда эпохи, выражение), "
            "окружение (архитектура, предметы, природа — всё соответствующие эпохе), освещение, атмосферу. "
            "Проверь историческую точность: одежда, материалы, технологии должны соответствовать эпохе персонажа. "
            "Цитату в кавычках."
            + auto_hint +
            " Верни ТОЛЬКО JSON."
        )},
        {"type": "image_url", "image_url": {"url": img_url}},
    ])

    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)
    data = _parse_json_response(text)

    if "video_prompt" not in data:
        raise ValueError("Prompt agent missing video_prompt")
    data.setdefault("script_ru", quote)
    data.setdefault("script_en", "")
    data.setdefault("voice_description", "")
    data.setdefault("detected_lang", "")

    if auto_detect_lang:
        # Субтитры = цитата как есть (в языке ввода)
        det = (data.get("detected_lang") or "en").strip().lower()[:2]
        if det == "ru":
            data["script_ru"], data["script_en"] = quote, ""
            data["detected_lang"] = "ru"
        else:
            # en, de, fr, es, it... — используем script_en
            data["script_ru"], data["script_en"] = "", quote
            data["detected_lang"] = "en"
    else:
        if not data.get("script_ru"):
            data["script_ru"] = quote
        if not data.get("script_en") and bilingual:
            data["script_en"] = quote  # fallback if no translation
        elif subtitle_lang == "en" and not data.get("script_en"):
            data["script_en"] = data.get("script_ru", quote)

    if bilingual:
        if not data.get("video_prompt_ru") and data.get("video_prompt"):
            data["video_prompt_ru"] = data["video_prompt"].replace("English", "Russian")
        if not data.get("video_prompt_en") and data.get("video_prompt"):
            data["video_prompt_en"] = data["video_prompt"].replace("Russian", "English")

    logger.success(f"[Mode4 Prompt] Generated video prompt for quote ({len(quote)} chars)")
    return data
