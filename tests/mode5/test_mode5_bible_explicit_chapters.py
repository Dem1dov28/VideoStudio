from modes.mode5.bible_chapters import (
    apply_bible_chapter_labels,
    build_bible_slices_from_explicit_chapters,
)
from modes.mode5.pipeline import _mode5_chapter_overlay_label


def test_bible_chapters_payload_from_script_splits_on_chapter_heading():
    from modes.mode5.bible_chapters import bible_chapters_payload_from_script

    text = (
        "Chapter 1. In the beginning God created the heaven and the earth. "
        "And the earth was without form, and void."
        " "
        "Chapter 2. Thus the heavens and the earth were finished, and all the host of them."
    )
    rows = bible_chapters_payload_from_script(text)
    assert len(rows) >= 2
    assert rows[0]["overlay_label"]
    assert "beginning" in rows[0]["text"].lower()
    assert "finished" in rows[-1]["text"].lower()

    slices = build_bible_slices_from_explicit_chapters(
        [
            {"overlay_label": "Genesis 1", "text": "In the beginning God created the heaven and the earth."},
            {"overlay_label": "Genesis 2", "text": "Thus the heavens and the earth were finished."},
        ]
    )
    assert len(slices) == 2
    assert slices[0].label == "Genesis 1"
    assert slices[1].label == "Genesis 2"


def test_explicit_overlay_label_is_used_on_video():
    plan = {
        "sub_mode": "bible",
        "bible_locked_labels": True,
        "chunks": [
            {
                "index": 0,
                "chapter_title": "My Custom Title",
                "segments": [{"s": 0, "text": "Some narration text."}],
            }
        ],
    }
    apply_bible_chapter_labels(plan)
    seg = plan["chunks"][0]["segments"][0]
    assert seg["chapter_label"] == "My Custom Title"
    assert _mode5_chapter_overlay_label(plan["chunks"][0], plan, seg=seg) == "My Custom Title"
