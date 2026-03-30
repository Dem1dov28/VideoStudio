"""
Mode 7 — LLM: сцена + два промпта для картинок (до / после) + два видеопромпта.

Картинки в пайплайне: 1) text2img «до»; 2) img2img «после» ТОЛЬКО от первой картинки (тот же ракурс и место).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from modes.mode7.constants import PRESET_LABELS, VALID_PRESET_IDS
from utils.json_parse import parse_json_safe
from utils.llm import make_llm

TEXT_MODEL = settings.openrouter_model

_PRESET_GUIDE = """
beach_cleanup: stills — грязный пляж → тот же ракурс, чистый песок (img2img). ВИДЕО — гиперлапс: толпы волонтёров в жилетах бегают, грабли, мешки, тачки; мусор уходит за ускоренное время; камера статична.
street_cleanup: stills — грязная улица → та же, чистая. ВИДЕО — таймлапс: дворники, метлы, воздуходувы, мешки, техника; люди постоянно в движении.
house_build_zero: stills — пустой участок/котлован → готовый дом на том же месте. ВИДЕО — таймлапс стройки: рабочие и краны в быстром движении, каркас, стены, крыша.
house_restoration: stills — разрушенный дом → восстановленный, тот же ракурс. ВИДЕО — гиперлапс: леса, кровельщики, каменщики, маляры, вывоз мусора, фасад.
interior_restoration: stills — запущенная комната → готовый интерьер, те же окна/план. ВИДЕО — таймлапс ремонта: штукатурка, краска, пол, электрика, люди снуют.
interior_from_scratch: stills — голые стены → готовый интерьер. ВИДЕО — гиперлапс отделки: полы, свет, мебель, монтажники в движении.
"""

_SYSTEM = f"""Ты — эксперт по промптам для AI-изображений и видео (fast-gen.ai), вертикаль 9:16.

Цепочка ИЗОБРАЖЕНИЙ (строго):
1) Первый кадр генерируется с нуля (text2img) по image_prompt_start — состояние «ДО».
2) Второй кадр — ТОЛЬКО img2img от первого кадра: image_prompt_end описывает состояние «ПОСЛЕ» для ТОЙ ЖЕ сцены — тот же ракурс, та же геометрия, те же якорные объекты; меняется степень уборки/стройки/ремонта/чистоты. Нельзя описывать «после» как другую локацию или другой ракурс.

Промежуточное состояние между «до» и «после» НЕ рисуется отдельным still — только два ключа для картинок. Двухчастное развитие сюжета задаётся в video_prompt_0 (первый клип) и video_prompt_1 (второй клип).

ОБЯЗАТЕЛЬНО для ВСЕХ пресетов в video_prompt_0 и video_prompt_1 (на английском):
- Явно пиши hyperlapse / time-lapse / sped-up elapsed time, static locked camera.
- Много людей в движении: бегают, носят, работают инструментами; сцена меняется из-за их труда, не «магия» и не только погода.
- Соответствие категории: уборка (пляж/улица) — волонтёры/дворники; стройка дома — строители и техника; реставрация фасада — кровельщики, леса; интерьер — отделочники, маляры, монтаж мебели.
- Clip 1: яркий прогресс + шумная активность; clip 2: довести до финала still, активность может ослабеть к концу но не исчезать полностью до последних секунд.
- ЗАПРЕЩЕНО описывать видео как «показать первое фото потом второе», crossfade между двумя still, долгий статичный кадр «до» и только в конце смена. Нужны формулировки: continuous motion, every second something moves, mid-clip already half cleaned/built.

{_PRESET_GUIDE}

Верни ТОЛЬКО JSON:
{{
  "scene_blueprint": "одно короткое английское предложение: место, ключевые объекты, фиксированный ракурс",
  "image_prompt_start": "английский, детально: ПЕРВЫЙ кадр text2img — состояние ДО",
  "image_prompt_end": "английский, детально: второй кадр img2img ОТ ПЕРВОГО — состояние ПОСЛЕ, same camera same place",
  "video_prompt_0": "английский: clip 1 — NOT a slideshow; hyperlapse with constant motion; by middle of clip scene already partly transformed; workers/tools visible from second 1; locked camera 9:16",
  "video_prompt_1": "английский: clip 2 — same: ongoing hyperlapse labor until late in clip, then align with final still; never static-then-jump; locked camera 9:16"
}}

video_prompts без музыки. Без markdown."""


async def run_mode7_prompt_agent(preset_id: str, user_topic: str = "") -> dict:
    if preset_id not in VALID_PRESET_IDS:
        raise ValueError(f"Unknown preset: {preset_id}")
    label = PRESET_LABELS[preset_id]
    llm = make_llm(temperature=0.2, model=TEXT_MODEL)
    extra = (user_topic or "").strip()
    msg = HumanMessage(
        content=(
            f"Пресет: {preset_id} ({label}).\n"
            + (f"Дополнительно от пользователя: {extra}\n" if extra else "")
            + "Сгенерируй JSON. Два still (второй = img2img от первого). Видео: таймлапс с непрерывным процессом—не слайдшоу из двух картинок."
        )
    )
    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)
    data = parse_json_safe(text)
    for k in (
        "scene_blueprint",
        "image_prompt_start",
        "image_prompt_end",
        "video_prompt_0",
        "video_prompt_1",
    ):
        if k not in data:
            raise ValueError(f"Mode7 prompt agent missing key: {k}")
    data["preset_id"] = preset_id
    logger.success(f"[Mode7 Prompt] preset={preset_id}, blueprint={str(data['scene_blueprint'])[:60]}...")
    return data
