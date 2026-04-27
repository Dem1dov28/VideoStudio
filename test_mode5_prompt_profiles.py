from modes.mode5.prompt_builder import (
    build_mode5_image_prompt,
    build_mode5_image_prompt_debug,
    mode5_style_id_for_sub_mode,
    mode5_style_lock_for_sub_mode,
    normalize_mode5_sub_mode,
)


def test_mode5_submode_profile_mapping_defaults():
    assert normalize_mode5_sub_mode("manual") == "manual"
    assert normalize_mode5_sub_mode("bible") == "bible"
    assert normalize_mode5_sub_mode("facts50") == "facts50"
    assert normalize_mode5_sub_mode("outline") == "outline"
    assert normalize_mode5_sub_mode("book_night") == "book_night"
    assert normalize_mode5_sub_mode("unwritten_chapter") == "unwritten_chapter"
    assert normalize_mode5_sub_mode("unknown_mode") == "manual"


def test_mode5_style_lock_is_deterministic_per_mode():
    s1 = mode5_style_lock_for_sub_mode("book_night")
    s2 = mode5_style_lock_for_sub_mode("book_night")
    assert s1 == s2
    assert mode5_style_id_for_sub_mode("book_night") == "soft_cinematic_realistic"


def test_mode5_prompt_uses_current_segment_and_chunk_context():
    out = build_mode5_image_prompt(
        sub_mode="outline",
        segment_text="Narrator describes a factory worker inspecting a broken turbine.",
        chunk_context="Previous segment: power outage in the district.",
        style_lock=mode5_style_lock_for_sub_mode("outline"),
        output_format="horizontal",
    )
    low = out.lower()
    assert "base the image on this narration moment" in low
    assert "factory worker inspecting a broken turbine" in low
    assert "for continuity of place, era, people, or mood" in low
    assert "power outage in the district" in low
    assert "horizontal landscape composition (16:9)." in low
    assert "the narration moment is authoritative" in low
    assert "build the scene around" in low
    assert "use even lighting" in low
    assert "generate exactly one photo with exactly one scene only" in low
    assert "exactly one photo with exactly one scene only" in low


def test_mode5_prompt_contains_mode_specific_constraints():
    out = build_mode5_image_prompt(
        sub_mode="book_night",
        segment_text="A woman reflects on her daily routine in a quiet kitchen.",
        chunk_context="Neighbor context",
        style_lock=mode5_style_lock_for_sub_mode("book_night"),
        output_format="horizontal",
    )
    assert "Soft cinematic realism" in out
    low = out.lower()
    assert "no book spread" in low
    assert "library shelf as the dominant subject" in low


def test_each_mode5_submode_has_distinct_operational_slots():
    """Every sub_mode gets its own Scene slots / extra rules (not generic one-size)."""
    checks = {
        "manual": ("realistic documentary", "sober documentary, grounded"),
        "bible": ("classical painterly", "ancient near east plausible"),
        "facts50": ("clean editorial realism", "current fact line"),
        "outline": ("neutral documentary", "recurring motifs consistent"),
        "book_night": ("soft cinematic realism", "sleep-friendly"),
        "unwritten_chapter": ("archival documentary realism", "investigation props"),
    }
    for sm, (style_marker, slot_marker) in checks.items():
        out = build_mode5_image_prompt(
            sub_mode=sm,
            segment_text="Example narration line for testing.",
            chunk_context="Earlier chunk line for continuity.",
            style_lock=mode5_style_lock_for_sub_mode(sm),
            output_format="horizontal",
        )
        low = out.lower()
        assert style_marker in low, sm
        assert slot_marker in low, sm
        assert "build the scene around" in low
        assert "generate exactly one photo with exactly one scene only" in low


def test_unwritten_chapter_prompt_has_archival_profile_and_segment_priority():
    style_lock = mode5_style_lock_for_sub_mode("unwritten_chapter")
    out = build_mode5_image_prompt(
        sub_mode="unwritten_chapter",
        segment_text="Investigators compare declassified folders under a desk lamp in a dim archive room.",
        chunk_context="Previous segment: witness testimony about missing pages.",
        style_lock=style_lock,
        output_format="horizontal",
    )
    low = out.lower()
    debug = build_mode5_image_prompt_debug(
        sub_mode="unwritten_chapter",
        segment_text="Investigators compare declassified folders under a desk lamp in a dim archive room.",
        chunk_context="Previous segment: witness testimony about missing pages.",
        style_lock=style_lock,
        output_format="horizontal",
    ).lower()
    assert "mode profile: unwritten_chapter." in debug
    assert "locked style id: archival_documentary_muted." in debug
    assert "scene selection rule: derive subject/action/environment from current_segment first." in debug
    assert "investigators compare declassified folders under a desk lamp" in low
    assert "previous segment: witness testimony about missing pages." in low
    assert "absolutely no visible text anywhere in the image" in low
    assert "investigation props" in low
    assert "do not create symbolic, metaphorical, or conceptual substitutions" in low


def test_final_prompt_does_not_expose_prompt_metadata_labels_to_image_model():
    out = build_mode5_image_prompt(
        sub_mode="unwritten_chapter",
        segment_text="Investigators compare folders in an archive room.",
        chunk_context="Earlier context about missing pages.",
        style_lock=mode5_style_lock_for_sub_mode("unwritten_chapter"),
        output_format="horizontal",
    )
    forbidden = (
        "Mode profile",
        "Locked style id",
        "CURRENT_SEGMENT",
        "CHUNK_CONTEXT",
        "Scene slots",
        "Technical rules",
        "Scene source:",
        "Continuity context:",
        "Mode-specific direction:",
        "Priority rule:",
        "Anti-abstract rule:",
        "Critical single-scene rule:",
        "Scene construction:",
        "Quality constraints:",
        "Frame format:",
        "Visual style:",
        "Follow this visual direction:",
        "Absolutely no visible text anywhere in the image:",
        "Fact-first rule:",
        "Era rule:",
        "Outline coherence:",
        "Evidence visibility rule:",
    )
    for marker in forbidden:
        assert marker not in out
    low = out.lower()
    assert "absolutely no visible text anywhere in the image" in low
    assert "no tiled layout, no side-by-side layout, no segmented layout, no panel layout, no small inset pictures" in low
