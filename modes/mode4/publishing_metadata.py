"""
Mode 4 — метаданные для публикации (YouTube Shorts): заголовок, описание, теги, первый комментарий.

Текстовая LLM (без vision). Промпт заточен под христианскую нишу и 8-секундные Shorts с цитатой;
автор подставляется из запроса (Иисус и др.).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.json_parse import parse_json_safe
from utils.llm import make_llm
from utils.publishing_metadata import normalize_hashtags, normalize_tags, normalize_title

_MIN_TAGS = 8
_MAX_TAGS = 12

# Добираем теги, если модель вернула мало — без дублей, в духе ниши Shorts + вера
_TAG_TOPUP_RU: list[str] = [
    "христианские Shorts",
    "стих дня",
    "Библия",
    "вера",
    "Иисус Христос",
    "евангелие",
    "духовное размышление",
    "христианская мотивация",
    "Слово Божье",
    "Shorts христианство",
    "библейская цитата",
    "вера и жизнь",
    "христианский контент",
    "библейский стих",
]

_TAG_TOPUP_EN: list[str] = [
    "Jesus Christ",
    "Christian Shorts",
    "Bible verse",
    "faith motivation",
    "Christianity",
    "Gospel",
    "daily Scripture",
    "Bible study",
    "Christian content",
    "faith journey",
    "Scripture Shorts",
    "Jesus teachings",
    "spiritual growth",
    "Christian life",
]

_HASHTAG_TOPUP_RU: list[str] = [
    "#Shorts",
    "#Библия",
    "#христианство",
    "#вера",
    "#Иисус",
    "#цитата",
    "#евангелие",
    "#мотивация",
]

_HASHTAG_TOPUP_EN: list[str] = [
    "#Shorts",
    "#Jesus",
    "#Christianity",
    "#Faith",
    "#BibleVerse",
    "#Gospel",
    "#ChristianLife",
    "#Scripture",
]


def _top_up_tags(tags: list[str], language: str) -> list[str]:
    if len(tags) >= _MIN_TAGS:
        return tags[:_MAX_TAGS]
    seen = {t.lower().strip() for t in tags if t.strip()}
    pool = _TAG_TOPUP_RU if language == "ru" else _TAG_TOPUP_EN
    out = [t.strip() for t in tags if t.strip()]
    for p in pool:
        if len(out) >= _MIN_TAGS:
            break
        pl = p.lower().strip()
        if pl not in seen:
            seen.add(pl)
            out.append(p)
    return out[:_MAX_TAGS]


def _ensure_description_body_and_hashtags(desc: str, language: str) -> str:
    """Добавляет абзац и хэштеги, если описание слишком короткое или мало #."""
    s = (desc or "").strip()
    found_ht = re.findall(r"#[\w\u0400-\u04FF]+", s)
    extras = _HASHTAG_TOPUP_RU if language == "ru" else _HASHTAG_TOPUP_EN
    low = s.lower()
    if len(found_ht) < 3:
        to_add = [h for h in extras if h.lower() not in low]
        need = 3 - len(found_ht)
        if to_add and need > 0:
            s = s.rstrip() + "\n\n" + " ".join(to_add[:need])
    if len(s) < 220:
        if language == "ru":
            pad = (
                "\n\nОдна мысль на день — чтобы не гнаться за шумом, а услышать спокойнее. "
                "Подпишитесь, если заходите за честными Shorts по Писанию без пустых обещаний."
            )
        else:
            pad = (
                "\n\nOne truth to sit with — not hype, just Scripture you can carry into real life. "
                "Subscribe if you want more straight, faith-filled Shorts without empty noise."
            )
        if pad.strip() not in s:
            s = s.rstrip() + pad
    hashtags = normalize_hashtags(
        re.findall(r"#[\w\u0400-\u04FF]+", s),
        fallback_pool=extras,
        min_count=3,
        max_count=5,
    )
    s_wo_hash = re.sub(r"(?:\n\s*)?(#[\w\u0400-\u04FF]+\s*)+$", "", s, flags=re.MULTILINE).strip()
    return (s_wo_hash + "\n\n" + " ".join(hashtags)).strip()


