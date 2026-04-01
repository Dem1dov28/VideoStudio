"""Diagnostic live script: dump Video-tab buttons related to keyframes."""
import asyncio
import sys

sys.path.insert(0, r"d:\work\VideoStudio")

from agents.content_generator.fastgen_scraper import FastGenScraper


async def main():
    scraper = FastGenScraper()
    await scraper.start()
    try:
        await scraper._authenticate()
        await scraper._activate_video_tab()
        await scraper._select_video_settings()
        await asyncio.sleep(1.5)
        page = scraper._page
        assert page is not None

        strict_sel = "button.flex-1.rounded-md.px-3.py-1\\.5.text-xs.font-medium.transition-colors[data-state]"
        strict_count = await page.locator(strict_sel).count()
        print(f"[DUMP] strict segmented count: {strict_count}")

        buttons = page.locator("button")
        total = await buttons.count()
        print(f"[DUMP] total buttons: {total}")
        for i in range(min(total, 120)):
            btn = buttons.nth(i)
            try:
                if not await btn.is_visible():
                    continue
                txt = ((await btn.inner_text()) or "").strip()
                if not txt:
                    continue
                low = txt.lower()
                if any(k in low for k in ["кадр", "key", "frame", "video", "видео"]):
                    ds = await btn.get_attribute("data-state")
                    cls = await btn.get_attribute("class")
                    role = await btn.get_attribute("role")
                    print(f"[{i}] text='{txt}' role={role} data-state={ds} class={cls}")
            except Exception:
                continue
    finally:
        await scraper.stop()


if __name__ == "__main__":
    asyncio.run(main())
