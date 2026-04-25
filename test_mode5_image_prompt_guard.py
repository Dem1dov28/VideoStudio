from modes.mode5.pipeline import _mode5_locked_style, _mode5_visual_policy, _sanitize_mode5_image_prompt


def test_mode5_prompt_guard_removes_collage_and_book_trope():
    raw = (
        "Scene prompt: make a collage grid of 9 photos with an open book on table in center. "
        "Art direction: cinematic."
    )
    out = _sanitize_mode5_image_prompt(raw)
    low = out.lower()
    assert "hard override for mode5" in low
    assert "collage grid" not in low
    assert "open book" not in low
    assert "book on table" not in low


def test_mode5_prompt_guard_is_always_appended_even_when_not_flagged():
    raw = "Single traveler walking near the river at dusk, cinematic atmosphere."
    out = _sanitize_mode5_image_prompt(raw)
    low = out.lower()
    assert "hard override for mode5" in low
    assert "no text/ui/logos/watermarks in frame" in low
    assert "single traveler walking near the river" in low


def test_mode5_style_lock_keeps_original_style_suffix():
    plan = {"style_suffix": "soft painterly realism"}
    first = _mode5_locked_style(plan)
    assert first == "soft painterly realism"
    assert plan["style_lock"] == "soft painterly realism"

    plan["style_suffix"] = "different style drift"
    locked = _mode5_locked_style(plan)
    assert locked == "soft painterly realism"
    assert plan["style_suffix"] == "soft painterly realism"


def test_mode5_visual_policy_covers_manual_and_bible_submodes():
    assert _mode5_visual_policy("manual") == "mode5"
    assert _mode5_visual_policy("bible") == "mode5"
