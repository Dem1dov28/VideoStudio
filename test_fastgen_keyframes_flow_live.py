"""Live smoke test for keyframes flow: upload images, fill prompt, click Generate."""
import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, r"d:\work\VideoStudio")

from agents.content_generator.fastgen_scraper import (
    FastGenScraper,
    _toggle_keyframes_mode,
    _upload_keyframe_start,
    _upload_keyframe_end,
    _find_first,
    _react_fill,
    _PROMPT_SELECTORS,
    _GENERATE_SELECTORS,
)


_PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO6pN5kAAAAASUVORK5CYII="
)


def _make_test_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(_PNG_1X1_BASE64))


async def main() -> None:
    temp_dir = Path(r"d:\work\VideoStudio\output\debug_screenshots")
    start_img = temp_dir / "kf_test_start.png"
    end_img = temp_dir / "kf_test_end.png"
    _make_test_image(start_img)
    _make_test_image(end_img)

    scraper = FastGenScraper()
    await scraper.start()
    try:
        await scraper._authenticate()
        await scraper._activate_video_tab()
        await scraper._select_video_settings()

        page = scraper._page
        assert page is not None

        # 1) Keyframes toggle
        ok = await _toggle_keyframes_mode(page)
        if not ok:
            raise RuntimeError("Не удалось включить режим keyframes.")
        print("[FLOW] Keyframes toggle: OK")

        # 2) Upload start/end images
        up_start = await _upload_keyframe_start(page, start_img)
        if not up_start:
            raise RuntimeError("Не удалось прикрепить START изображение.")
        print("[FLOW] Start image upload: OK")

        up_end = await _upload_keyframe_end(page, end_img)
        if not up_end:
            raise RuntimeError("Не удалось прикрепить END изображение.")
        print("[FLOW] End image upload: OK")

        # 3) Fill prompt
        prompt_el, prompt_sel = await _find_first(page, _PROMPT_SELECTORS, timeout=10000)
        if not prompt_el or not prompt_sel:
            raise RuntimeError("Поле промпта не найдено.")
        prompt = "Cinematic construction timelapse, realistic workers, stable camera."
        await _react_fill(page, prompt_sel, prompt)
        await asyncio.sleep(0.4)
        print(f"[FLOW] Prompt fill: OK ({prompt_sel})")

        # 4) Generate button presence + click
        gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=7000)
        if not gen_el:
            raise RuntimeError("Кнопка Generate не найдена.")
        disabled = await gen_el.get_attribute("disabled")
        if disabled is None:
            await gen_el.click()
            await asyncio.sleep(0.8)
            print(f"[FLOW] Generate click: OK ({gen_sel})")
        else:
            print(f"[FLOW] Generate found but disabled ({gen_sel})")

        print("test_fastgen_keyframes_flow_live.py: PASS")
        await asyncio.sleep(2.0)
    finally:
        await scraper.stop()


if __name__ == "__main__":
    asyncio.run(main())
