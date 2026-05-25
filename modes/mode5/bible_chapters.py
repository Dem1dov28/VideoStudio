"""Detect real Bible book/chapter for Mode5 bible sub-mode overlays (English labels)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MIN_CHAPTER_SLICE_CHARS = 80
_MIN_MARKER_GAP_CHARS = 48

# Longest names first so "1 Samuel" matches before "Samuel".
_MODE5_BIBLE_BOOKS: tuple[str, ...] = (
    "Song of Solomon",
    "1 Chronicles",
    "2 Chronicles",
    "1 Corinthians",
    "2 Corinthians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalms",
    "Proverbs",
    "Ecclesiastes",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "Philemon",
    "Hebrews",
    "James",
    "Jude",
    "Revelation",
)

_BOOK_ALT: dict[str, str] = {
    "gen": "Genesis",
    "exod": "Exodus",
    "lev": "Leviticus",
    "num": "Numbers",
    "deut": "Deuteronomy",
    "matt": "Matthew",
    "mat": "Matthew",
    "mk": "Mark",
    "lk": "Luke",
    "jn": "John",
    "rev": "Revelation",
    "revelation": "Revelation",
}

_BOOKS_PATTERN = "|".join(re.escape(b) for b in _MODE5_BIBLE_BOOKS)
_BOOK_IN_TEXT_RE = re.compile(rf"\b({_BOOKS_PATTERN})\b", re.IGNORECASE)

_OPENING_SIGNATURES: tuple[tuple[re.Pattern[str], str, int], ...] = (
    (re.compile(r"book of the genealogy of jesus christ", re.IGNORECASE), "Matthew", 1),
    (re.compile(r"^in the beginning god created", re.IGNORECASE), "Genesis", 1),
    (re.compile(r"^in the beginning\b", re.IGNORECASE), "Genesis", 1),
    (re.compile(r"^now the birth of jesus christ", re.IGNORECASE), "Matthew", 1),
)

# KJV-style section openings when the pasted text has no "Chapter N" heading.
# If several match one segment, the latest match in the text wins (narration order).
_CHAPTER_BOUNDARY_SIGNATURES: tuple[tuple[re.Pattern[str], str, int], ...] = (
    (re.compile(r"\bnow after jesus was born in bethlehem\b", re.IGNORECASE), "Matthew", 2),
    (re.compile(r"\bwise men from the east came to jerusalem\b", re.IGNORECASE), "Matthew", 2),
    (re.compile(r"\bin those days came john the baptist\b", re.IGNORECASE), "Matthew", 3),
    (re.compile(r"\bjohn the baptist came preaching\b", re.IGNORECASE), "Matthew", 3),
    (re.compile(r"\bthen was jesus led up (?:of|by) the spirit\b", re.IGNORECASE), "Matthew", 4),
    (re.compile(r"\bwhen he saw the multitudes\b", re.IGNORECASE), "Matthew", 5),
    (re.compile(r"\bwhen he had entered capernaum\b", re.IGNORECASE), "Matthew", 8),
)

_CHAPTER_ONLY_RE = re.compile(
    r"\b(?:chapter|ch\.?|глава)\s*(\d{1,3})\b",
    re.IGNORECASE,
)
_BOOK_CHAPTER_RE = re.compile(
    rf"\b({_BOOKS_PATTERN})\s+(?:chapter|ch\.?)\s*(\d{{1,3}})\b",
    re.IGNORECASE,
)
_BOOK_NUM_RE = re.compile(
    rf"\b({_BOOKS_PATTERN})\s+(\d{{1,3}})(?:\s|:|\b)",
    re.IGNORECASE,
)
_VERSE_REF_RE = re.compile(r"\b(\d{1,3}):(\d{1,3})\b")


def _normalize_book(raw: str) -> str | None:
    token = re.sub(r"\s+", " ", (raw or "").strip())
    if not token:
        return None
    low = token.lower()
    if low in _BOOK_ALT:
        return _BOOK_ALT[low]
    for book in _MODE5_BIBLE_BOOKS:
        if book.lower() == low:
            return book
    return token[:40]


def _opening_book_chapter(text: str) -> tuple[str, int] | None:
    for pat, book, chapter in _OPENING_SIGNATURES:
        if pat.search(text):
            return book, chapter
    return None


def _latest_chapter_boundary(text: str, current_book: str | None) -> tuple[str, int] | None:
    """Last known chapter-opening phrase in segment text (for undivided Bible paste)."""
    norm_book = _normalize_book(current_book) if current_book else None
    best_pos = -1
    best: tuple[str, int] | None = None
    for pat, book, chapter in _CHAPTER_BOUNDARY_SIGNATURES:
        if norm_book and norm_book != book:
            continue
        m = pat.search(text)
        if m and m.start() >= best_pos:
            best_pos = m.start()
            best = (book, chapter)
    return best


def infer_bible_book_from_plan(plan: dict[str, Any]) -> str | None:
    parts = [
        str(plan.get("header_title") or ""),
        str(plan.get("script_text") or "")[:800],
        str(plan.get("source_input_text") or "")[:800],
    ]
    blob = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if not blob:
        return None
    opening = _opening_book_chapter(blob)
    if opening:
        return opening[0]
    m = _BOOK_IN_TEXT_RE.search(blob)
    if m:
        return _normalize_book(m.group(1))
    return None


def bible_chapter_label(book: str | None, chapter: int) -> str:
    ch = max(1, int(chapter or 1))
    if book:
        return f"{book} {ch}"
    return f"Chapter {ch}"


def update_bible_chapter_state(
    text: str,
    *,
    book: str | None,
    chapter: int,
) -> tuple[str | None, int, str]:
    """Advance book/chapter state from segment narration; return English overlay label."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return book, chapter, bible_chapter_label(book, chapter)

    # Section openings (e.g. Matt 2:1) before generic Matt 1 openers in the same segment.
    boundary = _latest_chapter_boundary(raw, book)
    if boundary:
        book, chapter = boundary
        return book, chapter, bible_chapter_label(book, chapter)

    opening = _opening_book_chapter(raw)
    if opening:
        book, chapter = opening
        return book, chapter, bible_chapter_label(book, chapter)

    m = _BOOK_CHAPTER_RE.search(raw)
    if m:
        book = _normalize_book(m.group(1))
        chapter = int(m.group(2))
        return book, chapter, bible_chapter_label(book, chapter)

    m = _BOOK_NUM_RE.search(raw)
    if m:
        book = _normalize_book(m.group(1))
        chapter = int(m.group(2))
        return book, chapter, bible_chapter_label(book, chapter)

    m = _CHAPTER_ONLY_RE.search(raw)
    if m:
        chapter = int(m.group(1))
        return book, chapter, bible_chapter_label(book, chapter)

    m = _VERSE_REF_RE.search(raw)
    if m and book:
        chapter = int(m.group(1))
        return book, chapter, bible_chapter_label(book, chapter)

    if not book:
        m = _BOOK_IN_TEXT_RE.search(raw)
        if m:
            book = _normalize_book(m.group(1))

    return book, chapter, bible_chapter_label(book, chapter)


