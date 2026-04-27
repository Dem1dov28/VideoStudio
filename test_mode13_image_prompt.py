"""Регрессии: единый блок hard rules, эпоха flex, FastGen без ложного historical lock."""

from agents.content_generator.fastgen_scraper import prepare_fastgen_prompt_for_ui
from modes.mode13.pipeline import (
    _compose_image_prompt,
    _mode13_hard_rules_suffix,
)


def test_mode13_hard_rules_suffix_horizontal():
    s = _mode13_hard_rules_suffix(output_format="horizontal")
    assert "Hard rules (every frame)" in s
    assert "Horizontal widescreen" in s
    assert "All-ages only" in s
    assert s.count("All-ages only") == 1
    assert "single uninterrupted frame" in s.lower()
    assert "table-with-book" in s.lower()
    assert "16:9" not in s
    assert "9:16" not in s


def test_compose_image_prompt_includes_hard_rules_once():
    out = _compose_image_prompt(
        "Anonymous figures on a city riverbank at blue hour.",
        "Cool desaturated palette, soft volumetric light.",
        output_format="horizontal",
        visual_policy="default",
        visual_bible=None,
    )
    assert out.count("All-ages only") == 1
    rules = _mode13_hard_rules_suffix(output_format="horizontal")
    assert rules in out
    assert out.rsplit("\n\n", 1)[-1] == rules
    assert "Infer the IMPLIED ERA" in out
    assert "16:9" not in out
    assert "9:16" not in out


def test_compose_ignores_visual_bible_custom_rules():
    out = _compose_image_prompt(
        "Team huddle before a whiteboard with no legible markings.",
        "Clean editorial illustration, muted corporate palette.",
        output_format="horizontal",
        visual_policy="default",
        visual_bible={"frame_rules": "Custom rule that should not leak"},
    )
    assert "Custom rule that should not leak" not in out
    assert out.count("All-ages only") == 1


def test_compose_longform_flex_uses_same_base_template():
    out = _compose_image_prompt(
        "A quiet home desk with a plant and mug.",
        "Cozy golden-hour domestic palette.",
        output_format="horizontal",
        visual_policy="longform_flex",
        visual_bible=None,
    )
    assert "Show one concrete scene from the spoken episode." in out
    assert out.count("All-ages only") == 1
    assert "For this long-form mode5 sequence" not in out


def test_compose_prompt_has_no_legacy_mode5_phrases_for_any_policy():
    legacy_markers = (
        "Hard override for mode5",
        "archival investigation narration",
        "Prioritize Biblical context for visual prompts",
        "book-summary narration",
        "No book-on-table hero shot",
    )
    for policy in ("default", "facts50", "book_night", "unwritten_chapter", "mode5", "longform_flex"):
        out = _compose_image_prompt(
            "A calm evening street with two pedestrians crossing near a tram stop.",
            "Muted cinematic palette, soft shadows.",
            output_format="horizontal",
            visual_policy=policy,
            visual_bible={"frame_rules": "legacy injected rule"},
        )
        for marker in legacy_markers:
            assert marker not in out


def test_fastgen_no_false_historical_lock_on_modern_self_help_copy():
    p = (
        "Every still must reflect contemporary life, emphasizing modern environments. "
        "Avoid anachronisms, such as outdated technology or historical settings that do not align "
        "with the modern self-help theme. Scene: serene park at golden hour."
    )
    full = prepare_fastgen_prompt_for_ui(p)
    assert "AUTHENTIC HISTORICAL WORLD" not in full


def test_fastgen_still_adds_historical_lock_for_medieval_topic():
    p = "16:9 illustration of a medieval castle at dawn, stone walls, torches, no text."
    full = prepare_fastgen_prompt_for_ui(p)
    assert "AUTHENTIC HISTORICAL WORLD" in full


def test_fastgen_enforces_single_full_frame_scene_for_all_modes():
    p = "Stylized editorial portrait, dramatic light, no text."
    full = prepare_fastgen_prompt_for_ui(p)
    low = full.lower()
    assert "final image requirement" in low
    assert "one dominant full-frame image only" in low
    assert "single uninterrupted scene in one frame" in low
    assert "final text restriction" in low
    assert "absolutely no visible text anywhere in the image" in low


def test_fastgen_strips_explicit_collage_gallery_terms_from_user_prompt():
    p = "Create a collage grid of 9 photos like a gallery carousel, cinematic."
    full = prepare_fastgen_prompt_for_ui(p)
    first_block = full.split("\n\n", 1)[0].lower()
    assert "collage" not in first_block
    assert "gallery" not in first_block
    assert "carousel" not in first_block
