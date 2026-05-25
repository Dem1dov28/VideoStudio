from modes.mode5.bible_chapters import (
    apply_bible_chapter_labels,
    infer_bible_book_from_plan,
    update_bible_chapter_state,
)
from modes.mode5.pipeline import (
    _mode5_chapter_overlay_label,
    _mode5_default_show_subtitles,
)


def test_bible_enables_subtitles():
    assert _mode5_default_show_subtitles("bible") is True
    assert _mode5_default_show_subtitles("manual") is False


def test_matthew_genealogy_opening():
    plan = {
        "sub_mode": "bible",
        "header_title": "The book of the genealogy of Jesus Christ",
        "chunks": [
            {
                "index": 0,
                "segments": [
                    {
                        "s": 0,
                        "text": (
                            "The book of the genealogy of Jesus Christ, the son of David, "
                            "the son of Abraham."
                        ),
                    }
                ],
            }
        ],
    }
    apply_bible_chapter_labels(plan)
    assert plan["chunks"][0]["segments"][0]["chapter_label"] == "Matthew 1"
    assert infer_bible_book_from_plan(plan) == "Matthew"


def test_chapter_advances_on_chapter_two_marker():
    book, ch, label = update_bible_chapter_state(
        "Chapter 2. John the Baptist prepares the way.",
        book="Matthew",
        chapter=1,
    )
    assert book == "Matthew"
    assert ch == 2
    assert label == "Matthew 2"


def test_chapter_advances_on_verse_reference():
    book, ch, label = update_bible_chapter_state(
        "Now when Jesus was born in Bethlehem of Judea in the days of Herod the king, behold, wise men from the east came to Jerusalem.",
        book="Matthew",
        chapter=1,
    )
    assert label == "Matthew 1"
    book, ch, label = update_bible_chapter_state(
        "After Jesus was born in Bethlehem of Judea, 2:1 during the time of King Herod, Magi came.",
        book=book,
        chapter=ch,
    )
    assert ch == 2
    assert label == "Matthew 2"


def test_chapter_overlay_uses_outline_fields():
    ch = {"chapter_title": "Genesis", "subchapter_title": "Day One"}
    plan = {"sub_mode": "outline"}
    assert _mode5_chapter_overlay_label(ch, plan) == "Genesis — Day One"


def test_per_segment_overlay_label():
    plan = {"sub_mode": "bible", "header_title": "Matthew"}
    ch = {"index": 0, "text": "..."}
    seg = {"chapter_label": "Matthew 3"}
    assert _mode5_chapter_overlay_label(ch, plan, seg=seg) == "Matthew 3"
