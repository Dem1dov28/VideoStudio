"""Регрессии: единый блок hard rules, эпоха flex, FastGen без ложного historical lock."""

from agents.content_generator.fastgen_scraper import prepare_fastgen_prompt_for_ui
from modes.mode13.pipeline import (
    VISUAL_POLICY_LONGFORM_FLEX,
    _compose_image_prompt,
    _mode13_hard_rules_suffix,
)


def test_mode13_hard_rules_suffix_horizontal():
    s = _mode13_hard_rules_suffix(output_format="horizontal")
    assert "Hard rules (every frame)" in s
    assert "Horizontal 16:9" in s
    assert "All-ages only" in s
    assert s.count("All-ages only") == 1
    assert "no collage" in s.lower()
    assert "table-with-book" in s.lower()


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


def test_compose_with_visual_bible_custom_rules():
    bible = {
        "frame_rules": "Contemporary office: laptops closed or angled away; warm daylight; no readable screens.",
        "scene_cue": "Pick one beat from the narration.",
        "series_style": "",
    }
    out = _compose_image_prompt(
        "Team huddle before a whiteboard with no legible markings.",
        "Clean editorial illustration, muted corporate palette.",
        output_format="horizontal",
        visual_policy="default",
        visual_bible=bible,
    )
    assert "Contemporary office" in out
    assert out.count("All-ages only") == 1


def test_compose_longform_flex_skips_extra_scene_rules_block():
    out = _compose_image_prompt(
        "A quiet home desk with a plant and mug.",
        "Cozy golden-hour domestic palette.",
        output_format="horizontal",
        visual_policy=VISUAL_POLICY_LONGFORM_FLEX,
        visual_bible=None,
    )
    assert "Show one concrete scene from the spoken episode, not a symbolic collage" not in out
    assert out.count("All-ages only") == 1
    assert "exactly one dominant full-frame scene" in out
    assert "Never center the composition on a book-on-table trope" in out


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
