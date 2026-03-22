"""
Multi-source topic fetchers for the Trends Analyzer.

Sources (all free, no API key):
  1. RSS feeds — N+1, Naked Science, ScienceDaily, Phys.org, Popular Mechanics RU
  2. Wikipedia Recent Science articles (search API + summaries)
  3. DuckDuckGo Instant Answer API (fact enrichment)

Design notes:
  - Every fetch is wrapped in try/except so one broken source never kills the pipeline.
  - httpx is used with short timeouts — sources that are slow are skipped.
  - Results are normalised to the same dict shape before returning.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TypedDict

import httpx
from loguru import logger


# ─────────────────────────────────────────────────────────────────────────────
# RSS Science Feeds
# ─────────────────────────────────────────────────────────────────────────────

class RSSItem(TypedDict):
    title: str
    summary: str
    source: str
    lang: str     # "ru" or "en"


_RSS_FEEDS: list[tuple[str, str, str]] = [
    # (label, url, lang) — обновлены нерабочие URL (2025)
    ("N+1",            "https://nplus1.ru/rss",                                  "ru"),
    ("Naked Science",  "https://naked-science.ru/article/category/sci/feed",   "ru"),
    ("Elementy",      "https://old.elementy.ru/rss/news",                      "ru"),
    ("ScienceDaily",   "https://www.sciencedaily.com/rss/all.xml",              "en"),
    ("Nature",         "https://feeds.nature.com/news",                        "en"),
    ("Ars Technica",   "https://feeds.arstechnica.com/arstechnica/science",    "en"),
]

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


async def fetch_rss_topics(
    max_per_feed: int = 12,
    timeout: float = 7.0,
) -> list[RSSItem]:
    """
    Fetch recent article titles from trusted science RSS feeds.
    Returns a flat list of RSSItem dicts.
    """
    items: list[RSSItem] = []

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=_RSS_HEADERS
    ) as client:
        for label, url, lang in _RSS_FEEDS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)

                # Handle both RSS 2.0 and Atom
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = (
                    root.findall(".//item")           # RSS 2.0
                    or root.findall(".//atom:entry", ns)  # Atom
                )

                count = 0
                for entry in entries[:max_per_feed]:
                    title_el = entry.find("title")
                    desc_el  = entry.find("description") or entry.find("atom:summary", ns)
                    title = title_el.text.strip() if title_el is not None and title_el.text else ""
                    desc  = desc_el.text.strip()  if desc_el  is not None and desc_el.text  else ""

                    # Strip HTML tags from description
                    desc = _strip_html(desc)[:300]

                    if title:
                        items.append(RSSItem(
                            title=title,
                            summary=desc,
                            source=label,
                            lang=lang,
                        ))
                        count += 1

                logger.debug(f"[Sources] {label}: {count} items")

            except Exception as exc:
                logger.debug(f"[Sources] RSS {label} failed: {exc}")

    logger.info(f"[Sources] RSS total: {len(items)} articles from {len(_RSS_FEEDS)} feeds")
    return items


def _strip_html(text: str) -> str:
    """Quick HTML tag removal without dependencies."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return " ".join(text.split())


# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia API
# ─────────────────────────────────────────────────────────────────────────────

_WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
_WIKI_SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"


_WIKI_HEADERS = {
    "User-Agent": "ContentFactory/1.0 (educational research bot; contact@example.com)",
    "Accept": "application/json",
}


async def search_wikipedia(
    query: str,
    lang: str = "ru",
    limit: int = 3,
    timeout: float = 8.0,
) -> list[dict]:
    """
    Search Wikipedia and return page summaries.

    Returns list of dicts: {title, extract, url}
    """
    results: list[dict] = []
    api_url = _WIKI_API.format(lang=lang)

    async with httpx.AsyncClient(timeout=timeout, headers=_WIKI_HEADERS) as client:
        # Step 1: search
        try:
            resp = await client.get(api_url, params={
                "action":   "query",
                "list":     "search",
                "srsearch": query,
                "srlimit":  limit,
                "format":   "json",
                "utf8":     1,
            })
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("query", {}).get("search", [])
        except Exception as exc:
            logger.debug(f"[Sources] Wikipedia search ({lang}) failed: {exc}")
            return []

        # Step 2: fetch summaries for top results
        for page in pages[:limit]:
            title = page.get("title", "")
            if not title:
                continue
            try:
                summary_url = _WIKI_SUMMARY.format(
                    lang=lang,
                    title=httpx.URL(title).path,   # URL-encode title
                )
                # Use params encoding via httpx
                summ_resp = await client.get(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
                )
                if summ_resp.status_code == 200:
                    d = summ_resp.json()
                    results.append({
                        "title":   d.get("title", title),
                        "extract": d.get("extract", "")[:600],
                        "url":     d.get("content_urls", {}).get("desktop", {}).get("page", ""),
                        "lang":    lang,
                    })
            except Exception:
                pass

    return results


# ─────────────────────────────────────────────────────────────────────────────
# DuckDuckGo Instant Answer
# ─────────────────────────────────────────────────────────────────────────────

async def ddg_instant_answer(query: str, timeout: float = 6.0) -> str:
    """
    Query the DuckDuckGo Instant Answer API.
    Returns a short text abstract, or empty string if nothing found.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q":            query,
                    "format":       "json",
                    "no_html":      "1",
                    "skip_disambig": "1",
                },
                headers={"User-Agent": "ContentFactory/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            abstract = data.get("AbstractText") or data.get("Answer") or ""
            return abstract[:800]
    except Exception as exc:
        logger.debug(f"[Sources] DDG instant answer failed: {exc}")
        return ""
