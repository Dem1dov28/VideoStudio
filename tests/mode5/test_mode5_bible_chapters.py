"""Bible chapter overlay labels for Mode5."""

from modes.mode5.bible_chapters import (
    apply_bible_chapter_labels,
    infer_bible_book_from_plan,
    update_bible_chapter_state,
)


def test_infer_matthew_from_genealogy_opening():
    plan = {
        "source_input_text": (
            "The book of the genealogy of Jesus Christ, the Son of David, Abraham begot Isaac."
        ),
        "chunks": [],
    }
    assert infer_bible_book_from_plan(plan) == "Matthew"


def test_matthew_ch2_without_chapter_heading():
    book, chapter, label = update_bible_chapter_state(
        "Now after Jesus was born in Bethlehem of Judea in the days of Herod the king, "
        "behold, wise men from the East came to Jerusalem.",
        book="Matthew",
        chapter=1,
    )
    assert chapter == 2
    assert label == "Matthew 2"


def test_apply_labels_advances_on_bethlehem_segment():
    plan = {
        "sub_mode": "bible",
        "source_input_text": "The book of the genealogy of Jesus Christ",
        "chunks": [
            {
                "index": 0,
                "segments": [
                    {"s": 0, "text": "Abraham begot Isaac, and Isaac begot Jacob."},
                    {
                        "s": 1,
                        "text": (
                            "Now after Jesus was born in Bethlehem of Judea in the days of Herod the king, "
                            "wise men from the East came to Jerusalem."
                        ),
                    },
                ],
            },
        ],
    }
    apply_bible_chapter_labels(plan)
    segs = plan["chunks"][0]["segments"]
    assert segs[0]["chapter_label"] == "Matthew 1"
    assert segs[1]["chapter_label"] == "Matthew 2"