@dataclass(frozen=True)
class BibleChapterSlice:
    book: str | None
    chapter: int
    label: str
    text: str


def _infer_start_book_chapter(text: str) -> tuple[str | None, int]:
    blob = re.sub(r"\s+", " ", (text or "").strip())[:1200]
    if not blob:
        return None, 1
    opening = _opening_book_chapter(blob)
    if opening:
        return opening[0], opening[1]
    m = _BOOK_IN_TEXT_RE.search(blob)
    if m:
        return _normalize_book(m.group(1)), 1
    return None, 1


def _collect_chapter_start_markers(text: str) -> list[tuple[int, str | None, int]]:
    """Positions where a new Bible chapter (or book) begins."""
    book0, ch0 = _infer_start_book_chapter(text)
    markers: list[tuple[int, str | None, int]] = [(0, book0, ch0)]
    cur_book = book0

    def add(pos: int, book: str | None, chapter: int) -> None:
        if pos <= 0:
            return
        b = _normalize_book(book) if book else cur_book
        markers.append((pos, b, max(1, int(chapter))))

    for pat, book, chapter in _CHAPTER_BOUNDARY_SIGNATURES:
        for m in pat.finditer(text):
            add(m.start(), book, chapter)

    for pat, book, chapter in _OPENING_SIGNATURES:
        for m in pat.finditer(text):
            if m.start() > 0:
                add(m.start(), book, chapter)

    for m in _BOOK_CHAPTER_RE.finditer(text):
        add(m.start(), _normalize_book(m.group(1)), int(m.group(2)))

    for m in _CHAPTER_ONLY_RE.finditer(text):
        add(m.start(), cur_book, int(m.group(1)))

    markers.sort(key=lambda x: x[0])
    return markers


