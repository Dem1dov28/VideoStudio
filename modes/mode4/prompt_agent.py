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
import random
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm

VISION_MODEL = settings.openrouter_vision_model

# Случайная «зерновая» подсказка типа локации на запрос: разнообразие между цитатами.
# Модель ОБЯЗАНА перенести тип сцены в эпоху, регион и биографию конкретного персонажа (не копировать буквально, если несовместимо).
_LOCATION_STEERING_HINTS: tuple[str, ...] = (
    "covered market or exchange arcade, stalls, fabrics, morning bustle",
    "stone quay, boats, rope, gulls, drizzle",
    "cathedral or temple aisle: pillars, stone floor, dim light",
    "rampart or fortress wall walk, crenellations, wind",
    "riverside willows, reed bank, small jetty, golden hour",
    "vineyard terrace, stone wall, vine rows",
    "palace or manor gallery: parquet, portraits, tall windows",
    "lecture hall or examination room: benches, chalkboard, inkstands",
    "apothecary or workshop: jars, herbs, single lamp",
    "scriptorium or archive: lecterns, books, narrow windows",
    "forge or armoury: anvil, coals, tools",
    "barn or threshing floor: straw, beams, dust in sunbeams",
    "orchard or garden wall, bloom, wooden fence",
    "mountain trail: wind, scree, distant peaks",
    "caravanserai courtyard: arcades, well, pack animals",
    "steppe camp: tents, fire smoke, wide sky",
    "irrigated fields or terraces, paths, workers",
    "tea pavilion or bamboo path, paper lanterns at dusk",
    "forum or agora edge: colonnade, merchants, bright noon",
    "Roman bath interior: marble, steam, oil lamps",
    "amphitheatre stone seats, sand, long shadows",
    "ship or boat deck: oars, spray, coastline",
    "counting-house above warehouse: ledgers, harbor noise",
    "coaching inn courtyard: carriage, lanterns, cobbles",
    "railway platform: iron canopy, steam (only if era allows)",
    "theatre backstage: ropes, costumes, footlights",
    "music room: harpsichord or piano, candles",
    "hospital or ward of the period: beds, screens",
    "law court antechamber: benches, clerks",
    "prison yard or corridor: grilles, worn stone",
    "captain's cabin: maps, compass, sea window",
    "observatory: brass instruments, charts, night sky",
    "library reading room: stacks, ladder, green lamps",
    "coffeehouse or club room: chairs, newspapers, foggy window",
    "artist's studio: easel, casts, north light",
    "greenhouse or orangery: glass, plants, winter sun",
    "stable aisle: straw, tack, horses",
    "mill interior: stones, grain dust, light shaft",
    "bridge midpoint: arches below, wind",
    "city gate or toll: carts, guards, dust",
    "monastery cloister: garth, fountain, arcades",
    "courtyard of worship: tiles, fountain, quiet hour",
    "roadside shrine: candles, steps, trees",
    "fishing village: nets, racks, low sun",
    "salt works or drying yard: white glare, workers",
    "quarry or stone yard: blocks, chisels, dust",
    "fair or feast-day square: booths, banners",
    "cemetery gate: iron, yew, overcast",
    "roof or belvedere: chimneys, pigeons, sunset",
    "wine cellar: brick vault, racks, candle",
    "war tent or field HQ: maps, pennants, twilight",
    "siege camp: earthworks, smoke, dawn",
    "hunting lodge hall: fire, trophies, shadows",
    "scholar's room: low desk, brush and ink, garden glimpse",
    "carriage interior: rain on window, lamp sway",
    "lighthouse gallery: lantern glass, sea spray",
    "early factory floor: belts, high windows (only if era fits)",
    "dockside tavern back room: barrels, harbor light",
    "formal garden: hedges, gravel, fountain",
    "moor or heath: bent grass, stone, lowering sky",
    "oasis fringe: palms, pool, heat shimmer",
    "frozen river or winter fair (only if era and climate fit)",
)


def _pick_location_steering_hint() -> str:
    return random.choice(_LOCATION_STEERING_HINTS)


