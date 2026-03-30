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

## ИСТОРИЧЕСКАЯ ТОЧНОСТЬ И ФАКТЫ (критично):
- По **имени** (и цитате, если даёт подсказку) определи: **век или узкий диапазон лет**, **регион/государство**, **социальный статус и род занятий** (сенатор, монах, офицер, купец, учёный…). Опирайся на общеизвестные исторические сведения о таких людях и их эпохе; не выдумывай несуществующие титулы, формы одежды или технологии.
- Одежда и локация должны быть **согласованы** друг с другом и с эпохой: нельзя смешивать века, нельзя ставить персонажа в интерьер с предметами, появившимися позже (электричество до эпохи, огнестрел до изобретения, стёкла панорамные в античности и т.д.).
- Освещение и быт: только то, что **реально могло быть** (свеча, лучина, масляный светильник, газовый фонарь улицы, дневной свет через конкретный тип окон — в зависимости от периода).
- Если личность **малоизвестна** — не придумывай экзотику: возьми **характерный, хорошо документированный** архетип среды для данного статуса и региона (ткани, крой мебели, тип здания того времени).
- В english video_prompt избегай размытых формулировок вроде «period costume», «old room»: всегда **конкретные** термины (названия предметов одежды, детали архитектуры, материалы).

## ОДЕЖДА — обязательная детализация (в блоке ПЕРСОНАЖ, на английском):
- **Ткани и фактура**: шерсть, лён, сукно, шёлк, кожа, мех, бархат — что уместно статусу и климату; плотность/вес ткани (heavy wool coat, fine linen shirt).
- **Крой и силуэт** эпохи: длина подола, ширина рукава, высота воротника/головного убора, характерная линия плеч/талии для данного века (не XXI век).
- **Застёжки и узлы**: пуговицы, крючки, шнуровка, пояс, фибула — **только** свойственные периоду.
- **Обувь, чулки/поножи, перчатки**, головной убор или причёска — по нормам эпохи и пола персонажа по фото.
- **Знаки статуса**: регалии, ордена, перстни, оружие эпохи (клинок, шпага), письменные принадлежности, инструмент ремесла — только если логично роли.

## ЛОКАЦИЯ — обязательная детализация (в блоке ОКРУЖЕНИЕ, на английском):
- **Тип места** + **архитектурный стиль** периода (романский/готический зал, классицизм, сруб/терем, каменный подвал, античный перистиль — по смыслу, без путаницы веков).
- **Материалы**: камень (гранит, известняк, кирпич), дерево (тёмный дуб, сосна), штукатурка, мрамор; **пол** — плитка, доски, земля, мозаика.
- **Окна, двери, потолок** (свод, балки, роспись, голые балки), **мебель и реквизит** с названиями предметов эпохи (кафедра, кируас, секретер, кивот, канделябр — уместные для даты).
- **География и атмосфера**: город/сельская местность, **растительность** и погода, соответствующие региону (не пальмы у полярного круга; не «европейский» дуб в сцене Древнего Рима без контекста).

## РАЗНООБРАЗИЕ ЛОКАЦИЙ (обязательно):
- Не циклись на одних и тех же местах (кабинет с книгами, набережная, «римский сад», писательский стол у окна).
- Каждый раз выбирай **одну** свежую, конкретную локацию, которая **прямо подходит** персонажу и эпохе, но не обязана быть «классической» для цитат.
- Черпай из широкого круга (всё — в границах эпохи): улочка / рынок / храм или церковь / аркада / вокзал или пристань / каюта или купе / поле или виноградник / терраса / лестница дворца / скрипторий или архив / трактир / баня или термы / сад-огород / мастерская / крыша или башня / зимний двор / подземная сводчатая зала / мост / сенат или зала заседаний / укрепление или лагерь / больничная палата эпохи / концертный зал XIX в. — и т.п.
- Если образ на фото нейтральный — локацию всё равно зафиксируй однозначно и колоритно; не оставляй «просто комната».

## ДЕТАЛЬНОСТЬ video_prompt (200–320 слов, плотно по фактам):
Пиши развёрнуто, на английском. Структура:

1. ПЕРСОНАЖ (подробно): внешность по фото, возраст, волосы/борода; **одежда — минимум 4–6 конкретных деталей** из раздела «ОДЕЖДА» (ткани, крой, застёжки, головной убор/обувь, аксессуар эпохи); поза, осанка; выражение лица.
2. ОКРУЖЕНИЕ (подробно): **конкретная** локация; **минимум 5–7 деталей** из раздела «ЛОКАЦИЯ» (стиль здания, материалы пола/стен, окна, мебель и предметы с историческими именами, природа/город, время суток и погода).
3. ОСВЕЩЕНИЕ И АТМОСФЕРА: время дня, тип света (закат, газовые фонари, свечи), тени, воздух, настроение.
4. ДВИЖЕНИЕ: walks slowly, stops, turns, faces the camera.
5. РЕЧЬ: He begins speaking in [Russian/English], his voice [детальное описание тембра], saying: "[точная цитата]". Expression: [глубокое описание].
6. Технические: wide-to-medium shot, Cinematic quality, photorealistic, 8K, vertical 9:16 portrait, shallow depth of field.

Имя в промпте НЕ писать. Описывать по роли и внешности, с **конкретной** эпохальной одеждой и местом (без штампов и без имени).

