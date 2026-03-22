"""
Trends Analyzer Agent  (v2 — multi-source + Излом channel scoring).

Data pipeline:
  1. Google Trends (pytrends) — real-time searches in Russia
  2. Science RSS feeds — N+1, Naked Science, ScienceDaily, Phys.org, Ars Technica
  3. Wikipedia search — for topic depth and reliability signal
  LLM then scores ALL collected topics for the "Излом" channel:
    - How counterintuitive / mind-blowing is the potential fact angle?
    - How well does it fit the "breaks-your-logic" format?
    - Does it have beautiful visual potential?
  Fallback: LLM generates fresh evergreen topics if every external source fails.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from utils.llm import make_llm
from agents.trends_analyzer.sources import fetch_rss_topics, search_wikipedia


# ─────────────────────────────────────────────────────────────────────────────
# Typed output
# ─────────────────────────────────────────────────────────────────────────────

class TrendingTopic(TypedDict):
    topic: str            # e.g. "Нейтронные звёзды"
    category: str         # e.g. "Космос"
    why_trending: str     # Why it's interesting / in the news now
    video_angle: str      # Specific "Излом"-framed video concept
    izlom_hook: str       # The single most mind-blowing counterintuitive sentence
    score: int            # 1-10 overall suitability
    izlom_score: int      # 1-10 counterintuitive / "breaks logic" factor
    sources: list[str]    # Which sources mentioned this


# ─────────────────────────────────────────────────────────────────────────────
# Google Trends (unchanged from v1, with urllib3 patch)
# ─────────────────────────────────────────────────────────────────────────────

def _patch_urllib3_retry() -> None:
    try:
        import urllib3.util.retry as _retry
        import inspect
        sig = inspect.signature(_retry.Retry.__init__)
        if "method_whitelist" not in sig.parameters:
            orig = _retry.Retry.__init__
            def patched(self, *a, method_whitelist=None, **kw):
                if method_whitelist is not None and "allowed_methods" not in kw:
                    kw["allowed_methods"] = method_whitelist
                orig(self, *a, **kw)
            _retry.Retry.__init__ = patched
    except Exception:
        pass


def _fetch_google_trends(geo: str = "RU", top_n: int = 20) -> list[str]:
    try:
        _patch_urllib3_retry()
        from pytrends.request import TrendReq
        pt = TrendReq(hl="ru-RU", tz=180, timeout=(10, 25))
        df = pt.trending_searches(pn="russia")
        topics = df[0].tolist()[:top_n]
        logger.info(f"[TrendsAgent] Google Trends: {len(topics)} topics")
        return topics
    except Exception as e:
        logger.warning(f"[TrendsAgent] Google Trends failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# LLM scoring — "Излом" channel
# ─────────────────────────────────────────────────────────────────────────────

_IZLOM_SCORE_SYSTEM = """Ты — контент-стратег научно-популярного канала для TikTok/YouTube Shorts.

Формат строго такой: "Топ-5 фактов о <теме>".
Нужны 5 разных коротких верифицируемых фактов, которые легко показать в видео.

Тебе дан список тем из разных источников (Google Trends, RSS-ленты науки, Wikipedia).
Для каждой темы определи:

1. Подходит ли тема для набора из 5 фактов (1-10, "izlom_score"):
   - 10: можно придумать 5 фактов с конкретикой и визуалом
   - 6-9: подходит, часть фактов может быть менее наглядной
   - <6: плохо подходит

2. Общая оценка SHORT-VIDEO (1-10, "score"):
   - визуальный потенциал AI-изображений
   - доступность
   - вирусность

3. video_angle: строго в формате "Топ-5 фактов о <теме>" (≤10 слов)

4. izlom_hook: одно предложение ≤12 слов, где явно зашит формат "Топ-5 фактов о ...".

5. why_trending: почему актуально сейчас (1 предложение, русский)

6. category: одна из категорий ниже

