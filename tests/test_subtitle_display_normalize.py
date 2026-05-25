"""Subtitle display normalization (curly quotes, tofu placeholders)."""

from agents.video_editor.subtitles import normalize_subtitle_display_text


def test_curly_quotes_become_ascii():
    raw = "saying, \u201cWhere is He who has been born King of the Jews?\u201d"
    out = normalize_subtitle_display_text(raw)
    assert "\u201c" not in out
    assert '"Where is He' in out


def test_strips_orphan_leading_comma():
    out = normalize_subtitle_display_text(',"Now after Jesus was born')
    assert out.startswith('"Now')


def test_drops_replacement_and_placeholder_glyphs():
    out = normalize_subtitle_display_text("hello \ufffd \u25a1 world")
    assert out == "hello world"
