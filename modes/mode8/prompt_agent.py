"""
Mode 8 — по тексту пользователя: blueprint + промпты «до» / «после» для FastGen (как Mode 7, один клип видео).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.json_parse import parse_json_safe
from utils.llm import make_llm

TEXT_MODEL = settings.openrouter_model

_SYSTEM = """Ты — эксперт по промптам для AI-изображений (fast-gen.ai), вертикаль 9:16.

Пользователь описывает трансформацию «было → стало» (может быть по-русски). Если сюжет про строительство — это частный дом на участке, не многоэтажный ЖК и не офисная высотка. Ты задаёшь два английских промпта для картинок:
1) image_prompt_start — text2img: начальное состояние «ДО», один чёткий кадр.
2) image_prompt_end — цель для img2img ОТ первого кадра: то же место, тот же ракурс и геометрия, состояние «ПОСЛЕ».

scene_kind: "interior" если одна комната / квартира / кухня / ванная / офис изнутри; иначе "exterior" (улица, пляж, дом снаружи, участок).

Верни ТОЛЬКО JSON:
{
  "scene_blueprint": "english: fixed camera, place, main masses",
  "scene_kind": "interior" | "exterior",
  "image_prompt_start": "english detailed BEFORE, photorealistic 9:16",
  "image_prompt_end": "english AFTER for img2img from first image, same camera same place"
}
Без markdown."""


async def run_mode8_prompt_agent(user_topic: str) -> dict:
    t = (user_topic or "").strip()
    if not t:
        raise ValueError("Mode8 prompt agent: empty topic")
    llm = make_llm(temperature=0.2, model=TEXT_MODEL)
    msg = HumanMessage(content=f"Описание от пользователя:\n{t}\n\nСгенерируй JSON.")
    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)
    data = parse_json_safe(text)
    for k in ("scene_blueprint", "scene_kind", "image_prompt_start", "image_prompt_end"):
        if k not in data:
            raise ValueError(f"Mode8 prompt agent missing key: {k}")
    sk = str(data["scene_kind"]).lower().strip()
    if sk not in ("interior", "exterior"):
        data["scene_kind"] = "exterior"
    else:
        data["scene_kind"] = sk
    logger.success(f"[Mode8 Prompt] blueprint={str(data['scene_blueprint'])[:55]}... kind={data['scene_kind']}")
    return data
