"""Загрузка обложки книги для превью публикации (Open Library — без API-ключа)."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import httpx
from loguru import logger

_OL_SEARCH = "https://openlibrary.org/search.json"
_DEFAULT_UA = "VideoEditor/1.0 (mode5 thumbnail; openlibrary.org covers)"

# Слишком короткие совпадения дают ложные попадания (напр. «он» в названии).
_MIN_KW_LEN = 4
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "book",
        "night",
        "sleep",
        "read",
        "audiobook",
        "edition",
        "volume",
        "part",
        "книга",
        "книги",
        "ночь",
        "ночи",
        "для",
        "при",
        "этот",
        "эта",
        "автор",
        "издание",
        "глава",
        "часть",
    }
)


def _clean_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", str(topic or "").strip())


def _tokenize_meaningful(text: str) -> list[str]:
    """Слова для матчинга с полем title (латиница + кириллица)."""
    raw = (text or "").lower()
    words = re.findall(r"[a-zа-яёіїєґ]{3,}", raw, flags=re.IGNORECASE)
    out: list[str] = []
    for w in words:
        wl = w.lower()
        if wl in _STOPWORDS:
            continue
        if len(wl) < _MIN_KW_LEN:
            continue
        out.append(wl)
    return out


def _extract_title_phrases(topic: str) -> list[str]:
    """Кандидаты «название до запятой / тире» + целая строка."""
    t = _clean_topic(topic)
    if not t:
        return []
    parts: list[str] = [t]
    for sep in (",", " — ", " – ", " —", "– ", " - ", ": "):
        if sep in t:
            head = t.split(sep, 1)[0].strip()
            if len(head) >= 4:
                parts.insert(0, head)
            break
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        key = p.casefold()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out[:5]


def _doc_text_blob(doc: dict) -> str:
    chunks: list[str] = []
    title = doc.get("title")
    if isinstance(title, list):
        chunks.extend(str(x) for x in title if x)
    elif isinstance(title, str) and title.strip():
        chunks.append(title)
    auth = doc.get("author_name")
    if isinstance(auth, list):
        chunks.extend(str(a) for a in auth if a)
    elif isinstance(auth, str) and auth.strip():
        chunks.append(auth)
    return " ".join(chunks).lower()


def _score_doc(doc: dict, keywords: list[str], phrases: list[str]) -> float:
    blob = _doc_text_blob(doc)
    if not blob.strip():
        return 0.0
    score = 0.0
    for ph in phrases:
        pl = ph.strip().lower()
        if len(pl) >= 8 and pl in blob:
            score += 14.0
        elif len(pl) >= 5:
            # несколько слов фразы как подстроки
            toks = _tokenize_meaningful(pl)
            if toks and sum(1 for x in toks if x in blob) >= min(2, len(toks)):
                score += 10.0
    for kw in keywords:
        if kw in blob:
            score += max(2.0, min(8.0, len(kw) * 0.6))
    return score


def _cover_id_and_isbn(doc: dict) -> tuple[int | None, str | None]:
    cid = doc.get("cover_i")
    cover_i = int(cid) if isinstance(cid, int) and cid > 0 else None
    ib = doc.get("isbn")
    raw_isbn: str | None = None
    if isinstance(ib, list) and ib:
        raw_isbn = str(ib[0]).strip().replace("-", "").replace(" ", "")
    elif isinstance(ib, str) and ib.strip():
        raw_isbn = ib.strip().replace("-", "").replace(" ", "")
    if raw_isbn is not None and len(raw_isbn) < 10:
        raw_isbn = None
    return cover_i, raw_isbn


def _search_openlibrary(q: str, *, limit: int, headers: dict[str, str], timeout: float) -> list[dict]:
    params = urllib.parse.urlencode({"q": q, "limit": str(limit)})
    try:
        r = httpx.get(f"{_OL_SEARCH}?{params}", headers=headers, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.warning(f"[OpenLibrary] search failed q={q[:80]!r}: {e}")
        return []
    docs = payload.get("docs") if isinstance(payload, dict) else None
    if not isinstance(docs, list):
        return []
    return [d for d in docs if isinstance(d, dict)]


def try_fetch_openlibrary_cover(topic: str, dest: Path, *, timeout: float = 22.0) -> bool:
    """
    Ищет книгу по строке запроса и сохраняет обложку в dest (JPEG).
    Берёт издание с наилучшим совпадением title/автора с запросом — не первое попавшееся в выдаче.
    """
    q_base = _clean_topic(topic)[:280]
    if len(q_base) < 3:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": _DEFAULT_UA}

    phrases = _extract_title_phrases(q_base)
    keywords = _tokenize_meaningful(q_base)
    # Уникальные ключевые слова, порядок сохраняем
    kw_ordered: list[str] = []
    seen_kw: set[str] = set()
    for k in keywords:
        if k not in seen_kw:
            seen_kw.add(k)
            kw_ordered.append(k)

    queries: list[str] = [q_base]
    # Узкий поиск по названию (часто точнее общего q=)
    for ph in phrases:
        pt = ph.strip()
        if len(pt) >= 6:
            queries.append(f'title:"{pt}"')
        if len(pt) >= 10:
            queries.append(f"title:{pt}")

    merged: list[dict] = []
    sig_seen: set[tuple[int | None, str, str]] = set()
    for sq in queries:
        for doc in _search_openlibrary(sq, limit=28, headers=headers, timeout=timeout):
            ci, isn = _cover_id_and_isbn(doc)
            if ci is None and isn is None:
                continue
            sig = (ci, isn or "", _doc_text_blob(doc)[:120])
            if sig in sig_seen:
                continue
            sig_seen.add(sig)
            merged.append(doc)

    if not merged:
        logger.info("[OpenLibrary] no docs with cover_i/isbn for thumbnail")
        return False

    best_doc: dict | None = None
    best_score = -1.0
    for doc in merged:
        sc = _score_doc(doc, kw_ordered, phrases)
        if sc > best_score:
            best_score = sc
            best_doc = doc

    # Порог: иначе лучше без референса, чем обложка «Месси» для Atomic Habits
    min_score = 5.0 if len(kw_ordered) >= 2 else 4.0
    if kw_ordered:
        min_score = max(min_score, min(10.0, 2.0 + 1.8 * min(len(kw_ordered), 4)))

    if best_doc is None or best_score < min_score:
        logger.warning(
            f"[OpenLibrary] no confident edition match for thumbnail "
            f"(best_score={best_score:.1f} < min={min_score:.1f}; keywords={kw_ordered[:8]}). "
            "Skipping reference cover to avoid wrong art."
        )
        return False

    picked_title = _doc_text_blob(best_doc)[:100]
    ci, isn = _cover_id_and_isbn(best_doc)
    logger.info(f"[OpenLibrary] thumbnail cover pick score={best_score:.1f} title_blob={picked_title!r} cover_i={ci}")

    if ci is not None:
        url = f"https://covers.openlibrary.org/b/id/{ci}-L.jpg"
        ok = _download_cover(url, dest, headers, timeout)
        if ok:
            return True
    if isn:
        url = f"https://covers.openlibrary.org/b/isbn/{isn}-L.jpg"
        return _download_cover(url, dest, headers, timeout)
    return False


def _download_cover(url: str, dest: Path, headers: dict[str, str], timeout: float) -> bool:
    try:
        r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            logger.debug(f"[OpenLibrary] cover HTTP {r.status_code} for {url}")
            return False
        data = r.content
        if len(data) < 900:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        if ct and "image" not in ct:
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        logger.warning(f"[OpenLibrary] cover download failed: {e}")
        return False
