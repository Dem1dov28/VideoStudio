from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm
from utils.publishing_metadata import finalize_metadata, hashtags_from_text

_HASHTAGS_RU = ["#сон", "#релакс", "#медитация", "#успокаивающе", "#sleepvideo"]
_HASHTAGS_EN = ["#sleep", "#relax", "#meditation", "#calm", "#sleepvideo"]
_TAGS_RU = [
    "факты перед сном",
    "успокаивающий рассказ",
    "длинное видео для сна",
    "расслабляющий фон",
    "медленный образовательный контент",
    "sleep facts",
    "calm documentary",
    "ночной релакс",
    "атмосферное видео для сна",
    "background for sleep",
]
_TAGS_EN = [
    "sleep facts",
    "calm documentary",
    "long form sleep video",
    "relaxing narration",
    "ambient educational content",
    "bedtime facts",
    "soft spoken style",
    "night background video",
    "slow paced storytelling",
    "sleep meditation video",
]

_TAGS_BOOK_NIGHT_RU = [
    "пересказ книги",
    "аудиокнига саммари",
    "nonfiction пересказ",
    "книга на ночь слушать",
    "спокойная озвучка",
    "длинное видео книга",
    "саммари бизнес книги",
    "обзор книги спокойно",
    "slow narration russian",
    "book summary video",
    "calm audiobook style",
    "вечернее прослушивание",
]

_TAGS_BOOK_NIGHT_EN = [
    "nonfiction book summary",
    "calm audiobook summary",
    "long form book digest",
    "slow narration",
    "book explained calmly",
    "evening listening",
    "soft spoken book recap",
    "bedtime book listen",
    "author ideas overview",
    "structured book summary",
    "relaxing educational video",
    "nonfiction recap",
]

_PUBLISHING_PROMPT = """Create YouTube metadata for a long-form sleep-oriented video.

VIDEO CONTEXT:
- Topic/title: {topic}
- Sub-mode: {sub_mode}
- Approx duration (minutes): {duration_min}
- Script excerpt: {script_excerpt}

TARGET QUALITY:
- Non-template writing. Sound human, modern, and channel-ready for 2026 YouTube.
- Audience intent: watch before sleep (calm, slow, trustworthy, no hype spam).
- Title: 45-70 chars, no hashtags, clear and searchable, calm curiosity hook.
- Description: 2 short paragraphs, first line instantly explains viewer value.
- Hashtags: 3-5.
- Tags: 10-15 practical YouTube Studio tags, intent-focused, no duplicates.
- first_comment: one engaging, calm CTA question.

Return strict JSON only:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#sleep", "..."],
  "tags": ["...", "..."],
  "first_comment": "..."
}}

Language: {language}
"""

_PUBLISHING_PROMPT_BOOK_NIGHT = """Create YouTube metadata for a long-form **nonfiction book summary** video.

PRIMARY PROMISE (must be obvious in title + first line of description):
- This is a calm, structured **digest / audiobook-style recap** of the book named in the topic — main parts, ideas, and mental models.
- It is **NOT** sleep meditation, hypnosis, or a tutorial on "how to use this book to fall asleep".
- You may mention once, briefly, that the pacing is relaxed and suitable for evening listening — **without** making sleep or meditation the main hook.

VIDEO CONTEXT:
- Book / topic line: {topic}
- Sub-mode: {sub_mode}
- Approx duration (minutes): {duration_min}
- Script excerpt: {script_excerpt}

TARGET QUALITY:
- Non-template writing. Sound human, modern, and channel-ready for 2026 YouTube.
- Audience intent: people who want to **hear the book unpacked** in one sitting (calm voice, no hype).
- Title: 45-72 chars, no hashtags, searchable (book title / recognizable shorthand + hint at summary or calm listen).
- Description: 2 short paragraphs; **lead with what the viewer learns about the book**; second paragraph may note relaxed narration length — still secondary.
- Hashtags: 3-5; prefer book/summary/education; at most **one** generic calm/sleep-adjacent tag if natural — do not stack sleep/meditation tags.
- Tags: 10-15 intent-focused tags mixing **book summary**, **nonfiction**, **audiobook-style**, **calm narration** — not exclusively sleep-video tags.
- first_comment: one calm question about **which book or author** to cover next (not "how do you fall asleep").

Return strict JSON only:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#...", "..."],
  "tags": ["...", "..."],
  "first_comment": "..."
}}

Language: {language}
"""