ВАЖНО:
- Отбирай только темы с izlom_score ≥ 6
- Приоритет: Наука, Космос, Биология, Физика, Психология, История
- Избегай: политика, спорт, шоу-бизнес, местные события

Верни JSON array (топ-5 по izlom_score), без markdown:
[
  {
    "topic": "название темы (без префикса)",
    "category": "Наука | Технологии | Природа | История | Психология | Здоровье | Космос | Биология | Физика",
    "why_trending": "почему актуально сейчас (1 предложение, русский)",
    "video_angle": "Топ-5 фактов о <теме>",
    "izlom_hook": "Топ-5 фактов о <теме>: ...",
    "score": 8,
    "izlom_score": 9,
    "sources": ["N+1", "Google Trends"]
  }
]
Верни ТОЛЬКО валидный JSON array."""


async def _score_topics_izlom(
    topics: list[dict],   # each has "title", "summary", "source"
) -> list[TrendingTopic]:
    if not topics:
        return []

    llm = make_llm(temperature=0.3)

    # Format topics for the prompt
    lines = []
    for t in topics[:40]:   # cap at 40 to stay within context
        src = t.get("source", "?")
        summ = t.get("summary", "")
        if summ:
            lines.append(f"[{src}] {t['title']} — {summ[:120]}")
        else:
            lines.append(f"[{src}] {t['title']}")

    messages = [
        SystemMessage(content=_IZLOM_SCORE_SYSTEM),
        HumanMessage(content="Темы:\n" + "\n".join(lines)),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        scored: list[TrendingTopic] = json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("["), raw.rfind("]") + 1
        if s != -1 and e > s:
            scored = json.loads(raw[s:e])
        else:
            logger.error(f"[TrendsAgent] Parse error: {raw[:300]}")
            return []

    # Ensure sources field exists
    for t in scored:
        t.setdefault("sources", [])
        t.setdefault("izlom_hook", t.get("video_angle", ""))
        t.setdefault("izlom_score", t.get("score", 5))

    scored.sort(key=lambda x: x.get("izlom_score", 0), reverse=True)
    logger.info(f"[TrendsAgent] Scored {len(scored)} topics for Top-5 facts format")
    for t in scored[:3]:
        logger.debug(
            f"  izlom={t['izlom_score']}/10 score={t['score']}/10 "
            f"| {t['topic']} — {t.get('izlom_hook', '')[:80]}"
        )
    return scored


# ─────────────────────────────────────────────────────────────────────────────
# LLM scoring — "Почему X?" (Mode 2)
# ─────────────────────────────────────────────────────────────────────────────

_WHY_SCORE_SYSTEM = """Ты — контент-стратег для формата "Почему X?" — 5 коротких вопросов с ответами.

Формат: каждая тема → 5 вопросов вида "Почему <что-то>?" с короткими ответами.
Пример: тема "животные" → "Почему собаки виляют хвостом?", "Почему кошки мурлыкают?" и т.д.

Тебе дан список тем из Google Trends, RSS, Wikipedia.
Для каждой темы определи:

1. why_score (1-10): насколько тема подходит для 5 разных "Почему"-вопросов
   - 10: широкая тема, легко придумать 5 конкретных вопросов с интересными ответами
   - 6-9: подходит
   - <6: узкая тема или сложно сформулировать вопросы

2. score (1-10): визуальный потенциал для видео, вирусность

3. video_angle: краткая формулировка для сценариста, напр. "животные", "сон", "военная история" (1-4 слова)

4. topic: обобщённая тема (без префикса "Почему")

5. why_trending: почему интересно сейчас

6. category: Наука | Природа | Животные | Психология | История | Здоровье | Технологии

ВАЖНО:
- Нужны ШИРОКИЕ темы (животные, сон, природа), а не узкие (одно конкретное явление)
- Отбирай только why_score ≥ 6
- Избегай: политика, шоу-бизнес, местные события