Верни ТОЛЬКО JSON:
{
  "video_prompt": "подробный промпт 200–320 слов (одежда + локация максимально конкретны и проверяемы по эпохе)",
  "video_prompt_ru": "промпт с 'speaking in Russian' (только если bilingual)",
  "video_prompt_en": "промпт с 'speaking in English' (только если bilingual)",
  "voice_description": "...",
  "script_ru": "цитата дословно",
  "script_en": "перевод (если bilingual ИЛИ subtitle_lang=en)",
  "person_name_en": "имя автора на английском (только если source_russian_only+bilingual)",
  "detected_lang": "ru|en|de|fr|es|... (если auto_detect — ISO 639-1 код языка цитаты)"
}
При auto_detect: определи язык цитаты, верни detected_lang. Субтитры = цитата как есть. script_ru/script_en — устаревшие при auto_detect.

Режим source_russian_only + bilingual: цитата и имя автора ВВОДА на русском. Обязательно:
- script_ru — цитата дословно по-русски;
- script_en — точный литературный перевод цитаты на английский;
- person_name_en — принятое английское написание имени (Marcus Aurelius, Leo Tolstoy, …);
- video_prompt_ru — персонаж/сцена, в речи дословная русская цитата в кавычках;
- video_prompt_en — НЕ переписывай заново внешность: это ТОТ ЖЕ человек и ТА ЖЕ сцена, что в video_prompt_ru. Скопируй блоки 1–4 (персонаж, окружение, свет, движение) с video_prompt_ru, переведи их на английский ДОСЛОВНО по смыслу, без новых черт лица/причёски/возраста. Меняется только пункт РЕЧЬ: speaking in English + английская цитата в кавычках. Лицо и тело задаёт только фото-референс в генераторе — в тексте не противоречь фото и не описывай «другого» человека.
- video_prompt — ВСЕГДА заполни: дублируй video_prompt_en (или общий промпт на английском 200–320 слов). Без ключа video_prompt ответ считается ошибочным."""


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
    from utils.json_parse import parse_json_safe
    return parse_json_safe(text)


def _ensure_video_prompt(data: dict) -> None:
    """
    LLM иногда отдаёт только video_prompt_ru / video_prompt_en (bilingual), без video_prompt.
    """
    vp = (data.get("video_prompt") or "").strip()
    if vp:
        return
    ru = (data.get("video_prompt_ru") or "").strip()
    en = (data.get("video_prompt_en") or "").strip()
    if en:
        data["video_prompt"] = en
        logger.warning("[Mode4 Prompt] Filled video_prompt from video_prompt_en")
    elif ru:
        data["video_prompt"] = ru
        logger.warning("[Mode4 Prompt] Filled video_prompt from video_prompt_ru")
    else:
        raise ValueError(
            "Prompt agent missing video_prompt (and no video_prompt_ru / video_prompt_en)"
        )


async def run_quote_prompt_agent(
    photo_path: str | Path,
    quote: str,
    person_name: str = "",
    bilingual: bool = False,
    subtitle_lang: str = "ru",
    auto_detect_lang: bool = False,
    source_russian_only: bool = False,
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
        source_russian_only: цитата и имя на русском; при bilingual — перевод для EN-версии и person_name_en

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

    ru_bilingual_hint = (
        "\n\nsource_russian_only: True — цитата и имя автора УЖЕ на русском. "
        "Сгенерируй ДВЕ версии промптов (video_prompt_ru + video_prompt_en), script_ru, script_en, person_name_en. "
        "ОБЯЗАТЕЛЬНО также ключ video_prompt — скопируй туда video_prompt_en (полный английский промпт). "
        "Имя автора в промпты НЕ включать; для подписи пользователю нужен person_name_en. "
        "КРИТИЧНО: сначала полностью сформируй video_prompt_ru (одно лицо/сцена по фото). "
        "video_prompt_en = тот же персонаж и сцена (перевод описания), отличается только язык речи и цитата в кавычках. "
        "Запрещено в EN-версии выдумывать другую внешность."
    ) if source_russian_only and bilingual else ""

    msg = HumanMessage(content=[
        {"type": "text", "text": (
            f"Имя личности (НЕ писать в промпте! Используй для эпохи и исторической точности): {person_name}\n\n"
            f"Цитата (вставить в video_prompt в кавычках): {quote}\n\n"
            f"bilingual: {bilingual}\n"
            f"subtitle_lang: {subtitle_lang}\n"
            f"auto_detect_lang: {auto_detect_lang}\n"
            f"source_russian_only: {source_russian_only}\n"
            "video_prompt: 200–320 слов на английском. Одежда и локация — **максимально детально** и **в рамках исторических фактов** (см. системные разделы про одежду, локацию, хронологию; конкретные материалы, крой, архитектура, мебель, освещение эпохи). "
            "Окружение: **разнообразная** подходящая локация (не штамп кабинет/набережная по умолчанию). "
            "Перед ответом мысленно проверь: нет ли анахронизмов в одежде, здании и быту. "
            "Цитату в кавычках."
            + auto_hint
            + ru_bilingual_hint
            + " Верни ТОЛЬКО JSON."
        )},
        {"type": "image_url", "image_url": {"url": img_url}},
    ])

    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)
    data = _parse_json_response(text)

    _ensure_video_prompt(data)

    data.setdefault("script_ru", quote)
    data.setdefault("script_en", "")
    data.setdefault("person_name_en", "")
    data.setdefault("voice_description", "")
    data.setdefault("detected_lang", "")

    if source_russian_only and bilingual:
        if not data.get("script_ru"):
            data["script_ru"] = quote
        if not (data.get("script_en") or "").strip():
            logger.warning("[Mode4 Prompt] Missing script_en — using Russian quote as fallback")
            data["script_en"] = quote
        if not (data.get("person_name_en") or "").strip():
            logger.warning("[Mode4 Prompt] Missing person_name_en — using Russian name as fallback")
            data["person_name_en"] = person_name

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