_THUMBNAIL_PROMPT = """Design one high-quality YouTube thumbnail concept for a sleep-oriented long-form video.

VIDEO CONTEXT:
- Topic/title: {topic}
- Sub-mode: {sub_mode}
- Script excerpt: {script_excerpt}

OUTPUT REQUIREMENTS:
- Return only JSON with key "prompt".
- The prompt must be for generating one cinematic 16:9 thumbnail image.
- Visual style baseline (must be close to this): high-quality whimsical soft-cartoon look, Ghibli-inspired atmosphere, magical but clean.
- Composition baseline (must be close to this): one iconic scene tied to topic + large clean negative space (left half preferred) for title text.
- Typography baseline: large bold rounded bubble-like title text integrated in-scene, white fill with soft dark outline, readable at mobile size.
- Text structure baseline: main hook line + second small sleep line in banner (e.g. "FOR SLEEP"), with tiny sleep icons/stars around text.
- Must be trend-aware for YouTube in 2026: strong focal hierarchy, premium cinematic lighting, zero clutter.
- Calm sleep mood is mandatory (no chaos, no aggressive action, no horror, no bright red alarm palette).
- Keep topic relevance literal and sub-mode aware; avoid generic unrelated scenes.
- One scene only, one frame only, no watermark/logo/UI.

Return strict JSON only:
{{"prompt":"..."}}
"""

# Fixed creative shell for facts50 ("77 facts") publish thumbnails — only scene/title slots vary (English on-image copy).
_FACTS50_THUMBNAIL_TEMPLATE = (
    "A high-quality, whimsical YouTube thumbnail in a soft cartoon style inspired by Studio Ghibli. "
    "The scene is {night_scene}. {landmark_sentence} "
    "In the left half, there is a large, clean negative space for text. "
    "Integrated into this space is large, bold typography using a friendly, rounded, bubble-like font "
    "(white with a soft dark blue outline). "
    'The text reads: "{overlay_title}" (arranged in two lines, with \'77\' being the largest). '
    "Below it, in a slightly smaller, distinct font within a soft blue banner, the text reads: \"FOR SLEEP\". "
    "Small, cute sleeping star icons surround the text. "
    "The overall color palette is deep sapphire, warm amber glows, and pastel purples. "
    "Magical, relaxing atmosphere. 16:9 aspect ratio, cinematic lighting, zero clutter."
)

_FACTS50_THUMB_FIELDS_PROMPT = """You fill thumbnail variables for a sleep-oriented \"77 facts\" YouTube video.

Headline/topic (may be Russian or English):
{topic}

Return strict JSON only with keys:
- "night_scene": short phrase starting with \"a serene, starry night\" and naming the real-world place (city/region) that matches the topic (English).
- "landmark_sentence": ONE English sentence: a stylized gently glowing recognizable landmark from that place stands under a massive smiling crescent moon (match topic; no unrelated countries).
- "overlay_title": English uppercase thumbnail title, format like \"77 FRANCE FACTS\" or \"77 RUSSIA FACTS\" — always starts with 77, ends with FACTS, middle words summarize the topic geography/theme in English (max ~28 chars for the middle part).

Example for France topic: night_scene \"a serene, starry night in Paris\", landmark_sentence \"A stylized, gently glowing Eiffel Tower stands under a massive, smiling crescent moon.\", overlay_title \"77 FRANCE FACTS\".

JSON only, no markdown.
"""

_MODE5_BOOK_THUMBNAIL_SUBMODES = frozenset({"book_night", "unwritten_chapter"})

