from utils.json_parse import extract_first_json, parse_json_safe


def test_extract_first_json_skips_malformed_preamble():
    text = (
        'Sure, here is the structure: {"video_prompt": "draft"\n'
        'Actual payload follows:\n'
        '{"video_prompt": "final", "script_ru": "quote"}'
    )

    extracted = extract_first_json(text)

    assert extracted == '{"video_prompt": "final", "script_ru": "quote"}'


def test_parse_json_safe_unclosed_markdown_fence():
    """Модель иногда обрывает ответ до закрывающих ``` — JSON всё же может быть полным."""
    text = '```json\n{"video_prompt": "short", "script_ru": "цитата"}'

    data = parse_json_safe(text)

    assert data["video_prompt"] == "short"
    assert data["script_ru"] == "цитата"


def test_parse_json_safe_reads_json_inside_fence_with_trailing_text():
    text = """```json
{"video_prompt": "final", "script_ru": "quote"}
```
Notes after JSON.
"""

    data = parse_json_safe(text)

    assert data["video_prompt"] == "final"
    assert data["script_ru"] == "quote"