def _dedupe_chapter_markers(
    markers: list[tuple[int, str | None, int]],
) -> list[tuple[int, str | None, int]]:
    if not markers:
        return [(0, None, 1)]
    markers = sorted(markers, key=lambda x: x[0])
    out: list[tuple[int, str | None, int]] = []
    last_book: str | None = None
    last_ch = 0
    for pos, book, chapter in markers:
        if not out:
            out.append((pos, book, chapter))
            last_book, last_ch = book, chapter
            continue
        if pos - out[-1][0] < _MIN_MARKER_GAP_CHARS:
            continue
        book_changed = bool(book and last_book and book != last_book)
        chapter_advanced = chapter > last_ch
        if book_changed or chapter_advanced:
            out.append((pos, book or last_book, chapter))
            last_book = book or last_book
            last_ch = chapter
    return out or [(0, None, 1)]


def split_script_into_bible_chapters(script: str) -> list[BibleChapterSlice]:
    """
    Split pasted Bible narration into one part per chapter for parallel TTS.
    Uses explicit headings (Chapter 2) and known KJV section openings when headings are missing.
    """
    text = (script or "").strip()
    if not text:
        return []
    markers = _dedupe_chapter_markers(_collect_chapter_start_markers(text))
    raw_slices: list[BibleChapterSlice] = []
    for i, (start, book, chapter) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        part = text[start:end].strip()
        if not part:
            continue
        raw_slices.append(
            BibleChapterSlice(
                book=book,
                chapter=chapter,
                label=bible_chapter_label(book, chapter),
                text=part,
            )
        )
    if not raw_slices:
        book, chapter = _infer_start_book_chapter(text)
        return [
            BibleChapterSlice(
                book=book,
                chapter=chapter,
                label=bible_chapter_label(book, chapter),
                text=text,
            )
        ]
    merged: list[BibleChapterSlice] = []
    for sl in raw_slices:
        if merged and len(sl.text) < _MIN_CHAPTER_SLICE_CHARS:
            prev = merged[-1]
            merged[-1] = BibleChapterSlice(
                book=prev.book,
                chapter=prev.chapter,
                label=prev.label,
                text=f"{prev.text} {sl.text}".strip(),
            )
        else:
            merged.append(sl)
    return merged


def bible_chapters_payload_from_script(script: str) -> list[dict[str, str]]:
    """Split pasted Bible text into chapter rows for the UI/API."""
    return [
        {"overlay_label": sl.label, "text": sl.text}
        for sl in split_script_into_bible_chapters(script)
    ]


def build_bible_slices_from_explicit_chapters(
    chapters: list[dict[str, Any]],
) -> list[BibleChapterSlice]:
    """One TTS chunk per user-provided chapter; overlay label is shown at the top of the video."""
    slices: list[BibleChapterSlice] = []
    for raw in chapters or []:
        if not isinstance(raw, dict):
            continue
        text = re.sub(r"\s+", " ", str(raw.get("text") or "").strip())
        if not text:
            continue
        overlay = re.sub(
            r"\s+",
            " ",
            str(raw.get("overlay_label") or raw.get("overlayLabel") or "").strip(),
        )
        if not overlay:
            overlay = f"Chapter {len(slices) + 1}"
        slices.append(
            BibleChapterSlice(
                book=None,
                chapter=len(slices) + 1,
                label=overlay[:140],
                text=text,
            )
        )
    return slices


def apply_bible_chapter_labels(plan: dict[str, Any]) -> None:
    """Walk all segments in narration order; set seg['chapter_label'] in English."""
    chunks = sorted(plan.get("chunks") or [], key=lambda c: int(c.get("index") or 0))
    if not chunks:
        return
    if plan.get("bible_locked_labels"):
        for ch in chunks:
            label = re.sub(r"\s+", " ", str(ch.get("chapter_title") or "").strip())
            if not label:
                continue
            segs = sorted((ch.get("segments") or []), key=lambda s: int(s.get("s") or 0))
            for seg in segs:
                seg["chapter_label"] = label[:140]
        return
    book = infer_bible_book_from_plan(plan)
    chapter = 1
    for ch in chunks:
        segs = sorted((ch.get("segments") or []), key=lambda s: int(s.get("s") or 0))
        for seg in segs:
            seg_text = str(seg.get("text") or "").strip()
            book, chapter, label = update_bible_chapter_state(
                seg_text,
                book=book,
                chapter=chapter,
            )
            seg["chapter_label"] = label
        if segs:
            ch["chapter_title"] = str(segs[0].get("chapter_label") or "").strip() or None