# Превью с референсом обложки (Open Library): окружение — Ghibli-ночь, сама обложка — как на референсе.
_BOOK_THUMBNAIL_TEMPLATE_REFERENCE_COVER = (
    "A high-quality, whimsical YouTube thumbnail in a soft cartoon style inspired by Studio Ghibli. "
    "The scene is {night_scene}. "
    "REFERENCE IMAGE: the uploaded image is the real published book cover art. "
    "Place it faithfully on the front face of one slightly angled physical hardcover in frame "
    "(preserve the reference artwork, colors, typography, and layout; do not invent a different cover design; "
    "do not painterly-repaint the cover — only integrate lighting shadows and gentle rim light so it sits in the scene). "
    "Do not replace the reference with celebrities, athletes, or unrelated people — only what appears on the reference pixels. "
    "The cozy illustrated treatment applies to the room and atmosphere (shelves, lamp, moon, curtains), not to replacing the cover graphic. "
    "The book is a clear hero focal prop. "
    "In the left half, there is a large, clean negative space for text. "
    "Integrated into this space is large, bold typography using a friendly, rounded, bubble-like font "
    "(white with a soft dark blue outline). "
    'The text reads: "{overlay_title}" (arranged in two lines; emphasize the book title naturally). '
    "Below it, in a slightly smaller, distinct font within a soft blue banner, the text reads: \"FOR SLEEP\". "
    "Small, cute sleeping star icons surround the text. "
    "The overall color palette is deep sapphire, warm amber glows, and pastel purples with cozy reading-lamp warmth. "
    "Magical, relaxing bedtime-story atmosphere. 16:9 aspect ratio, cinematic lighting, zero clutter."
)

# Same thumbnail grammar as facts50 (Ghibli-like whimsical night + typography + FOR SLEEP), adapted for sleep-reading books; cover is mandatory.
_BOOK_THUMBNAIL_TEMPLATE = (
    "A high-quality, whimsical YouTube thumbnail in a soft cartoon style inspired by Studio Ghibli. "
    "The scene is {night_scene}. {cover_sentence} "
    "The composition MUST include one clear, prominent illustrated book cover angled slightly toward the viewer "
    "(whimsical painterly faux-cover art that evokes this specific book's themes and palette — iconic imagery only, "
    "no tiny readable paragraphs on the cover; title wording belongs only in the overlay typography area). "
    "In the left half, there is a large, clean negative space for text. "
    "Integrated into this space is large, bold typography using a friendly, rounded, bubble-like font "
    "(white with a soft dark blue outline). "
    'The text reads: "{overlay_title}" (arranged in two lines; emphasize the book title naturally). '
    "Below it, in a slightly smaller, distinct font within a soft blue banner, the text reads: \"FOR SLEEP\". "
    "Small, cute sleeping star icons surround the text. "
    "The overall color palette is deep sapphire, warm amber glows, and pastel purples with cozy reading-lamp warmth on the book. "
    "Magical, relaxing bedtime-story atmosphere. 16:9 aspect ratio, cinematic lighting, zero clutter."
)

_BOOK_THUMB_FIELDS_PROMPT = """You fill thumbnail variables for a sleep-oriented long-form video based on a BOOK (bedtime listen / slow narration).

Headline / book topic (may be Russian or English, may include author):
{topic}

Return strict JSON only with keys:
- "night_scene": short English phrase — magical serene starry night mood tailored to reading this book (cozy nook, bedside table, quiet library bay window under moonlight, etc.); must feel calm and sleep-friendly.
- "cover_sentence": ONE English sentence describing how the illustrated book cover appears as the hero focal prop (soft glowing edges, gentle tilt, warm lamp or moonlight catching it). Optionally include a massive smiling crescent moon in soft focus through a window or above shelves — keep harmonious with a dreamy thumbnail.
- "overlay_title": English uppercase thumbnail hook derived from the BOOK TITLE only (not author): compact like \"ATOMIC HABITS\" or \"THE SILMARILLION\" — maximum ~26 characters total including spaces; if title is long, abbreviate to strongest 2–4 recognizable words.

JSON only, no markdown.
"""