# ── Системный промпт (RU) — по ТЗ пользователя + гибкость по автору ─────────
SYSTEM_RU = """Ты — эксперт по YouTube Shorts в христианской нише. Твоя задача — создавать оптимизированные заголовки, описания и теги для 8-секундных видео с цитатами (в т.ч. Иисуса Христа и других библейских/духовных авторов, если указаны во входе).

ОСНОВНЫЕ ПРАВИЛА:

1. ВИДЕО:
- Длительность: 8 секунд
- Содержание: только цитата (голос или текст на экране)
- Внутри видео нет призывов подписаться, нет объяснений, нет «решений»

2. ЗАГОЛОВОК (Title):
- Длина: 50-70 символов (чтобы не обрезался на мобильных)
- Должен решать проблему или снимать возражение, которое вызывает цитата
- Первые 40 символов — самые важные (видно без нажатия)
- Используй сильные слова: Why, Truth, Warning, Shocking, Hard, Real Meaning (уместно по языку ответа)
- Формат: «Крючок | Имя автора (Книга:стих)» — если стих известен из цитаты/контекста; иначе «Крючок | Имя автора»
- НЕ используй: кликбейт без связи с цитатой, капслок, больше одного восклицательного знака

3. ОПИСАНИЕ (Description):
- Объём: целевой диапазон 380–650 символов (вместе с хэштегами) — Shorts и поиск любят плотное, но честное описание
- Первые 2 строки (130–180 символов) — крючок + SEO: боль, надежда, ключевые слова по теме цитаты
- Далее: 2–4 коротких абзаца — контекст стиха, почему это важно сегодня, эмоциональная отдача (без манипуляций)
- Одна строка — мягкий призыв подписаться
- Обязательно — открытый вопрос к комментаторам (можно два связанных вопроса)
- В конце ОТДЕЛЬНОЙ строкой или блоком: 8–12 хэштегов (смесь широких: #Shorts #христианство #Библия и узких под тему стиха: гонения, вера, мир и т.д.)
- Тон: уважительный, честный, без осуждения, без prosperity gospel
- НЕ используй: «нажми лайк», «отправь другу», капслок, эмодзи больше 2-3 штук

4. ТЕГИ (Tags):
- ОБЯЗАТЕЛЬНО не меньше 14 и не больше 22 тегов через запятую (одна строка)
- Первые 3–4: автор/роль, ключевая боль или обещание из темы, книга и стих если уместно
- Дальше: синонимы, «длинный хвост» (как ищут люди), нишевые формулировки, формат (shorts, размышление, стих дня), эмоции (надежда, испытание, вера)
- Добавь теги под алгоритмы: то, что реально вводят в поиске YouTube (рус/англ по языку ответа)
- Формат: без решёток, только слова и фразы через запятую

5. ПЕРВЫЙ КОММЕНТАРИЙ:
- 2–4 предложения — больше шанс удержать обсуждение и «виральность» в комментариях
- Раскрой одну ключевую мысль ИЛИ задай два разных угла вопроса (личный опыт + толкование)
- Мягкий призыв подписаться только в самом конце

ФОРМАТ ВЫВОДА (СТРОГО, без преамбулы и без пояснений после блоков):

=== ЗАГОЛОВОК ===
[твой вариант]

=== ОПИСАНИЕ ===
[твой вариант]

=== ТЕГИ ===
[твой вариант]

=== ПЕРВЫЙ КОММЕНТАРИЙ ===
[твой вариант]

Если автор во входе — не Иисус, сохраняй стиль Shorts и духовной ниши, но подставляй указанного автора в заголовок и теги вместо «Иисус», не выдумывай библейский стих без основания."""