Верни JSON array (топ-5 по why_score), без markdown:
[
  {
    "topic": "животные",
    "category": "Животные",
    "why_trending": "вечная тема с неожиданными фактами",
    "video_angle": "животные",
    "izlom_hook": "Почему собаки виляют хвостом? 5 ответов",
    "score": 8,
    "izlom_score": 9,
    "sources": ["Google Trends"]
  }
]
Верни ТОЛЬКО валидный JSON array. Поле izlom_score = why_score для совместимости."""


async def _score_topics_why(topics: list[dict]) -> list[TrendingTopic]:
    """Score raw topics for «Почему X?» format."""
    if not topics:
        return []

    llm = make_llm(temperature=0.3)
    lines = []
    for t in topics[:40]:
        src = t.get("source", "?")
        summ = t.get("summary", "")
        if summ:
            lines.append(f"[{src}] {t['title']} — {summ[:120]}")
        else:
            lines.append(f"[{src}] {t['title']}")

    messages = [
        SystemMessage(content=_WHY_SCORE_SYSTEM),
        HumanMessage(content="Темы:\n" + "\n".join(lines)),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        scored: list[TrendingTopic] = json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("["), raw.rfind("]") + 1
        if s != -1 and e > s:
            scored = json.loads(raw[s:e])
        else:
            logger.error(f"[TrendsAgent-Mode2] Parse error: {raw[:300]}")
            return []

    for t in scored:
        t.setdefault("sources", [])
        t.setdefault("izlom_hook", t.get("video_angle", ""))
        t.setdefault("izlom_score", t.get("score", 5))
        t.setdefault("video_angle", t.get("topic", ""))

    scored.sort(key=lambda x: x.get("izlom_score", 0), reverse=True)
    logger.info(f"[TrendsAgent-Mode2] Scored {len(scored)} topics for Почему X? format")
    return scored


_FALLBACK_WHY_SYSTEM = """Ты — контент-стратег для формата "Почему X?".

Сгенерируй {n} ШИРОКИХ тем, подходящих для 5 разных вопросов "Почему <что-то>?" с короткими ответами.

Требования:
- Тема должна быть широкая (животные, сон, природа), а не одно явление
- Легко придумать 5 конкретных "Почему"-вопросов
- Хороший визуальный потенциал для видео

Примеры тем: животные, сон, военная история, природа, человеческий мозг, еда, космос

Верни JSON array, без markdown:
[
  {{
    "topic": "животные",
    "category": "Животные",
    "why_trending": "вечная тема",
    "video_angle": "животные",
    "izlom_hook": "Почему X? — животные",
    "score": 9,
    "izlom_score": 9,
    "sources": ["LLM-generated"]
  }}
]"""


async def _generate_fallback_why(n: int = 6) -> list[TrendingTopic]:
    llm = make_llm(temperature=0.9)
    system = _FALLBACK_WHY_SYSTEM.replace("{n}", str(n))
    messages = [
        SystemMessage(content=system),
        HumanMessage(content="Генерируй темы для формата «Почему X?» — 5 вопросов с ответами."),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    try:
        topics: list[TrendingTopic] = json.loads(raw)
        for t in topics:
            t.setdefault("sources", ["LLM-generated"])
            t.setdefault("izlom_score", t.get("score", 7))
            t.setdefault("izlom_hook", t.get("video_angle", ""))
        topics.sort(key=lambda x: x.get("izlom_score", 0), reverse=True)
        return topics
    except Exception:
        s, e = raw.find("["), raw.rfind("]") + 1
        if s != -1 and e > s:
            return json.loads(raw[s:e])
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: LLM generates fresh "Излом" topics
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_SYSTEM = """Ты — контент-стратег научно-популярного канала для TikTok/YouTube Shorts.

Сгенерируй {n} КОНКРЕТНЫХ тем в формате строго "Топ-5 фактов о <теме>".
Каждая тема должна позволять сформулировать 5 коротких верифицируемых фактов.