_BOOK_THUMB_FIELDS_PROMPT_REF_ONLY = """You fill thumbnail variables for a sleep-oriented long-form video based on a BOOK.

The image generator already has the REAL book cover as a reference upload — do not describe an alternate cover.

Headline / book topic (may be Russian or English, may include author):
{topic}

Return strict JSON only with keys:
- "night_scene": short English phrase — magical serene starry night mood tailored to reading this book (cozy nook, bedside table, quiet library bay window under moonlight, etc.); must feel calm and sleep-friendly.
- "overlay_title": English uppercase thumbnail hook derived from the BOOK TITLE only (not author): compact like \"ATOMIC HABITS\" or \"THE SILMARILLION\" — maximum ~26 characters total including spaces; if title is long, abbreviate to strongest 2–4 recognizable words.

JSON only, no markdown.
"""


def _book_thumbnail_fallback_fields(topic: str) -> tuple[str, str, str]:
    raw = re.sub(r"\s+", " ", str(topic or "").strip())
    words = re.findall(r"[A-Za-zÀ-ÿА-Яа-яІіЇїЄєҐґ0-9]+", raw)
    if words:
        overlay = " ".join(words[:5]).upper()
        if len(overlay) > 26:
            overlay = overlay[:26].rsplit(" ", 1)[0] if " " in overlay[:26] else overlay[:26]
    else:
        overlay = "BEDTIME READ"
    night = (
        "a serene, starry night in a cozy reading nook with warm lamplight and shelves softly fading into violet shadow"
    )
    cover = (
        "A tilted illustrated book cover glows as the focal prop beside tea steam and drifting dust motes, "
        "while a gentle crescent moon smiles through the window."
    )
    return night, cover, overlay


def _book_thumbnail_fallback_fields_ref(topic: str) -> tuple[str, str]:
    """Только night_scene + overlay при наличии референса обложки."""
    night, _cover, overlay = _book_thumbnail_fallback_fields(topic)
    return night, overlay


async def _book_modes_thumbnail_prompt(topic: str, *, use_reference_cover: bool = False) -> str:
    base_topic = re.sub(r"\s+", " ", str(topic or "").strip())[:400] or "Book night"
    if use_reference_cover:
        night_scene, overlay_title = _book_thumbnail_fallback_fields_ref(base_topic)
        try:
            model = getattr(settings, "openrouter_model", None)
            llm = make_llm(temperature=0.38, model=model, max_tokens=360)
            response = await asyncio.wait_for(
                llm.ainvoke(
                    [
                        SystemMessage(content="You return only valid JSON objects. No markdown."),
                        HumanMessage(content=_BOOK_THUMB_FIELDS_PROMPT_REF_ONLY.format(topic=base_topic)),
                    ]
                ),
                timeout=28.0,
            )
            data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
            if isinstance(data, dict):
                ns = re.sub(r"\s+", " ", str(data.get("night_scene") or "").strip())
                ot = re.sub(r"\s+", " ", str(data.get("overlay_title") or "").strip()).upper()
                if ns and ot and 3 <= len(ot) <= 34:
                    night_scene, overlay_title = ns, ot
        except Exception as e:
            logger.warning(f"[Mode5 Thumbnail] book_modes (ref cover) field LLM fallback: {e}")
        return _BOOK_THUMBNAIL_TEMPLATE_REFERENCE_COVER.format(
            night_scene=night_scene,
            overlay_title=overlay_title.replace('"', "").strip(),
        )

    night_scene, cover_sentence, overlay_title = _book_thumbnail_fallback_fields(base_topic)
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.38, model=model, max_tokens=420)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content="You return only valid JSON objects. No markdown."),
                    HumanMessage(content=_BOOK_THUMB_FIELDS_PROMPT.format(topic=base_topic)),
                ]
            ),
            timeout=28.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        if isinstance(data, dict):
            ns = re.sub(r"\s+", " ", str(data.get("night_scene") or "").strip())
            cs = re.sub(r"\s+", " ", str(data.get("cover_sentence") or "").strip())
            ot = re.sub(r"\s+", " ", str(data.get("overlay_title") or "").strip()).upper()
            if ns and cs and ot and 3 <= len(ot) <= 34:
                night_scene, cover_sentence, overlay_title = ns, cs, ot
    except Exception as e:
        logger.warning(f"[Mode5 Thumbnail] book_modes field LLM fallback: {e}")
    if not cover_sentence.endswith("."):
        cover_sentence = cover_sentence + "."
    return _BOOK_THUMBNAIL_TEMPLATE.format(
        night_scene=night_scene,
        cover_sentence=cover_sentence.strip(),
        overlay_title=overlay_title.replace('"', "").strip(),
    )


