"""
Extract first complete JSON object from LLM response.
Handles "Extra data" error when model returns JSON + trailing text.
"""

from __future__ import annotations

import json
import re


def extract_first_json(text: str) -> str:
    """
    Extract the first complete JSON object from text.
    Handles markdown code blocks and trailing content after closing brace.
    """
    raw = text.strip()
    # Открытый ```json без закрывающих ``` (частый случай при обрезке по max_tokens)
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        if first_nl != -1:
            raw = raw[first_nl + 1 :].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[0].strip()
    # Закрытый fence целиком
    for pattern in (r"```(?:json)?\s*(.*?)\s*```",):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            break

    decoder = json.JSONDecoder()
    saw_json_start = False

    for start, char in enumerate(raw):
        if char not in "{[":
            continue

        saw_json_start = True
        try:
            _, end = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        return raw[start : start + end]

    if saw_json_start:
        raise ValueError("Unbalanced braces in JSON")
    raise ValueError("No JSON object found in response")


def parse_json_safe(text: str) -> dict:
    """Parse JSON, using only the first complete object. Avoids 'Extra data' error."""
    extracted = extract_first_json(text)
    return json.loads(extracted)