SYSTEM_EN = """You are a YouTube Shorts expert in the Christian niche. Create optimized titles, descriptions, and tags for 8-second quote videos (Jesus Christ and other biblical/spiritual authors as given in the input).

CORE RULES:

1. VIDEO: 8 seconds; quote only on screen/voice; no subscribe CTAs, explanations, or "solutions" inside the video.

2. TITLE: 50-70 characters; addresses tension/objection the quote raises; first ~40 chars critical; strong words: Why, Truth, Warning, Shocking, Hard, Real Meaning where fit. Format: "Hook | Author (Book:verse)" if verse is clear, else "Hook | Author". No misleading clickbait, no ALL CAPS, max one exclamation mark.

3. DESCRIPTION: Target 380–650 characters total including hashtags. First 2 lines (130–180 chars): hook + SEO keywords tied to the quote's tension. Then 2–4 short paragraphs: context, why it matters today, emotional payoff (no manipulation). One soft subscribe line. Mandatory open question(s) for comments. End with a separate line/block of 8–12 hashtags — mix broad (#Shorts #Christianity #Bible) and niche tags matching the verse theme (persecution, faith, peace, etc.). Respectful tone; no prosperity gospel; no "smash like"; max 2-3 emojis.

4. TAGS: MANDATORY minimum 14 and maximum 22 comma-separated tags, no #. First 3–4: author, core theme/pain point, book/chapter if applicable. Then synonyms, long-tail search phrases, Shorts/devotional format tags, emotional angles people actually type into YouTube search.

5. FIRST COMMENT: 2–4 sentences, pin-worthy; deepen one idea OR two angles (personal + interpretation); soft subscribe only at the very end.

OUTPUT FORMAT (strictly, no preamble):

=== TITLE ===
[your line]

=== DESCRIPTION ===
[your text]

=== TAGS ===
[comma-separated]

=== FIRST COMMENT ===
[your comment]

If the author is not Jesus, keep the same Shorts+faith style but use the named author; do not invent scripture references."""


def _human_ru(
    quote_ru: str,
    person_ru: str,
    quote_en: str,
    person_en: str,
) -> str:
    return f"""КОНТЕКСТ (английский вариант той же мысли, если отличается):
«{quote_en.strip()}» — {person_en.strip()}

СЕЙЧАС ТЫ ПОЛУЧИШЬ ЦИТАТУ. НАПИШИ ВСЁ ПО ФОРМАТУ. НИКАКИХ ОБЪЯСНЕНИЙ, ТОЛЬКО РЕЗУЛЬТАТ.

Автор (как в ролике): {person_ru.strip()}
Текст цитаты:
«{quote_ru.strip()}»"""


def _human_en(
    quote_ru: str,
    person_ru: str,
    quote_en: str,
    person_en: str,
) -> str:
    return f"""Context (Russian original):
«{quote_ru.strip()}» — {person_ru.strip()}

You will now receive THE QUOTE. OUTPUT EVERYTHING IN THE REQUIRED FORMAT ONLY. NO EXPLANATIONS.

Author (as in the video): {person_en.strip()}
Quote text:
«{quote_en.strip()}»"""


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _parse_sections(text: str, language: str) -> dict[str, str]:
    """Parse === SECTION === blocks (RU or EN headers)."""
    text = _strip_fences(text)
    if language == "ru":
        spec = [
            ("title", "ЗАГОЛОВОК"),
            ("description", "ОПИСАНИЕ"),
            ("tags", "ТЕГИ"),
            ("first_comment", "ПЕРВЫЙ КОММЕНТАРИЙ"),
        ]
    else:
        spec = [
            ("title", "TITLE"),
            ("description", "DESCRIPTION"),
            ("tags", "TAGS"),
            ("first_comment", "FIRST COMMENT"),
        ]
    out: dict[str, str] = {}
    for key, header in spec:
        pat = rf"===\s*{re.escape(header)}\s*===\s*(.*?)(?=\n===|\Z)"
        m = re.search(pat, text, flags=re.DOTALL | re.IGNORECASE)
        if m:
            out[key] = m.group(1).strip()
    return out


def _tags_from_line(line: str) -> list[str]:
    parts = re.split(r"[,;\n]+", line)
    return [p.strip() for p in parts if p.strip()][:28]


def _normalize_from_sections(
    parts: dict[str, str],
    *,
    fallback_title: str,
    language: str = "en",
) -> dict[str, Any]:
    lang = "ru" if (language or "").lower().startswith("ru") else "en"
    title = normalize_title((parts.get("title") or "").strip(), fallback=fallback_title, max_chars=60)
    desc = (parts.get("description") or "").strip()
    if not desc:
        desc = f"{title}\n\n#Shorts"
    desc = _ensure_description_body_and_hashtags(desc, lang)
    tags_line = (parts.get("tags") or "").strip()
    tags = _tags_from_line(tags_line) if tags_line else []
    tags = normalize_tags(
        _top_up_tags(tags, lang),
        fallback_pool=_TAG_TOPUP_RU if lang == "ru" else _TAG_TOPUP_EN,
        min_count=_MIN_TAGS,
        max_count=_MAX_TAGS,
    )
    first_comment = (parts.get("first_comment") or "").strip()
    hashtags = normalize_hashtags(
        re.findall(r"#[\w\u0400-\u04FF]+", desc),
        fallback_pool=_HASHTAG_TOPUP_RU if lang == "ru" else _HASHTAG_TOPUP_EN,
        min_count=3,
        max_count=5,
    )
    return {
        "title": title,
        "title_variants": [],
        "description": desc,
        "tags": tags,
        "hashtags": hashtags,
        "first_comment": first_comment,
    }