def _facts50_thumbnail_fallback_fields(topic: str) -> tuple[str, str, str]:
    """Cheap fallback when LLM fails: generic night + moon + title from topic words."""
    raw = re.sub(r"\s+", " ", str(topic or "").strip())
    stripped = re.sub(
        r"(?i)^\s*(77\s*)?(facts|фактов)\s*(about|о|об)?\s*",
        "",
        raw,
    ).strip(" —–-:|")
    words = re.findall(r"[A-Za-zÀ-ÿА-Яа-яІіЇїЄєҐґ]+", stripped)
    if words:
        mid = " ".join(words[:4]).upper()
        if len(mid) > 36:
            mid = mid[:36].rsplit(" ", 1)[0] if " " in mid[:36] else mid[:36]
        overlay = f"77 {mid} FACTS"
    else:
        overlay = "77 CALM FACTS"
    night = "a serene, starry night tied to the video topic"
    landmark = (
        "A stylized, gently glowing iconic landmark suggested by the topic "
        "stands under a massive, smiling crescent moon."
    )
    return night, landmark, overlay[:44]


async def _facts50_thumbnail_prompt(topic: str) -> str:
    base_topic = re.sub(r"\s+", " ", str(topic or "").strip())[:400] or "77 facts"
    night_scene, landmark_sentence, overlay_title = _facts50_thumbnail_fallback_fields(base_topic)
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.35, model=model, max_tokens=400)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content="You return only valid JSON objects. No markdown."),
                    HumanMessage(content=_FACTS50_THUMB_FIELDS_PROMPT.format(topic=base_topic)),
                ]
            ),
            timeout=25.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        if isinstance(data, dict):
            ns = re.sub(r"\s+", " ", str(data.get("night_scene") or "").strip())
            ls = re.sub(r"\s+", " ", str(data.get("landmark_sentence") or "").strip())
            ot = re.sub(r"\s+", " ", str(data.get("overlay_title") or "").strip()).upper()
            if ns and ls and ot and ot.startswith("77") and "FACTS" in ot:
                night_scene, landmark_sentence, overlay_title = ns, ls, ot
    except Exception as e:
        logger.warning(f"[Mode5 Thumbnail] facts50 field LLM fallback: {e}")
    if not landmark_sentence.endswith("."):
        landmark_sentence = landmark_sentence + "."
    return _FACTS50_THUMBNAIL_TEMPLATE.format(
        night_scene=night_scene,
        landmark_sentence=landmark_sentence.strip(),
        overlay_title=overlay_title.replace('"', "").strip(),
    )


