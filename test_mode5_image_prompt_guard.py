from modes.mode5.pipeline import _mode5_locked_style, _sanitize_mode5_image_prompt


def test_mode5_prompt_sanitize_collapses_whitespace_only():
    raw = "  Scene prompt   with   extra   spaces.  "
    out = _sanitize_mode5_image_prompt(raw)
    assert out.startswith("Scene prompt with extra spaces.")
    assert "Final hard requirement for this Mode5 image" in out


def test_mode5_prompt_sanitize_does_not_append_legacy_guard():
    raw = "Single traveler walking near the river at dusk, cinematic atmosphere."
    out = _sanitize_mode5_image_prompt(raw)
    low = out.lower()
    assert "single traveler walking near the river" in low
    assert "hard override for mode5" not in low
    assert "absolutely no visible text anywhere" in low


def test_mode5_style_lock_keeps_original_style_suffix():
    plan = {"style_suffix": "soft painterly realism"}
    first = _mode5_locked_style(plan)
    assert first == "soft painterly realism"
    assert plan["style_lock"] == "soft painterly realism"

    plan["style_suffix"] = "different style drift"
    locked = _mode5_locked_style(plan)
    assert locked == "soft painterly realism"
    assert plan["style_suffix"] == "soft painterly realism"


def test_mode5_prompt_sanitize_keeps_content_verbatim():
    raw = "No collage and no open book references should be auto-removed now."
    out = _sanitize_mode5_image_prompt(raw)
    assert out.startswith(raw)


def test_mode5_prompt_sanitize_removes_metadata_labels_and_enforces_single_image():
    raw = (
        "Mode profile: unwritten_chapter. Locked style id: archival_documentary_muted. "
        "CURRENT_SEGMENT: investigators compare folders. CHUNK_CONTEXT: previous witness. "
        "Technical rules: no readable text."
    )
    out = _sanitize_mode5_image_prompt(raw)
    for marker in ("Mode profile", "Locked style id", "CURRENT_SEGMENT", "CHUNK_CONTEXT", "Technical rules"):
        assert marker not in out
    low = out.lower()
    assert "investigators compare folders" in low
    assert "previous witness" in low
    assert "exactly one full-frame image" in low
    assert "no tiled layout, no side-by-side layout, no segmented layout, no panel layout, no small inset pictures" in low
    assert "absolutely no visible text anywhere" in low