def _speech_language_user_hint(
    quote: str,
    *,
    bilingual: bool,
    source_russian_only: bool,
    auto_detect_lang: bool,
    subtitle_lang: str,
) -> str:
    """Одна строка в user-message: жёстко задаёт speaking in X под язык цитаты."""
    if bilingual and source_russian_only:
        return (
            "ЯЗЫК РЕЧИ (bilingual): в video_prompt_ru — speaking in Russian и только русская цитата; "
            "в video_prompt_en — speaking in English и только английский перевод; без Latin, без двух цитат в одном промпте.\n\n"
        )
    if auto_detect_lang:
        return (
            "ЯЗЫК РЕЧИ: определи detected_lang; в video_prompt speaking in [Language] совпадает с языком цитаты "
            "(ru→Russian, en→English, de→German, fr→French, …); цитата в кавычках на том же языке.\n\n"
        )
    if re.search(r"[\u0400-\u04FF]", quote):
        lang = "Russian"
    elif subtitle_lang.lower() == "en":
        lang = "English"
    else:
        lang = "Russian"
    return (
        f"ЯЗЫК РЕЧИ: в video_prompt — speaking in {lang}; цитата в кавычках строго на этом языке; "
        f"не Latin/Greek, если цитата не на латыни/греческом дословно.\n\n"
    )


