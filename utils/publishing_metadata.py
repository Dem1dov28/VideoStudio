from __future__ import annotations

import re
from typing import Any


def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def _dedupe_keep_order(items: list[str], *, key_lower: bool = True) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item or "").strip()
        if not s:
            continue
        k = s.lower() if key_lower else s
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def normalize_title(
    title: str,
    *,
    fallback: str,
    max_chars: int = 58,
) -> str:
    s = _clean_spaces(title)
    s = re.sub(r"(?:\s*#[\w\u0400-\u04FF]+)+\s*$", "", s).strip()
    if not s:
        s = _clean_spaces(fallback)
    if len(s) <= max_chars:
        return s
    cut = s[: max_chars - 1].rstrip(" ,;:|-")
    return f"{cut}…"


def hashtags_from_text(text: str) -> list[str]:
    return _dedupe_keep_order(re.findall(r"#[\w\u0400-\u04FF]+", text or ""))


def strip_hashtags_from_description(text: str) -> str:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if re.fullmatch(r"(#[\w\u0400-\u04FF]+\s*){1,12}", stripped):
            continue
        kept.append(stripped)
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept).strip()


def normalize_hashtags(
    hashtags: list[str] | str | None,
    *,
    fallback_pool: list[str],
    min_count: int = 3,
    max_count: int = 5,
) -> list[str]:
    items: list[str]
    if isinstance(hashtags, str):
        items = re.findall(r"#[\w\u0400-\u04FF]+", hashtags)
    elif isinstance(hashtags, list):
        items = [str(x).strip() for x in hashtags]
    else:
        items = []
    cleaned = []
    for item in items:
        s = str(item or "").strip()
        if not s:
            continue
        if not s.startswith("#"):
            s = f"#{s.lstrip('#')}"
        cleaned.append(s)
    out = _dedupe_keep_order(cleaned)
    for tag in fallback_pool:
        if len(out) >= min_count:
            break
        norm = tag if tag.startswith("#") else f"#{tag}"
        if norm.lower() not in {x.lower() for x in out}:
            out.append(norm)
    return out[:max_count]


def normalize_tags(
    tags: list[str] | str | None,
    *,
    fallback_pool: list[str],
    min_count: int = 8,
    max_count: int = 12,
) -> list[str]:
    if isinstance(tags, str):
        raw = re.split(r"[,;\n]+", tags)
    elif isinstance(tags, list):
        raw = [str(x) for x in tags]
    else:
        raw = []
    cleaned: list[str] = []
    for item in raw:
        s = str(item or "").strip().lstrip("#")
        s = re.sub(r"\s+", " ", s)
        if not s:
            continue
        cleaned.append(s[:60])
    out = _dedupe_keep_order(cleaned)
    existing = {x.lower() for x in out}
    for item in fallback_pool:
        if len(out) >= min_count:
            break
        s = str(item or "").strip().lstrip("#")
        if not s or s.lower() in existing:
            continue
        existing.add(s.lower())
        out.append(s[:60])
    return out[:max_count]


def build_description(
    body: str,
    *,
    hashtags: list[str],
    fallback_body: str,
    min_chars: int = 140,
    max_chars: int = 420,
) -> str:
    text = strip_hashtags_from_description(body)
    if len(text) < min_chars:
        text = (text + "\n\n" + fallback_body).strip() if text else fallback_body.strip()
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip(" ,;:-")
        if "\n" in text:
            text = text.rsplit("\n", 1)[0].rstrip() or text
        text = f"{text}…"
    hash_line = " ".join(hashtags).strip()
    return f"{text}\n\n{hash_line}".strip() if hash_line else text


def finalize_metadata(
    *,
    title: str,
    description: str,
    tags: list[str] | str | None,
    hashtags: list[str] | str | None,
    fallback_title: str,
    fallback_description: str,
    fallback_tags: list[str],
    fallback_hashtags: list[str],
    first_comment: str | None = None,
    title_max_chars: int = 58,
    min_description_chars: int = 140,
    max_description_chars: int = 420,
    min_tags: int = 8,
    max_tags: int = 12,
    min_hashtags: int = 3,
    max_hashtags: int = 5,
) -> dict[str, Any]:
    clean_hashtags = normalize_hashtags(
        hashtags,
        fallback_pool=fallback_hashtags,
        min_count=min_hashtags,
        max_count=max_hashtags,
    )
    clean_title = normalize_title(title, fallback=fallback_title, max_chars=title_max_chars)
    clean_tags = normalize_tags(
        tags,
        fallback_pool=fallback_tags,
        min_count=min_tags,
        max_count=max_tags,
    )
    clean_desc = build_description(
        description,
        hashtags=clean_hashtags,
        fallback_body=fallback_description,
        min_chars=min_description_chars,
        max_chars=max_description_chars,
    )
    return {
        "title": clean_title,
        "description": clean_desc,
        "tags": clean_tags,
        "hashtags": clean_hashtags,
        "first_comment": (first_comment or "").strip(),
    }