def _fallback_publish(topic: str, language: str) -> dict[str, Any]:
    lang = str(language or "ru").strip().lower()
    t = re.sub(r"\s+", " ", str(topic or "").strip()) or ("Успокаивающие факты для сна" if lang == "ru" else "Calming Facts for Sleep")
    if lang == "ru":
        return {
            "title": f"{t[:62]}",
            "description": (
                f"{t}. Спокойный формат для вечернего просмотра и мягкого погружения в сон.\n\n"
                "Медленный темп, атмосферная подача и расслабляющий визуальный фон без перегрузки."
            ),
            "hashtags": _HASHTAGS_RU,
            "tags": _TAGS_RU,
            "first_comment": "Какую тему в спокойном формате для сна сделать следующей?",
        }
    if lang == "es":
        return {
            "title": f"{t[:62]}",
            "description": (
                f"{t}. Formato largo y tranquilo para la noche, con ritmo suave y sin sobrecarga.\n\n"
                "Narracion serena, visuales atmosfericos y una presentacion pensada para escuchar con calma."
            ),
            "hashtags": _HASHTAGS_EN,
            "tags": _TAGS_EN,
            "first_comment": "Que tema relajado te gustaria para el siguiente episodio?",
        }
    if lang == "fr":
        return {
            "title": f"{t[:62]}",
            "description": (
                f"{t}. Un format long et calme pour le soir, avec un rythme doux et sans surcharge.\n\n"
                "Narration paisible, visuels atmospheriques et presentation confortable a ecouter."
            ),
            "hashtags": _HASHTAGS_EN,
            "tags": _TAGS_EN,
            "first_comment": "Quel sujet calme voulez-vous pour le prochain episode?",
        }
    if lang == "de":
        return {
            "title": f"{t[:62]}",
            "description": (
                f"{t}. Ruhiges Longform-Format fur den Abend, mit sanftem Tempo und ohne Reizuberflutung.\n\n"
                "Gelassene Erzahlung, atmospharische Bilder und ein entspannter Horfokus."
            ),
            "hashtags": _HASHTAGS_EN,
            "tags": _TAGS_EN,
            "first_comment": "Welches ruhige Thema soll die nachste Folge haben?",
        }
    return {
        "title": f"{t[:62]}",
        "description": (
            f"{t}. A calm long-form format designed for nighttime viewing and easy wind-down.\n\n"
            "Slow pacing, atmospheric visuals, and sleep-friendly narration with no overload."
        ),
        "hashtags": _HASHTAGS_EN,
        "tags": _TAGS_EN,
        "first_comment": "Which sleep-friendly topic should be the next long-form episode?",
    }


_HASHTAGS_BOOK_NIGHT_RU = ["#книги", "#саммари", "#nonfiction", "#спокойно"]
_HASHTAGS_BOOK_NIGHT_EN = ["#booksummary", "#nonfiction", "#calmlisten", "#longform"]