Требования:
- Тема должна быть реальной и задокументированной (наука, история, биология, физика)
- Визуальный потенциал: можно создать захватывающие AI-изображения

Примеры тем:
- "Нейтронные звёзды"
- "Время и скорость"
- "Акулы"
- "Мозг и решения"

Верни JSON array, без markdown:
[
  {{
    "topic": "название (без префикса)",
    "category": "Наука | Космос | Биология | Физика | Психология | История",
    "why_trending": "почему интересно сейчас (1 пред., русский)",
    "video_angle": "Топ-5 фактов о <теме>",
    "izlom_hook": "Топ-5 фактов о <теме>: ...",
    "score": 9,
    "izlom_score": 9,
    "sources": ["LLM-generated"]
  }}
]"""


async def _generate_fallback_izlom(n: int = 6) -> list[TrendingTopic]:
    llm = make_llm(temperature=0.9)
    system = _FALLBACK_SYSTEM.replace("{n}", str(n))
    messages = [
        SystemMessage(content=system),
        HumanMessage(content="Генерируй свежие, максимально контринтуитивные темы на сегодня."),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    try:
        topics: list[TrendingTopic] = json.loads(raw)
        for t in topics:
            t.setdefault("sources", ["LLM-generated"])
            t.setdefault("izlom_score", t.get("score", 7))
            t.setdefault("izlom_hook", t.get("video_angle", ""))
        topics.sort(key=lambda x: x.get("izlom_score", 0), reverse=True)
        return topics
    except Exception:
        s, e = raw.find("["), raw.rfind("]") + 1
        if s != -1 and e > s:
            return json.loads(raw[s:e])
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def run_trends_agent(
    top_n: int = 1,
    geo: str = "RU",
    use_fallback_if_empty: bool = True,
) -> list[TrendingTopic]:
    """
    Fetch, aggregate, and rank trending topics for the «Излом» channel.

    Multi-source pipeline:
      1. Google Trends (real-time Russia)
      2. Science RSS feeds (N+1, ScienceDaily, Phys.org …)
      3. LLM ranks all combined topics by Излом-factor

    Args:
        top_n:               How many topics to return (usually 1 for pipeline, 5 for UI preview).
        geo:                 Country for Google Trends.
        use_fallback_if_empty: If all external sources fail, generate with LLM.

    Returns:
        List of TrendingTopic sorted by izlom_score descending.
    """
    logger.info("[TrendsAgent] Fetching topics from all sources …")

    all_raw: list[dict] = []  # unified: {title, summary, source}

    # ── Source 1: Google Trends ───────────────────────────────────────────────
    try:
        gt = _fetch_google_trends(geo=geo)
        all_raw += [{"title": t, "summary": "", "source": "Google Trends"} for t in gt]
    except Exception as exc:
        logger.warning(f"[TrendsAgent] Google Trends error: {exc}")

    # ── Source 2: Science RSS feeds ───────────────────────────────────────────
    try:
        rss = await fetch_rss_topics(max_per_feed=10)
        all_raw += [
            {"title": r["title"], "summary": r["summary"], "source": r["source"]}
            for r in rss
        ]
    except Exception as exc:
        logger.warning(f"[TrendsAgent] RSS feeds error: {exc}")

    # ── Source 3: Wikipedia (search for science topics from Google Trends) ────
    if all_raw:
        # Search Wikipedia for top 5 Google Trends topics to enrich context
        gt_titles = [t["title"] for t in all_raw if t["source"] == "Google Trends"][:5]
        for title in gt_titles:
            try:
                wiki_results = await search_wikipedia(title, lang="ru", limit=1)
                for w in wiki_results:
                    all_raw.append({
                        "title":   w["title"],
                        "summary": w["extract"][:200],
                        "source":  "Wikipedia",
                    })
            except Exception:
                pass

    logger.info(f"[TrendsAgent] Collected {len(all_raw)} raw topics from all sources")

    # ── Score & rank ──────────────────────────────────────────────────────────
    scored: list[TrendingTopic] = []
    if all_raw:
        scored = await _score_topics_izlom(all_raw)

    # ── Fallback: LLM generates evergreen topics ──────────────────────────────
    if not scored and use_fallback_if_empty:
        logger.info("[TrendsAgent] No external data — using LLM-generated topics")
        scored = await _generate_fallback_izlom(n=max(top_n + 3, 6))

    if not scored:
        raise RuntimeError("[TrendsAgent] Could not find any topics")

    # ── Filter out already-used topics ────────────────────────────────────────
    from agents.topics_history import filter_unused_topics
    scored = filter_unused_topics(scored, topic_key="topic", angle_key="video_angle")

    result = scored[:top_n]
    for t in result:
        logger.success(
            f"[TrendsAgent] Selected: izlom={t['izlom_score']}/10 | "
            f"{t['topic']} | hook: {t.get('izlom_hook', '')[:70]}"
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Mode 2: «Почему X?» trends agent
# ─────────────────────────────────────────────────────────────────────────────

async def run_trends_agent_mode2(
    top_n: int = 1,
    geo: str = "RU",
    use_fallback_if_empty: bool = True,
) -> list[TrendingTopic]:
    """
    Fetch and rank trending topics for format «Почему X?» — 5 Q&A questions.

    Uses same data sources as run_trends_agent, but different LLM scoring:
    - Prefers broad themes (животные, сон, природа) suitable for 5 different "Почему"-questions
    - video_angle = short theme for scenario writer (e.g. "животные")

    Args:
        top_n: How many topics to return.
        geo: Country for Google Trends.
        use_fallback_if_empty: If all external sources fail, generate with LLM.

    Returns:
        List of TrendingTopic sorted by izlom_score (why_score) descending.
    """
    logger.info("[TrendsAgent-Mode2] Fetching topics for Почему X? format …")

    all_raw: list[dict] = []

    try:
        gt = _fetch_google_trends(geo=geo)
        all_raw += [{"title": t, "summary": "", "source": "Google Trends"} for t in gt]
    except Exception as exc:
        logger.warning(f"[TrendsAgent-Mode2] Google Trends error: {exc}")

    try:
        rss = await fetch_rss_topics(max_per_feed=10)
        all_raw += [
            {"title": r["title"], "summary": r["summary"], "source": r["source"]}
            for r in rss
        ]
    except Exception as exc:
        logger.warning(f"[TrendsAgent-Mode2] RSS feeds error: {exc}")

    if all_raw:
        gt_titles = [t["title"] for t in all_raw if t["source"] == "Google Trends"][:5]
        for title in gt_titles:
            try:
                wiki_results = await search_wikipedia(title, lang="ru", limit=1)
                for w in wiki_results:
                    all_raw.append({
                        "title": w["title"],
                        "summary": w["extract"][:200],
                        "source": "Wikipedia",
                    })
            except Exception:
                pass

    logger.info(f"[TrendsAgent-Mode2] Collected {len(all_raw)} raw topics")

    scored: list[TrendingTopic] = []
    if all_raw:
        scored = await _score_topics_why(all_raw)

    if not scored and use_fallback_if_empty:
        logger.info("[TrendsAgent-Mode2] No external data — using LLM-generated topics")
        scored = await _generate_fallback_why(n=max(top_n + 3, 6))

    if not scored:
        raise RuntimeError("[TrendsAgent-Mode2] Could not find any topics")

    from agents.topics_history import filter_unused_topics
    scored = filter_unused_topics(scored, topic_key="topic", angle_key="video_angle")

    result = scored[:top_n]
    for t in result:
        logger.success(
            f"[TrendsAgent-Mode2] Selected: why={t['izlom_score']}/10 | "
            f"{t.get('topic', t.get('video_angle', ''))}"
        )
    return result
