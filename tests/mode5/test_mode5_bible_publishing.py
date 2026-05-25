"""Bible mode publishing metadata must not read as sleep-video copy."""

from __future__ import annotations

from modes.mode5.publishing_metadata import (
    _BIBLE_SLEEP_TOKEN,
    _fallback_publish_bible,
    _sanitize_bible_publishing_metadata,
)


def _assert_no_sleep_tokens(meta: dict) -> None:
    for key in ("title", "description", "first_comment"):
        val = str(meta.get(key) or "")
        assert not _BIBLE_SLEEP_TOKEN.search(val), f"{key} contains sleep token: {val!r}"
    for key in ("tags", "hashtags"):
        for item in meta.get(key) or []:
            assert not _BIBLE_SLEEP_TOKEN.search(str(item)), f"{key} item {item!r}"


def test_bible_fallback_en_has_no_sleep_tokens():
    fb = _fallback_publish_bible("Matthew 1 — Nativity", "en")
    _assert_no_sleep_tokens(fb)
    assert "scripture" in fb["description"].lower() or "bible" in fb["description"].lower()


def test_bible_fallback_ru_has_no_sleep_tokens():
    fb = _fallback_publish_bible("Матфея 1 — Рождество", "ru")
    _assert_no_sleep_tokens(fb)


def test_sanitize_strips_sleep_llm_output():
    fb = _fallback_publish_bible("Luke 2", "en")
    dirty = {
        "title": "A Soothing Journey Through the Nativity Story for Peaceful Sleep",
        "description": "Designed to ease your mind and prepare for restful sleep.\n\n#sleep #relaxation",
        "hashtags": ["#sleep", "#biblestory", "#nativity", "#relaxation", "#peaceful"],
        "tags": ["calm sleep", "sleep aid", "bible narration", "relaxing narration"],
        "first_comment": "What part resonates as you prepare for sleep?",
    }
    clean = _sanitize_bible_publishing_metadata(dirty, fallback=fb)
    _assert_no_sleep_tokens(clean)
    assert clean["title"] == fb["title"]
    assert "bible narration" in clean["tags"]
