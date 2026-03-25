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
    # Remove markdown fences
    for pattern in (r"```(?:json)?\s*(.*?)\s*```",):
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            break

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")

    depth = 0
    in_string = False
    escape = False
    quote = None

    for i, c in enumerate(raw[start:], start=start):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if not in_string:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]
            elif c in ('"', "'"):
                in_string = True
                quote = c
        elif c == quote:
            in_string = False

    raise ValueError("Unbalanced braces in JSON")


def parse_json_safe(text: str) -> dict:
    """Parse JSON, using only the first complete object. Avoids 'Extra data' error."""
    extracted = extract_first_json(text)
    return json.loads(extracted)