def _normalize_block(
    raw: dict[str, Any],
    *,
    fallback_title: str,
    language: str = "en",
) -> dict[str, Any]:
    """Legacy JSON path (fallback)."""
    title = normalize_title(str(raw.get("title") or "").strip(), fallback=fallback_title, max_chars=60)
    variants = raw.get("title_variants")
    if isinstance(variants, str):
        variants = [variants]
    if not isinstance(variants, list):
        variants = []
    cleaned: list[str] = []
    for x in variants:
        s = str(x).strip()
        if s and s not in cleaned:
            cleaned.append(s)
    while len(cleaned) < 3:
        if len(cleaned) == 0:
            cleaned.append(title)
        else:
            cleaned.append(cleaned[-1])
    cleaned = cleaned[:3]

    lang = "ru" if (language or "").lower().startswith("ru") else "en"
    desc = str(raw.get("description") or "").strip()
    if not desc:
        desc = f"{fallback_title}\n\n#Shorts #quote"
    desc = _ensure_description_body_and_hashtags(desc, lang)

    tags = raw.get("tags")
    if isinstance(tags, str):
        tags = _tags_from_line(tags)
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()][:28]
    tags = normalize_tags(
        _top_up_tags(tags, lang),
        fallback_pool=_TAG_TOPUP_RU if lang == "ru" else _TAG_TOPUP_EN,
        min_count=_MIN_TAGS,
        max_count=_MAX_TAGS,
    )

    hashtags = normalize_hashtags(
        re.findall(r"#[\w\u0400-\u04FF]+", desc),
        fallback_pool=_HASHTAG_TOPUP_RU if lang == "ru" else _HASHTAG_TOPUP_EN,
        min_count=3,
        max_count=5,
    )
    fc = str(raw.get("first_comment") or raw.get("pinned_comment") or "").strip()

    return {
        "title": title,
        "title_variants": cleaned,
        "description": desc,
        "tags": tags,
        "hashtags": hashtags,
        "first_comment": fc,
    }


def format_fallback_title(quote: str, person: str, language: str) -> str:
    q = (quote or "").strip()
    if len(q) > 70:
        q = q[:67] + "…"
    p = (person or "").strip() or ("Author" if language != "ru" else "Автор")
    if language == "ru":
        return f"{p}: {q}" if q else f"Цитата — {p}"
    return f"{p}: {q}" if q else f"Quote — {p}"