_SYSTEM = """Ты — эксперт по кинематографичной AI-генерации и исторической достоверности.

По фото личности, её имени и цитате создаёшь ДЕТАЛЬНЫЙ промпт для video-to-video генерации (Veo, Runway, fast-gen.ai).

## ИСТОРИЧЕСКАЯ ТОЧНОСТЬ И ФАКТЫ (критично):
- По **имени** (и цитате, если даёт подсказку) определи: **век или узкий диапазон лет**, **регион/государство**, **социальный статус и род занятий** (сенатор, монах, офицер, купец, учёный…). Опирайся на общеизвестные исторические сведения о таких людях и их эпохе; не выдумывай несуществующие титулы, формы одежды или технологии.
- Одежда и локация должны быть **согласованы** друг с другом и с эпохой: нельзя смешивать века, нельзя ставить персонажа в интерьер с предметами, появившимися позже (электричество до эпохи, огнестрел до изобретения, стёкла панорамные в античности и т.д.).
- Освещение и быт: только то, что **реально могло быть** (свеча, лучина, масляный светильник, газовый фонарь улицы, дневной свет через конкретный тип окон — в зависимости от периода).
- Если личность **малоизвестна** — не придумывай экзотику: возьми **характерный, хорошо документированный** архетип среды для данного статуса и региона (ткани, крой мебели, тип здания того времени).
- В english video_prompt избегай размытых формулировок вроде «period costume», «old room»: всегда **конкретные** термины (названия предметов одежды, детали архитектуры, материалы).
- **Реквизит и техника в кадре** — только то, что могло существовать в выбранном веке и регионе. Примеры ошибок: магнитный компас-коробка и «современная» навигация в раннем Риме; электрический свет до эпохи; панорамное остекление там, где его не было. Навигация античности — ориентиры по берегу, звёзды, гардемарины, восковые таблички, свитки-маршруты; не выдумывай приборы из более поздних веков.

## ЯЗЫК РЕЧИ В video_prompt (обязательно)
- Фраза **speaking in [Language]** должна **совпадать с языком цитаты в кавычках** в том же промпте: русская цитата → `speaking in Russian`; английская → `speaking in English`; и т.д. по `detected_lang` при auto_detect.
- **Запрещено**: писать Latin, Ancient Greek и т.п. для озвучки, если в кавычках **не** дословный текст на этом языке (цитата для пользователя на русском/английском — персонаж «говорит» на языке этой цитаты в промпте, это художественный приём для зрителя).
- **Один** пункт РЕЧЬ — **одна** цитата **одним** языком; не дублировать в одном video_prompt две реплики на разных языках (не «saying: RU…» и отдельно «He speaks EN…»).
- Режим **bilingual**: в `video_prompt_ru` — только `speaking in Russian` и русская цитата; в `video_prompt_en` — только `speaking in English` и английский перевод; поле `video_prompt` = как согласовано в инструкции ниже.

## ОДЕЖДА — точное соответствие эпохе и личности (блок ПЕРСОНАЖ, на английском; критично):
- Сначала мысленно зафиксируй: **век/десятилетие**, **регион**, **пол и возраст по фото**, **род занятий и статус** по имени и общеизвестным фактам. Вся одежда должна быть **проверяема** для этой комбинации (не «костюм эпохи» вообще, а одежда **этого** человека или **такого** статуса в **этом** месте и времени).
- Для широко известных личностей — опирайся на **характерные** для них типы одежды того периода (военная форма века, сана, придворный/гражданский костюм, монашеское облачение, мундир, халат учёного и т.д.), не выдумывай фантастические варианты.
- **Минимум 6–8 конкретных пунктов** в video_prompt про одежду и убор: ткани с названием фактуры, цветовые акценты, крой, длина, ворот, рукава, головной убор или причёска эпохи, обувь, перчатки/без, украшения или регалии **только** если уместны.
- **Ткани и фактура**: шерсть, лён, сукно, шёлк, кожа, мех, бархат, камлот — по статусу, климату региона и веку; плотность (heavy wool greatcoat, fine cambric shirt).
- **Крой и силуэт** строго века: не подмешивай силуэт XX–XXI века.
- **Застёжки и узлы**: пуговицы, крючки, шнуровка, пояс, фибула — только периода.
- Если на фото видна одежда — **не противоречь** ей по типу одежды (верх/длина/головной убор), но **детализируй и эпохализируй** под выведенный исторический контекст (как та же роль выглядела бы в документальной реконструкции).
- Запрещено: анахронизмы, обобщения «period costume», «vintage suit» без конкретики, смешение национальных форм без оснований.

## КИНЕМАТОГРАФИЧНЫЙ ФОН, ПРИВЯЗАННЫЙ К ЭПОХЕ (обязательно для всего video_prompt)
- Сначала **зафиксируй эпоху одной фразой** (на английском в блоке ОКРУЖЕНИЕ): примерный век, регион, тип места — например: *late 19th-century Russian provincial study*, *High Roman Empire interior*, *English Regency drawing room*. Это якорь: всё окружение должно **однозначно** относиться к этой эпохе и месту.
- Фон — не «иллюстрация», а **кадр из исторической драмы**: глубина (передний план / середина / даль), мотивированный свет (от окна, свечей, очага, уличных фонарей — что уместно веку), объём воздуха, пыль/туман/пар при необходимости, **цветовая гамма эпохи** (теплые масляные тона, холодный дневной свет, ламповый янтарь — по смыслу).
- Архитектура, мебель, бытовые предметы, окна, уличная застройка за окном — **только** из выбранного века; без смешения стилей и без «универсальной старины».
- В english video_prompt используй **киноязык**: wide shot / medium shot, layered composition, chiaroscuro where fitting, atmospheric haze, practical light sources visible in frame — но без названий фильмов и режиссёров.

## ОКРУЖЕНИЕ — **видимый** фон с глубиной (никогда void, пустая студия, однотонный экран).

Пометь тип: *documented setting* (B) или *portrait-with-environment* (A).

### B) Осмысленное место (**по умолчанию** — главный способ дать кинематографичный эпохальный фон)
- В **каждом** запросе пользователь даёт строку **LOCATION_STEERING_FOR_THIS_REQUEST** — это **случайный тип локации для разнообразия** между разными цитатами. Твоя задача: воплотить **тот же тип сцены** (рынок / набережная / библиотека / поле / казарма / мастерская и т.п.) в **конкретном месте и архитектуре эпохи и региона персонажа**.
- Если буквальная подсказка **географически или хронологически невозможна** (например, римский форум у северного мореплавателя XVII в.) — **не игнорируй** подсказку: замени на **эквивалент того же типа** в правильном веке и регионе (например, торговая площадь / пристань своего времени).
- Интерьер или натура **той же эпохи**, что персонаж; дополнительно согласуй с биографией, статусом и образами цитаты, если они требуют другого, **но всё равно сохрани «тип» из подсказки**, когда это совместимо.
- **Минимум 5–7 видимых деталей** + **2–3 кинематографических** (ключ, тени, планы, перспектива).
- Запрещено: игнорировать LOCATION_STEERING без причины; ставить «любимый» один и тот же кабинет вопреки подсказке; случайные декорации вне эпохи и личности.

### A) Портрет с глубиной (**редко**, очень абстрактная цитата)
- Фон **всё равно эпохальный**: размытый, но узнаваемый интерьер или вид из окна **того же века** — силуэты мебели эпохи, рама окна, колонна, шторы, полки, штукатурка.
- **Запрещено**: flat backdrop, пустая студия, градиент без предметов.
- **5–7 деталей** фона + указание, как свет из эпохи (свеча, окно) создаёт объём.

### Общее
- Не смешивай A и B. **Если сомневаешься — B** с типичной для личности обстановкой **конкретного века**.
- Shallow DOF допустим: фон мягкий, но **эпоха и пространство читаются** по силуэтам и свету.

## ДЕТАЛЬНОСТЬ video_prompt (200–320 слов, плотно по фактам):
Пиши развёрнуто, на английском. Структура:

1. ПЕРСОНАЖ (подробно): внешность по фото, возраст, волосы/борода; **одежда — минимум 6–8 конкретных деталей**, каждая согласована с **этой** личностью и **этой** эпохой (см. раздел «ОДЕЖДА»); поза, осанка; выражение лица.
2. ОКРУЖЕНИЕ (подробно): якорь — век + регион + тип места на английском; **обязательно** опирайся на **LOCATION_STEERING_FOR_THIS_REQUEST** (тип сцены), перенесённый в исторически достоверную локацию для персонажа. Затем **B** или **A**; **минимум 5–7 видимых деталей фона** + кинопостановка.
3. ОСВЕЩЕНИЕ И АТМОСФЕРА: кинематографично и **мотивированно эпохой** — источники света того времени, настроение кадра, тени, воздух (пыль, туман при уместности).
4. ДВИЖЕНИЕ: walks slowly, stops, turns, faces the camera.
5. РЕЧЬ: He/She begins speaking in **[exactly the language of the quoted text]**, his/her voice [тембр], saying: "[одна цитата — тот же язык]". Expression: [описание]. Без Latin/другого языка при цитате на RU/EN.
6. Технические: period-accurate **cinematic** framing, photorealistic, 8K, vertical 9:16 portrait; shallow DOF только если эпохальный фон **читается** по свету и силуэтам.

Имя в промпте НЕ писать. Описывать по роли и внешности, с **конкретной** эпохальной одеждой и местом (без штампов и без имени).

Верни ТОЛЬКО JSON:
{
  "video_prompt": "200–320 слов: одежда точно под эпоху и личность; окружение по случайной подсказке типа локации, перенесённой в исторические реалии персонажа",
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

    location_steering = _pick_location_steering_hint()
    speech_hint = _speech_language_user_hint(
        quote,
        bilingual=bilingual,
        source_russian_only=source_russian_only,
        auto_detect_lang=auto_detect_lang,
        subtitle_lang=subtitle_lang,
    )

    msg = HumanMessage(content=[
        {"type": "text", "text": (
            speech_hint
            + "ОДЕЖДА: подбери **в точности** под эпоху, регион, статус и пол персонажа (имя + фото). "
            "Минимум **6–8** конкретных элементов в блоке ПЕРСОНАЖ на английском; без анахронизмов и без обобщений «period dress».\n\n"
            "LOCATION_STEERING_FOR_THIS_REQUEST (случайный тип локации для разнообразия между цитатами; **не копируй буквально**, если не сочетается с веком/регионом):\n"
            f"{location_steering}\n\n"
            "Обязательно: воплоти **этот тип места** в **исторически достоверной** локации для данной личности (архитектура, быт, география). "
            "При несовместимости — тот же **тип** сцены в правильной эпохе и месте. Фон кинематографичный, с глубиной; без void. "
            "**B** по умолчанию; **A** — редко при очень абстрактной цитате (эпохальный размытый интерьер).\n\n"
            f"Имя личности (НЕ писать в промпте! Для эпохи, региона, одежды и локации): {person_name}\n\n"
            f"Цитата (вставить в video_prompt в кавычках): {quote}\n\n"
            f"bilingual: {bilingual}\n"
            f"subtitle_lang: {subtitle_lang}\n"
            f"auto_detect_lang: {auto_detect_lang}\n"
            f"source_russian_only: {source_russian_only}\n"
            "video_prompt: 200–320 слов на английском. В явном виде свяжи окружение с подсказкой типа локации выше (перенос в эпоху персонажа). "
            "Проверь: одежда ↔ личность ↔ эпоха; фон ↔ история; нет пустого фона. "
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
