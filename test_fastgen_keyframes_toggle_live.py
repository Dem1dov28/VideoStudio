"""Live Playwright test: opens fast-gen and clicks keyframes segmented buttons."""
import asyncio
import sys

sys.path.insert(0, r"d:\work\VideoStudio")

from agents.content_generator.fastgen_scraper import FastGenScraper


async def _find_segmented_buttons(page):
    selectors = [
        "div.flex.rounded-lg.bg-secondary\\/50.p-0\\.5 button",
        "div[class*='rounded-lg'][class*='bg-secondary'] button",
    ]
    for sel in selectors:
        loc = page.locator(sel)
        count = await loc.count()
        if count > 0:
            return loc, count
    return None, 0


async def _find_keyframes_button(buttons, count):
    for i in range(count):
        btn = buttons.nth(i)
        if not await btn.is_visible():
            continue
        txt = ((await btn.inner_text()) or "").strip().lower()
        if "ключ" in txt or "keyframe" in txt or ("key" in txt and "frame" in txt):
            return btn, txt
    return None, ""


async def main():
    scraper = FastGenScraper()
    await scraper.start()
    try:
        await scraper._authenticate()
        await scraper._activate_video_tab()
        await asyncio.sleep(1.2)

        page = scraper._page
        assert page is not None

        buttons, count = await _find_segmented_buttons(page)
        if not buttons or count == 0:
            raise RuntimeError("Не нашел segmented-контейнер с кнопками в Video tab.")

        key_btn, key_txt = await _find_keyframes_button(buttons, count)
        if key_btn is None:
            raise RuntimeError("Не нашел кнопку 'Ключ. кадры'/'Keyframes'.")

        # 1) Click keyframes button (or verify already active)
        state_before = await key_btn.get_attribute("data-state")
        print(f"[LIVE] Keyframes button text='{key_txt}', state before={state_before}")
        if state_before in ("open", "active", "checked"):
            print("[LIVE] Keyframes already active.")
        else:
            await key_btn.click()
            await asyncio.sleep(0.5)
            print(f"[LIVE] Clicked keyframes, state after={await key_btn.get_attribute('data-state')}")

        # 2) Click another button in same segmented control (if exists), then back to keyframes
        other_btn = None
        for i in range(count):
            btn = buttons.nth(i)
            if btn == key_btn:
                continue
            if await btn.is_visible():
                other_btn = btn
                break

        if other_btn is not None:
            other_txt = ((await other_btn.inner_text()) or "").strip()
            await other_btn.click()
            await asyncio.sleep(0.4)
            print(f"[LIVE] Clicked sibling button: '{other_txt}'")

            await key_btn.click()
            await asyncio.sleep(0.5)
            print(f"[LIVE] Returned to keyframes, state now={await key_btn.get_attribute('data-state')}")
        else:
            print("[LIVE] Sibling button not found, skipped second click sequence.")

        print("test_fastgen_keyframes_toggle_live.py: PASS")
        await asyncio.sleep(2.0)
    finally:
        await scraper.stop()


if __name__ == "__main__":
    asyncio.run(main())