def _fallback_publish_book_night(topic: str, language: str) -> dict[str, Any]:
    lang = str(language or "ru").strip().lower()
    t = re.sub(r"\s+", " ", str(topic or "").strip()) or (
        "Спокойный пересказ книги" if lang == "ru" else "Calm nonfiction book summary"
    )
    if lang == "ru":
        return {
            "title": f"{t[:62]} — спокойный пересказ"[:72],
            "description": (
                f"Спокойный пересказ идей из книги «{t}»: структура, главные мысли и практические акценты в формате "
                "длинной озвучки. Это не медитация и не гид «как уснуть» — просто неспешная подача, удобная для вечера.\n\n"
                "Подходит тем, кто хочет услышать суть издания одним материалом: без скачков и агрессивного монтажа."
            ),
            "hashtags": _HASHTAGS_BOOK_NIGHT_RU,
            "tags": _TAGS_BOOK_NIGHT_RU,
            "first_comment": "Какую nonfiction-книгу или автора разобрать в следующем спокойном пересказе?",
        }
    if lang == "es":
        return {
            "title": f"{t[:56]} — resumen sereno"[:72],
            "description": (
                f"Un resumen tranquilo y extenso del libro de no ficcion «{t}»: estructura, ideas principales y aprendizajes clave. "
                "No es una meditacion para dormir; es una narracion pausada para escuchar con calma por la noche.\n\n"
                "Ideal para quien quiere entender el libro en una sola sesion, sin prisas ni ruido."
            ),
            "hashtags": _HASHTAGS_BOOK_NIGHT_EN,
            "tags": _TAGS_BOOK_NIGHT_EN,
            "first_comment": "Que libro o autor de no ficcion te gustaria para el siguiente resumen?",
        }
    if lang == "fr":
        return {
            "title": f"{t[:56]} — resume calme"[:72],
            "description": (
                f"Un resume long et calme du livre de non-fiction «{t}»: structure, idees principales et points pratiques. "
                "Ce n'est pas une meditation du sommeil, mais une narration douce pour l'ecoute du soir.\n\n"
                "Parfait pour comprendre le livre en une seule session, sans surcharge."
            ),
            "hashtags": _HASHTAGS_BOOK_NIGHT_EN,
            "tags": _TAGS_BOOK_NIGHT_EN,
            "first_comment": "Quel livre ou auteur de non-fiction faut-il resumer ensuite?",
        }
    if lang == "de":
        return {
            "title": f"{t[:56]} — ruhige zusammenfassung"[:72],
            "description": (
                f"Eine ruhige, lange Zusammenfassung des Sachbuchs «{t}»: Struktur, Kerngedanken und praktische Einsichten. "
                "Keine Schlafmeditation, sondern ein gleichmassiger Erzahlrhythmus fur den Abend.\n\n"
                "Ideal, wenn du den Kern des Buches in einer Sitzung verstehen willst."
            ),
            "hashtags": _HASHTAGS_BOOK_NIGHT_EN,
            "tags": _TAGS_BOOK_NIGHT_EN,
            "first_comment": "Welches Sachbuch oder welcher Autor soll als nachstes zusammengefasst werden?",
        }
    return {
        "title": f"{t[:56]} — calm summary"[:72],
        "description": (
            f"A calm long-form summary of the nonfiction book «{t}»: structure, core ideas, and takeaways in audiobook-style narration. "
            "This is not a sleep meditation or a tutorial on falling asleep — just a steady, easy pace for evening listening.\n\n"
            "Best for viewers who want one relaxed sitting that unpacks the book without hype or overload."
        ),
        "hashtags": _HASHTAGS_BOOK_NIGHT_EN,
        "tags": _TAGS_BOOK_NIGHT_EN,
        "first_comment": "Which nonfiction book or author should we summarize calmly next?",
    }


def _finalize(raw: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    title = raw.get("title") or fallback["title"]
    description = raw.get("description") or fallback["description"]
    hashtags = raw.get("hashtags") or hashtags_from_text(description) or fallback["hashtags"]
    tags = raw.get("tags") or fallback["tags"]
    return finalize_metadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags,
        fallback_title=fallback["title"],
        fallback_description=fallback["description"],
        fallback_tags=fallback["tags"],
        fallback_hashtags=fallback["hashtags"],
        first_comment=raw.get("first_comment") or fallback.get("first_comment"),
        title_max_chars=72,
        min_description_chars=180,
        max_description_chars=900,
        min_tags=10,
        max_tags=15,
        min_hashtags=3,
        max_hashtags=5,
    )