def _fallback_block(language: str, quote: str, person: str) -> dict[str, Any]:
    q = (quote or "").strip()[:120]
    p = (person or "").strip() or "Author"
    if language == "ru":
        title = f"Жёсткая правда | {p} (Shorts)"
        if len(title) > 70:
            title = title[:67] + "…"
        desc = (
            f"«{q}» — {p}.\n\n"
            "Короткая цитата — повод остановиться: Писание часто говорит о том, что вера не всегда совпадает с настроением вокруг. "
            "Это не повод закрыться, а повод честно спросить себя, на чём вы стоите.\n\n"
            "Подпишитесь, если хотите больше таких Shorts — без пустых лозунгов, с текстом в центре.\n\n"
            "Что для вас сильнее всего в этих словах — страх, утешение или вызов? Напишите в комментариях.\n\n"
            "#Shorts #Библия #христианство #вера #Иисус #цитата #евангелие #мотивация #СловоБожье"
        )
        tags = [
            "Иисус Христос",
            "христианские Shorts",
            "Библия",
            "стих дня",
            "вера",
            "христианство",
            "евангелие",
            "духовное размышление",
            "библейская цитата",
            "мотивация веры",
            "Слово Божье",
            "христианский контент",
            "Shorts христианство",
            "библейский стих",
            "вера и жизнь",
        ]
        fc = (
            "Иногда одна фраза из Писания перекликается с тем, что вы чувствуете, но не можете сформулировать. "
            "Как эта мысль звучит в вашей ситуации сегодня? Подпишитесь, если заходите за честными короткими размышлениями."
        )
    else:
        title = f"Hard Truth | {p} (Shorts)"
        if len(title) > 70:
            title = title[:67] + "…"
        htag = re.sub(r"[^a-zA-Z0-9]", "", p.replace(" ", ""))[:20] or "faith"
        desc = (
            f"«{q}» — {p}.\n\n"
            "If you've ever felt tension between faith and the world around you, this line from Scripture names that reality — "
            "not to scare you, but so you don't feel alone when it shows up. "
            "Save this Short if you want to revisit it; subscribe for more honest, verse-led moments without fluff.\n\n"
            "What helps you stay steady when faith feels counter-cultural? Drop it below — I'd love to read your story.\n\n"
            "#Shorts #Jesus #Christianity #Faith #BibleVerse #Gospel #ChristianLife #Scripture #Bible"
        )
        tags = [
            "Jesus Christ",
            "Christian Shorts",
            "Bible verse",
            "faith under pressure",
            "Gospel",
            "Scripture",
            htag,
            "Christianity",
            "spiritual growth",
            "daily devotion",
            "Bible study",
            "Jesus teachings",
            "Christian motivation",
            "faith journey",
            "YouTube Shorts faith",
            "biblical truth",
        ]
        fc = (
            "When Jesus spoke about the world's hatred toward His followers, He wasn't inviting fear — He was framing expectations. "
            "How do you pray or act differently when you remember that tension? "
            "Subscribe if you want more Shorts that stay close to the text."
        )
    return _normalize_from_sections(
        {
            "title": title,
            "description": desc,
            "tags": ", ".join(tags),
            "first_comment": fc,
        },
        fallback_title=title,
        language=language,
    )


async def generate_mode4_publishing_metadata(
    *,
    quote_ru: str,
    person_name_ru: str,
    quote_en: str,
    person_name_en: str,
    language: str,
) -> dict[str, Any]:
    """Один язык: ru | en."""
    language = "ru" if language.lower().startswith("ru") else "en"
    fb_q = quote_ru if language == "ru" else quote_en
    fb_p = person_name_ru if language == "ru" else person_name_en
    fallback_title = format_fallback_title(fb_q, fb_p, language)

    try:
        llm = make_llm(temperature=0.65)
        if language == "ru":
            system = SYSTEM_RU
            human = _human_ru(quote_ru, person_name_ru, quote_en, person_name_en)
        else:
            system = SYSTEM_EN
            human = _human_en(quote_ru, person_name_ru, quote_en, person_name_en)
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=human),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=60.0)
        raw_text = response.content.strip() if hasattr(response, "content") else str(response)
        parts = _parse_sections(raw_text, language)
        if parts.get("title") and parts.get("description"):
            return _normalize_from_sections(parts, fallback_title=fallback_title, language=language)
        # Фолбэк: вдруг модель вернула JSON
        data = parse_json_safe(raw_text)
        if isinstance(data, dict) and data.get("title"):
            return _normalize_block(data, fallback_title=fallback_title, language=language)
        raise ValueError("no sections or json title")
    except Exception as e:
        logger.warning(f"[Mode4 Publishing] LLM failed ({language}): {e}")
        return _fallback_block(language, fb_q, fb_p)


async def generate_mode4_publishing_pair(
    *,
    quote_ru: str,
    person_name_ru: str,
    quote_en: str,
    person_name_en: str,
) -> dict[str, Any]:
    """RU + EN блоки для topics_history и API."""
    ru, en = await asyncio.gather(
        generate_mode4_publishing_metadata(
            quote_ru=quote_ru,
            person_name_ru=person_name_ru,
            quote_en=quote_en,
            person_name_en=person_name_en,
            language="ru",
        ),
        generate_mode4_publishing_metadata(
            quote_ru=quote_ru,
            person_name_ru=person_name_ru,
            quote_en=quote_en,
            person_name_en=person_name_en,
            language="en",
        ),
    )
    return {"ru": ru, "en": en}


def build_fallback_publishing_pair(
    quote_ru: str,
    person_name_ru: str,
    quote_en: str,
    person_name_en: str,
) -> dict[str, Any]:
    """Если LLM-задача отменена или упала — всё равно отдаём структуру для UI."""
    return {
        "ru": _fallback_block("ru", quote_ru, person_name_ru),
        "en": _fallback_block("en", quote_en, person_name_en),
    }
