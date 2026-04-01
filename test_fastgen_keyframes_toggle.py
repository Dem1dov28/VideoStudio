"""Smoke tests for FastGen keyframes toggle (new segmented UI)."""
import asyncio
import sys

sys.path.insert(0, r"d:\work\VideoStudio")

from agents.content_generator.fastgen_scraper import _toggle_keyframes_mode


class _MockButton:
    def __init__(self, text: str, data_state: str = "closed", visible: bool = True):
        self.text = text
        self.data_state = data_state
        self.visible = visible
        self.click_count = 0

    async def is_visible(self, timeout=None):  # noqa: ARG002
        return self.visible

    async def inner_text(self):
        return self.text

    async def get_attribute(self, name: str):
        if name == "data-state":
            return self.data_state
        return None

    async def click(self):
        self.click_count += 1
        self.data_state = "open"


class _MockCollection:
    def __init__(self, items):
        self.items = items

    @property
    def first(self):
        if self.items:
            return self.items[0]
        return _MockButton("", visible=False)

    async def count(self):
        return len(self.items)

    def nth(self, idx: int):
        return self.items[idx]


class _MockPage:
    def __init__(self, segmented_buttons):
        self.segmented_buttons = segmented_buttons

    def locator(self, selector: str):
        # Old switch selectors -> not found/hidden
        if "role=\"switch\"" in selector or "id*=\"keyframe\"" in selector or "checkbox" in selector:
            return _MockCollection([])

        # New segmented UI selector used in implementation
        if selector in (
            "div.flex.rounded-lg.bg-secondary\\/50.p-0\\.5 button",
            "div[class*=\"rounded-lg\"][class*=\"bg-secondary\"] button",
        ):
            return _MockCollection(self.segmented_buttons)

        # Fallback text locator should be invisible in this test
        if "text=/keyframe|key.*frame|кадр/i" in selector:
            return _MockCollection([])

        return _MockCollection([])


async def _test_closed_to_open():
    btn = _MockButton("Ключ. кадры", data_state="closed", visible=True)
    page = _MockPage([btn])
    ok = await _toggle_keyframes_mode(page)
    assert ok is True, "Expected keyframes mode to be enabled"
    assert btn.click_count == 1, "Expected one click on segmented keyframes button"
    assert btn.data_state == "open", "Expected button to become open"


async def _test_already_open():
    btn = _MockButton("Keyframes", data_state="open", visible=True)
    page = _MockPage([btn])
    ok = await _toggle_keyframes_mode(page)
    assert ok is True, "Expected keyframes mode already enabled"
    assert btn.click_count == 0, "Expected no click when already open"


if __name__ == "__main__":
    asyncio.run(_test_closed_to_open())
    asyncio.run(_test_already_open())
    print("test_fastgen_keyframes_toggle.py: PASS")