def _extract_json_dict(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


async def generate_mode5_publishing_metadata(
    *,
    topic: str,
    sub_mode: str,
    script_excerpt: str,
    duration_min: int,
    language: str = "ru",
) -> dict[str, Any]:
    lang = str(language or "ru").strip().lower()
    if lang not in {"ru", "en", "es", "fr", "de"}:
        lang = "en"
    sm_norm = re.sub(r"\s+", " ", str(sub_mode or "").strip()).lower()
    if sm_norm == "book_night":
        fallback = _fallback_publish_book_night(topic, lang)
        prompt = _PUBLISHING_PROMPT_BOOK_NIGHT.format(
            topic=re.sub(r"\s+", " ", str(topic or "").strip())[:220],
            sub_mode=re.sub(r"\s+", " ", str(sub_mode or "").strip())[:80] or "book_night",
            duration_min=max(1, int(duration_min or 1)),
            script_excerpt=re.sub(r"\s+", " ", str(script_excerpt or "").strip())[:2000],
            language=lang,
        )
        system_meta = (
            "You are a senior YouTube metadata strategist for calm nonfiction book-summary and long-form audiobook-digest channels. "
            "Lead with the book and ideas; sleep/meditation must not dominate. Write natural, modern, non-template metadata."
        )
    else:
        fallback = _fallback_publish(topic, lang)
        prompt = _PUBLISHING_PROMPT.format(
            topic=re.sub(r"\s+", " ", str(topic or "").strip())[:220],
            sub_mode=re.sub(r"\s+", " ", str(sub_mode or "").strip())[:80] or "manual",
            duration_min=max(1, int(duration_min or 1)),
            script_excerpt=re.sub(r"\s+", " ", str(script_excerpt or "").strip())[:2000],
            language=lang,
        )
        system_meta = (
            "You are a senior YouTube metadata strategist for sleep-focused long-form channels. "
            "Write natural, modern, non-template metadata."
        )
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.62, model=model, max_tokens=900)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system_meta),
                    HumanMessage(content=prompt),
                ]
            ),
            timeout=40.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        if isinstance(data, dict):
            return _finalize(data, fallback=fallback)
    except Exception as e:
        logger.warning(f"[Mode5 Publishing] LLM metadata fallback: {e}")
    return _finalize({}, fallback=fallback)


async def generate_mode5_thumbnail_prompt(
    *,
    topic: str,
    sub_mode: str,
    script_excerpt: str,
    use_reference_cover: bool = False,
) -> str:
    base_topic = re.sub(r"\s+", " ", str(topic or "").strip())[:220] or "Sleep facts video"
    sub_mode_clean = re.sub(r"\s+", " ", str(sub_mode or "").strip())[:80] or "manual"
    sm_low = sub_mode_clean.strip().lower()
    if sm_low == "facts50":
        return await _facts50_thumbnail_prompt(base_topic)
    if sm_low in _MODE5_BOOK_THUMBNAIL_SUBMODES:
        return await _book_modes_thumbnail_prompt(base_topic, use_reference_cover=use_reference_cover)
    if re.search(r"\bfacts?\b", base_topic, flags=re.IGNORECASE):
        title_overlay_hint = base_topic.upper()
    else:
        title_overlay_hint = f"{base_topic.upper()}".strip()
    fallback = (
        "A high-quality whimsical YouTube thumbnail in a soft cartoon style inspired by Studio Ghibli. "
        f"Topic: {base_topic}. Sub-mode: {sub_mode_clean}. "
        "Create one iconic topic-related scene with calm magical night mood, cinematic lighting, and deep but clean composition. "
        "Keep a large clean left-side negative space for text. "
        f"Add big rounded title typography: \"{title_overlay_hint}\" and a smaller banner line: \"FOR SLEEP\". "
        "White text with soft dark-blue outline, mobile-readable, zero clutter. 16:9, no watermark/logo/UI."
    )
    prompt = _THUMBNAIL_PROMPT.format(
        topic=base_topic,
        sub_mode=sub_mode_clean,
        script_excerpt=re.sub(r"\s+", " ", str(script_excerpt or "").strip())[:1800],
    )
    try:
        model = getattr(settings, "openrouter_model", None)
        llm = make_llm(temperature=0.68, model=model, max_tokens=700)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(
                        content="You are an elite YouTube thumbnail creative director. Return strict JSON only."
                    ),
                    HumanMessage(content=prompt),
                ]
            ),
            timeout=35.0,
        )
        data = _extract_json_dict(response.content if hasattr(response, "content") else str(response))
        p = re.sub(r"\s+", " ", str((data or {}).get("prompt") or "").strip())
        if p:
            return p
    except Exception as e:
        logger.warning(f"[Mode5 Thumbnail] LLM prompt fallback: {e}")
    return fallback
