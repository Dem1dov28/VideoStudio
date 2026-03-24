"""
Playwright scraper for fast-gen.ai web generator.
Auth: API key via input[type=password] -> "Проверить"
Images returned as blob: URLs -> extracted via JS fetch + FileReader
"""

from __future__ import annotations

import asyncio
import base64
import os
import random
import time
from pathlib import Path

from loguru import logger
from playwright.async_api import (
    Browser, BrowserContext, Page, async_playwright,
    TimeoutError as PlaywrightTimeout,
)

from config import settings

_URL = "https://fast-gen.ai/generator"
SCREENSHOT_DIR = Path("output/debug_screenshots")

_KEY_INPUT   = "input[type='password']"
_CHECK_BTN   = "button:has-text('Проверить')"
_ERROR_TEXT  = "лицензия не найдена"
_SUCCESS_KW  = ["task queue", "generate", "imagen", "banana", "model", "промпт", "prompt"]

_PROMPT_SELECTORS = [
    "[placeholder*='промпт' i]",
    "textarea",
    "[placeholder*='prompt' i]",
    "[placeholder*='описание' i]",
    "[placeholder*='введите' i]",
    "input[type='text'][placeholder]",
    "[contenteditable='true']",
]
_GENERATE_SELECTORS = [
    "button[type='submit']",
    "button:has-text('Генерировать')",
    "button:has-text('Создать')",
    "button:has-text('Generate')",
    "button:has-text('Create')",
    "button:has-text('Запустить')",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _screenshot(page: Page, name: str) -> None:
    """Save debug screenshot. Silently skips if page/browser is closed."""
    if not settings.fastgen_headless:
        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
            await page.screenshot(path=str(path), full_page=False)
            logger.debug(f"Screenshot: {path}")
        except Exception as e:
            logger.debug(f"Screenshot skipped ({name}): {e}")


async def _find_first(page: Page, selectors: list[str], timeout: int = 5000):
    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=timeout)
            return el, sel
        except PlaywrightTimeout:
            continue
    return None, None


async def _collect_image_srcs(page: Page) -> set[str]:
    """Collect all img src values currently on the page."""
    srcs: set[str] = set()
    try:
        results = await page.evaluate("""() =>
            Array.from(document.images)
                .map(img => img.src)
                .filter(src => src && src.length > 10)
        """)
        srcs = set(results)
    except Exception:
        pass
    return srcs


async def _download_blob(page: Page, blob_url: str) -> bytes:
    """
    Download a blob: URL by fetching it inside the browser context
    via JavaScript and returning base64-encoded data.
    """
    b64 = await page.evaluate("""async (url) => {
        const response = await fetch(url);
        const blob = await response.blob();
        return await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(',')[1]);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }""", blob_url)
    return base64.b64decode(b64)


async def _react_fill(page: Page, selector: str, text: str) -> None:
    """
    Fill a React-controlled input properly:
    1. Click to focus
    2. Select all & delete existing text
    3. Use nativeInputValueSetter to set value
    4. Dispatch 'input' and 'change' events so React state updates
    """
    await page.click(selector)
    await asyncio.sleep(0.1)
    # Use JS to set value and fire React events
    await page.evaluate("""([sel, val]) => {
        const el = document.querySelector(sel);
        if (!el) return;
        // React overrides the value setter, so we grab the native one
        const proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [selector, text])


async def _collect_video_srcs(page: Page) -> set[str]:
    """Collect all video src values currently on the page."""
    srcs: set[str] = set()
    try:
        results = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('video'))
                .map(v => v.src || v.querySelector('source')?.src)
                .filter(src => src && src.length > 10)
        """)
        srcs = set(r for r in results if r)
    except Exception:
        pass
    return srcs


# Тексты на странице, указывающие на ошибку генерации видео (перегенерируем сразу)
# Важно: не использовать "error"/"ошибка" — они слишком общие и дают ложные срабатывания
_VIDEO_ERROR_KEYWORDS = [
    "audio filtered",
    "content policy",
    "content filtered",
    "blocked",
    "rejected",
    "политика контента",
    "заблокирован",
    "отклонен",
    "generation failed",
    "video failed",
    "не удалось сгенерировать",
    "невозможно создать",
    "try again",
    "попробуйте снова",
    "попробуйте другой",
    "error generating",
    "ошибка генерации",
    "something went wrong",
    "что-то пошло не так",
    "failed to generate",
    "unable to generate",
]


async def _check_video_page_errors(page: Page) -> str | None:
    """Проверить страницу на сообщения об ошибке генерации. None = ошибки нет."""
    try:
        text = (await page.evaluate("() => document.body?.innerText ?? ''")) or ""
        lower = text.lower()
        for kw in _VIDEO_ERROR_KEYWORDS:
            if kw in lower:
                return f"Video generation error detected: '{kw}'"
    except Exception:
        pass
    return None


class VideoGenerationError(RuntimeError):
    """Ошибка генерации, обнаруженная на странице (можно перегенерировать)."""
    pass


async def _wait_for_new_video(
    page: Page, before: set[str], timeout_s: int = 300
) -> list[str]:
    logger.info(f"[FastGen] Waiting for video generation (timeout {timeout_s}s) ...")
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    last_error_check = time.monotonic()
    elapsed = 0
    ERROR_CHECK_INTERVAL = 10  # проверка на ошибки раз в 10 секунд
    while time.monotonic() < deadline:
        current = await _collect_video_srcs(page)
        new = current - before
        if new:
            logger.success(f"[FastGen] Video ready after ~{int(elapsed)}s")
            return list(new)

        # Раз в 10 секунд — проверка на сообщения об ошибке (раньше перегенерируем)
        if time.monotonic() - last_error_check >= ERROR_CHECK_INTERVAL:
            err = await _check_video_page_errors(page)
            if err:
                logger.warning(f"[FastGen] {err} — retrying earlier")
                raise VideoGenerationError(err)
            last_error_check = time.monotonic()

        await asyncio.sleep(4)
        elapsed += 4
        if time.monotonic() - last_log >= 20:
            remaining = int(deadline - time.monotonic())
            logger.info(f"[FastGen] Still generating video ... {int(elapsed)}s elapsed, {remaining}s left")
            last_log = time.monotonic()
    raise TimeoutError(f"[FastGen] No video appeared within {timeout_s}s")


_IMAGE_UPLOAD_SELECTORS = [
    # fast-gen.ai "Референсные изображения" (0/3) — dropzone for reference images
    "div:has-text('Референсные изображения') input[type='file']",
    "label:has-text('Перетащите референсные изображения')",
    "div:has-text('Перетащите референсные изображения') input[type='file']",
    "[class*='dropzone']:has-text('Перетащите') input[type='file']",
    "input[type='file'][accept*='image']",
    "input[type='file']",
    "[data-testid*='upload'] input[type='file']",
]

async def _upload_reference_image(page: Page, image_path: Path) -> bool:
    """Upload image into fast-gen.ai «Референсные изображения» dropzone. Returns True if succeeded."""
    if not image_path or not image_path.exists():
        return False
    resolved = str(image_path.resolve())
    # 1) Try direct file input (including inside reference images section)
    for sel in _IMAGE_UPLOAD_SELECTORS:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="attached", timeout=2000)
            if "input" in sel:
                await loc.set_input_files(resolved)
            else:
                # Label/dropzone: click to focus, then find and use file input
                await loc.click()
                await asyncio.sleep(0.3)
                inp = page.locator("input[type='file']").first
                await inp.set_input_files(resolved)
            logger.info(f"[FastGen] Reference image uploaded: {image_path.name}")
            await asyncio.sleep(1.5)
            return True
        except Exception as e:
            logger.debug(f"[FastGen] Selector {sel} failed: {e}")
            continue
    # 2) Fallback: click dropzone by text, then set_input_files on any file input
    for btn in [
        "label:has-text('Перетащите')",
        "div:has-text('Перетащите референсные изображения')",
        "button:has-text('Upload')", "button:has-text('Загрузить')",
        "label:has(input[type='file'])", "[data-dropzone]",
    ]:
        try:
            el = page.locator(btn).first
            await el.wait_for(state="visible", timeout=1500)
            await el.click()
            await asyncio.sleep(0.5)
            inp = page.locator("input[type='file']").first
            await inp.wait_for(state="attached", timeout=2000)
            await inp.set_input_files(str(image_path.resolve()))
            logger.info(f"[FastGen] Reference image uploaded via {btn}: {image_path.name}")
            await asyncio.sleep(1)
            return True
        except Exception:
            continue
    logger.warning("[FastGen] Could not find image upload UI — proceeding without reference image")
    return False


async def _upload_multiple_reference_images(page: Page, image_paths: list[Path]) -> int:
    """
    Upload multiple images into fast-gen.ai «Референсные изображения» dropzone.
    Returns number of successfully uploaded images.
    FastGen limit: 3 reference images max.
    """
    if not image_paths:
        return 0
    
    # FastGen limit is 3 reference images
    MAX_REFS = 3
    images_to_upload = image_paths[:MAX_REFS]
    
    uploaded = 0
    for i, img_path in enumerate(images_to_upload):
        if not img_path.exists():
            logger.warning(f"[FastGen] Image not found: {img_path}")
            continue
        
        # Click the "+" dropzone to add another image slot
        # The button is: <div class="aspect-square flex flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors cursor-pointer border-border hover:border-muted-foreground">
        if i > 0:  # Skip for first image (slot already open)
            try:
                # Exact selector matching the HTML structure provided by user
                add_btn = page.locator('div.aspect-square.flex.flex-col.items-center.justify-center.rounded-lg.border-2.border-dashed.cursor-pointer').first
                if await add_btn.is_visible(timeout=2000):
                    await add_btn.click()
                    await asyncio.sleep(0.5)
                    logger.debug(f"[FastGen] Clicked add button for image {i+1}")
                else:
                    # Fallback: try with has-text("+") if exact class not found
                    add_btn_fallback = page.locator('div[class*="aspect-square"][class*="border-dashed"]:has-text("+")').first
                    if await add_btn_fallback.is_visible(timeout=1500):
                        await add_btn_fallback.click()
                        await asyncio.sleep(0.5)
                        logger.debug(f"[FastGen] Clicked fallback add button for image {i+1}")
                    else:
                        logger.warning(f"[FastGen] Could not find add button for image {i+1}, trying upload anyway")
            except Exception as e:
                logger.debug(f"[FastGen] Add button click failed: {e}")
        
        # Upload the image
        if await _upload_reference_image(page, img_path):
            uploaded += 1
            logger.info(f"[FastGen] Uploaded {uploaded}/{len(images_to_upload)}: {img_path.name}")
        else:
            logger.warning(f"[FastGen] Failed to upload: {img_path.name}")
    
    logger.info(f"[FastGen] Total reference images uploaded: {uploaded}/{len(images_to_upload)} (max {MAX_REFS})")
    return uploaded


async def _clear_reference_image(page: Page) -> bool:
    """Try to remove uploaded reference image (for switching from img2img to text2img)."""
    for sel in [
        "button[aria-label*='remove' i]", "button[aria-label*='удалить' i]",
        "[data-testid*='remove']", "button:has-text('×')", "button:has-text('Remove')",
        "button:has-text('Удалить')", "img[alt*='ref'] + button",
    ]:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=800)
            await btn.click()
            await asyncio.sleep(0.5)
            logger.debug("[FastGen] Cleared reference image")
            return True
        except Exception:
            continue
    return False


async def _wait_for_new_image(
    page: Page, before: set[str], timeout_s: int = 180
) -> list[str]:
    logger.info(f"[FastGen] Waiting for image generation (timeout {timeout_s}s) ...")
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    elapsed = 0
    while time.monotonic() < deadline:
        current = await _collect_image_srcs(page)
        new = current - before
        if new:
            logger.success(f"[FastGen] Image ready after ~{int(elapsed)}s")
            return list(new)
        await asyncio.sleep(3)
        elapsed += 3
        # Log progress every 15 seconds so the user sees it's alive
        if time.monotonic() - last_log >= 15:
            remaining = int(deadline - time.monotonic())
            logger.info(f"[FastGen] Still generating ... {int(elapsed)}s elapsed, {remaining}s left")
            last_log = time.monotonic()
    raise TimeoutError(f"[FastGen] No image appeared within {timeout_s}s — check fast-gen.ai site")


# ── Scraper class ──────────────────────────────────────────────────────────────

class FastGenScraper:
    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._authenticated = False
        self._prompt_selector: str | None = None  # cache after first find

    async def start(self) -> None:
        if not settings.fastgen_api_key:
            raise ValueError(
                "\nFASTGEN_API_KEY is not set in .env!\n"
                "Get your key at: https://fast-gen.ai\n"
            )
        logger.info("[FastGen] Launching Chromium browser ...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.fastgen_headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ru-RU",
        )
        self._page = await self._context.new_page()
        logger.info(f"[FastGen] Browser started (headless={settings.fastgen_headless})")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()

    async def _authenticate(self) -> None:
        page = self._page
        assert page is not None
        logger.info(f"[FastGen] Navigating to {_URL} ...")
        await page.goto(_URL, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)
        await _screenshot(page, "01_login_page")

        body = (await page.evaluate("() => document.body.innerText")).lower()
        if any(kw in body for kw in _SUCCESS_KW):
            logger.info("Already authenticated")
            self._authenticated = True
            return

        inp = page.locator(_KEY_INPUT).first
        await inp.wait_for(state="visible", timeout=8000)
        logger.info("Entering API key ...")
        await inp.fill(settings.fastgen_api_key)
        await asyncio.sleep(0.3)

        await page.locator(_CHECK_BTN).first.click()
        await asyncio.sleep(4)
        await _screenshot(page, "02_after_auth")

        body = (await page.evaluate("() => document.body.innerText")).lower()
        if _ERROR_TEXT in body:
            raise ValueError("fast-gen.ai rejected the API key — check FASTGEN_API_KEY in .env")

        logger.success("Authentication successful!")
        self._authenticated = True

    async def _select_model(self) -> None:
        model = settings.fastgen_model
        if not model:
            return
        page = self._page
        assert page is not None
        try:
            sel_el = page.locator("select").first
            await sel_el.wait_for(state="visible", timeout=3000)
            await sel_el.select_option(label=model)
            logger.info(f"Model '{model}' selected")
            # Close any open Radix dropdowns to avoid overlay interception
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Could not select model: {e}")

    async def _activate_image_tab(self) -> None:
        page = self._page
        assert page is not None
        for sel in ["button:has-text('Image')", "button:has-text('Изображение')",
                    "[role='tab']:has-text('Image')"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=2000)
                await el.click()
                await asyncio.sleep(0.5)
                return
            except Exception:
                continue

    async def _activate_video_tab(self) -> None:
        page = self._page
        assert page is not None
        for sel in ["button:has-text('Video')", "button:has-text('Видео')",
                    "[role='tab']:has-text('Video')", "[role='tab']:has-text('Видео')"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=2000)
                await el.click()
                await asyncio.sleep(0.8)
                return
            except Exception:
                continue

    async def _select_aspect_ratio(self) -> None:
        """Select 9:16 (vertical) aspect ratio via the second <select> on the page."""
        page = self._page
        assert page is not None
        try:
            # Page has two <select>: first = model, second = aspect ratio
            ratio_select = page.locator("select").nth(1)
            await ratio_select.wait_for(state="attached", timeout=3000)
            await ratio_select.select_option(value="9:16")
            logger.info("Aspect ratio set to 9:16 (vertical)")
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Could not set aspect ratio: {e}")

    async def _select_video_settings(self) -> None:
        """
        Video tab: model & aspect ratio. UI differs from Image tab.
        - Model: skip (FASTGEN_MODEL is for images; video has different models — use default)
        - Aspect: try select/buttons for 9:16 vertical
        """
        page = self._page
        assert page is not None

        # Skip model — Image model names don't exist in Video tab dropdown
        # Video tab uses different models (Flow, Kling, etc.)

        # Aspect ratio: try multiple strategies (Video tab DOM may differ)
        async def _try_select(loc, timeout=2000):
            try:
                await loc.wait_for(state="attached", timeout=timeout)
                for opt in [{"value": "9:16"}, {"label": "9:16"}, {"label": "9: 16"}, {"label": "Portrait"}]:
                    try:
                        await loc.select_option(**opt)
                        return True
                    except Exception:
                        continue
                return False
            except Exception:
                return False

        for sel, idx in [("select", 1), ("select", 0)]:
            loc = page.locator(sel) if idx < 0 else page.locator(sel).nth(idx)
            if await _try_select(loc):
                logger.info("[FastGen Video] Aspect ratio 9:16 selected")
                return

        # Fallback: click button containing 9:16 or portrait
        for btn_sel in [
            "button:has-text('9:16')",
            "[role='button']:has-text('9:16')",
            "button:has-text('portrait')",
            "button:has-text('Portrait')",
        ]:
            try:
                btn = page.locator(btn_sel).first
                await btn.wait_for(state="visible", timeout=1500)
                await btn.click()
                logger.info(f"[FastGen Video] Clicked {btn_sel} for vertical")
                return
            except Exception:
                continue

        logger.warning("[FastGen Video] Could not set 9:16 — using default aspect ratio")

    async def generate(
        self,
        prompt: str,
        output_dir: Path,
        index: int | None = None,
        reference_image_path: Path | None = None,
    ) -> list[Path]:
        """Generate image. If reference_image_path provided, uses img2img (reference + prompt)."""
        page = self._page
        assert page is not None, "Call start() first"

        mode = "img2img" if reference_image_path and reference_image_path.exists() else "text2img"
        logger.info(f"[FastGen] Generating image ({mode}) for prompt: {prompt[:80]}...")
        if not self._authenticated:
            await self._authenticate()

        await self._activate_image_tab()
        await self._select_model()
        await self._select_aspect_ratio()

        if reference_image_path and reference_image_path.exists():
            await _upload_reference_image(page, Path(reference_image_path))
            await asyncio.sleep(1)
        else:
            await _clear_reference_image(page)

        await _screenshot(page, "03_ready")

        # Find prompt input (use cached selector if available)
        if self._prompt_selector:
            sel = self._prompt_selector
        else:
            _, sel = await _find_first(page, _PROMPT_SELECTORS, timeout=10000)
            if not sel:
                await _screenshot(page, "error_no_prompt")
                raise RuntimeError("Prompt input not found. Set FASTGEN_HEADLESS=false to debug.")
            self._prompt_selector = sel
            logger.info(f"Found prompt input: {sel}")

        # Fill prompt using React-compatible approach (fires input events)
        await _react_fill(page, sel, prompt)
        await asyncio.sleep(0.5)
        await _screenshot(page, "04_prompt_typed")

        # Click generate — wait for button to become enabled after input
        gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
        if not gen_el:
            await _screenshot(page, "error_no_gen_btn")
            raise RuntimeError("Generate button not found.")

        timeout_s = max(60, settings.fastgen_image_timeout)
        max_attempts = max(1, settings.fastgen_max_attempts)
        new_srcs: list[str] = []
        last_err: TimeoutError | None = None

        for attempt in range(max_attempts):
            if attempt > 0:
                gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                if not gen_el:
                    await _screenshot(page, "error_no_gen_btn_retry")
                    raise RuntimeError("Generate button not found on retry.")

            # Snapshot right before each click (new img src must differ from this set)
            images_before = await _collect_image_srcs(page)

            # Wait up to 5s for button to become enabled
            for _ in range(10):
                disabled = await gen_el.get_attribute("disabled")
                if disabled is None:
                    break
                await asyncio.sleep(0.5)

            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            if attempt > 0:
                logger.warning(
                    f"[FastGen] Retry {attempt + 1}/{max_attempts} "
                    f"(timeout was {timeout_s}s) ..."
                )

            logger.info(f"Clicking: {gen_sel}")
            await page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (el) el.click();
            }""", gen_sel)
            await asyncio.sleep(2)
            await _screenshot(page, "05_generating")

            try:
                new_srcs = await _wait_for_new_image(
                    page, images_before, timeout_s=timeout_s
                )
                break
            except TimeoutError as e:
                last_err = e
                await _screenshot(page, f"timeout_attempt_{attempt + 1}")
                if attempt + 1 >= max_attempts:
                    raise
                await asyncio.sleep(2)

        if not new_srcs and last_err:
            raise last_err

        logger.success(f"Got {len(new_srcs)} new image(s)")
        await _screenshot(page, "06_result")

        # Download images — handle both blob: and http: URLs
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        base_suffix = str(index) if index is not None else "0"
        for src in new_srcs[:1]:
            dest = output_dir / f"frame_{int(time.time())}_{base_suffix}.jpg"
            try:
                if src.startswith("blob:"):
                    # Extract blob content via JS
                    img_bytes = await _download_blob(page, src)
                elif src.startswith("data:"):
                    img_bytes = base64.b64decode(src.split(",", 1)[1])
                else:
                    response = await page.request.get(src)
                    img_bytes = await response.body()

                dest.write_bytes(img_bytes)
                logger.success(f"Saved: {dest} ({dest.stat().st_size // 1024} KB)")
                saved.append(dest)
            except Exception as e:
                logger.error(f"Could not save image: {e}")

        # Clear prompt for next call
        try:
            await page.fill(sel, "")
        except Exception:
            pass

        return saved

    async def generate_video_with_references(
        self,
        prompt: str,
        output_dir: Path,
        index: int = 0,
        reference_image_paths: list[Path] | None = None,
    ) -> Path | None:
        """
        Generate video via fast-gen.ai Video tab with MULTIPLE reference images.
        Uploads all character images as references for consistent character appearance.
        Returns path to saved .mp4 or None on failure.
        """
        page = self._page
        assert page is not None, "Call start() first"

        logger.info(f"[FastGen] Generating video with {len(reference_image_paths) if reference_image_paths else 0} references: {prompt[:80]}...")
        if not self._authenticated:
            await self._authenticate()

        await self._activate_video_tab()
        await self._select_video_settings()
        await _screenshot(page, "03_video_ready")

        # Upload ALL reference images
        if reference_image_paths:
            valid_paths = [p for p in reference_image_paths if p.exists()]
            if valid_paths:
                await _upload_multiple_reference_images(page, valid_paths)
                await _screenshot(page, "03b_video_after_multi_upload")

        if self._prompt_selector:
            sel = self._prompt_selector
        else:
            _, sel = await _find_first(page, _PROMPT_SELECTORS, timeout=10000)
            if not sel:
                raise RuntimeError("Prompt input not found.")
            self._prompt_selector = sel

        await _react_fill(page, sel, prompt)
        await asyncio.sleep(0.5)
        await _screenshot(page, "04_video_prompt_typed")

        gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
        if not gen_el:
            raise RuntimeError("Generate button not found.")

        timeout_s = max(120, settings.fastgen_image_timeout * 2)
        max_attempts = max(1, settings.fastgen_max_attempts)
        new_srcs: list[str] = []

        for attempt in range(max_attempts):
            if attempt > 0:
                gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                if not gen_el:
                    raise RuntimeError("Generate button not found on retry.")
                try:
                    await page.fill(sel, "")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await _react_fill(page, sel, prompt)
                await asyncio.sleep(0.5)
                logger.warning(
                    f"[FastGen] Retry {attempt + 1}/{max_attempts} for video "
                    "(previous attempt failed: timeout or content filtered) ..."
                )

            videos_before = await _collect_video_srcs(page)

            for _ in range(10):
                disabled = await gen_el.get_attribute("disabled")
                if disabled is None:
                    break
                await asyncio.sleep(0.5)

            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            await gen_el.click()
            await asyncio.sleep(2)
            await _screenshot(page, f"05_video_generating{'_retry' + str(attempt) if attempt > 0 else ''}")

            try:
                new_srcs = await _wait_for_new_video(page, videos_before, timeout_s=timeout_s)
            except (TimeoutError, VideoGenerationError) as e:
                err_type = "error" if isinstance(e, VideoGenerationError) else "timeout"
                await _screenshot(page, f"{err_type}_video{'_retry' + str(attempt) if attempt > 0 else ''}")
                logger.warning(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt + 1 >= max_attempts:
                    logger.error(f"[FastGen] All {max_attempts} attempts exhausted, giving up")
                    return None
                logger.info(f"[FastGen] Retrying generation ({attempt + 2}/{max_attempts}) ...")
                await asyncio.sleep(3)
                continue

            if not new_srcs:
                if attempt + 1 >= max_attempts:
                    return None
                await asyncio.sleep(2)
                continue

            break

        if not new_srcs:
            return None

        # Download the first new video
        video_url = new_srcs[0]
        ext = ".mp4"
        out_path = output_dir / f"video_{index:03d}{ext}"
        
        try:
            if video_url.startswith("blob:"):
                data = await _download_blob(page, video_url)
                out_path.write_bytes(data)
            else:
                import httpx
                async with httpx.AsyncClient() as client:
                    r = await client.get(video_url, timeout=60)
                    r.raise_for_status()
                    out_path.write_bytes(r.content)
            logger.success(f"[FastGen] Video saved: {out_path.name}")
            return out_path
        except Exception as e:
            logger.error(f"[FastGen] Failed to download video: {e}")
            return None

    async def generate_video(
        self,
        prompt: str,
        output_dir: Path,
        index: int = 0,
        reference_image_path: Path | str | None = None,
        upload_reference: bool = True,
    ) -> Path | None:
        """
        Generate video via fast-gen.ai Video tab.
        If reference_image_path and upload_reference, uploads image once (для последующих клипов достаточно менять промпт).
        Returns path to saved .mp4 or None on failure.
        """
        page = self._page
        assert page is not None, "Call start() first"

        logger.info(f"[FastGen] Generating video for prompt: {prompt[:80]}...")
        if not self._authenticated:
            await self._authenticate()

        await self._activate_video_tab()
        await self._select_video_settings()  # Video tab: skip model, try 9:16
        await _screenshot(page, "03_video_ready")

        # Референс — загружаем 1 раз, затем только меняем промпты
        if reference_image_path and upload_reference:
            path = Path(reference_image_path)
            await _upload_reference_image(page, path)
            await _screenshot(page, "03b_video_after_image_upload")

        if self._prompt_selector:
            sel = self._prompt_selector
        else:
            _, sel = await _find_first(page, _PROMPT_SELECTORS, timeout=10000)
            if not sel:
                raise RuntimeError("Prompt input not found.")
            self._prompt_selector = sel

        await _react_fill(page, sel, prompt)
        await asyncio.sleep(0.5)
        await _screenshot(page, "04_video_prompt_typed")

        gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
        if not gen_el:
            raise RuntimeError("Generate button not found.")

        timeout_s = max(120, settings.fastgen_image_timeout * 2)
        max_attempts = max(1, settings.fastgen_max_attempts)
        new_srcs: list[str] = []

        for attempt in range(max_attempts):
            if attempt > 0:
                gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                if not gen_el:
                    raise RuntimeError("Generate button not found on retry.")
                # Clear and re-fill prompt (reset error state like "Audio filtered")
                try:
                    await page.fill(sel, "")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await _react_fill(page, sel, prompt)
                await asyncio.sleep(0.5)
                logger.warning(
                    f"[FastGen] Retry {attempt + 1}/{max_attempts} for video "
                    "(previous attempt failed: timeout or content filtered) ..."
                )

            videos_before = await _collect_video_srcs(page)

            for _ in range(10):
                disabled = await gen_el.get_attribute("disabled")
                if disabled is None:
                    break
                await asyncio.sleep(0.5)

            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            await gen_el.click()
            await asyncio.sleep(2)
            await _screenshot(page, f"05_video_generating{'_retry' + str(attempt) if attempt > 0 else ''}")

            try:
                new_srcs = await _wait_for_new_video(page, videos_before, timeout_s=timeout_s)
            except (TimeoutError, VideoGenerationError) as e:
                err_type = "error" if isinstance(e, VideoGenerationError) else "timeout"
                await _screenshot(page, f"{err_type}_video{'_retry' + str(attempt) if attempt > 0 else ''}")
                logger.warning(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt + 1 >= max_attempts:
                    logger.error(f"[FastGen] All {max_attempts} attempts exhausted, giving up")
                    return None
                logger.info(f"[FastGen] Retrying generation ({attempt + 2}/{max_attempts}) ...")
                await asyncio.sleep(3)  # пауза перед повтором
                continue

            if not new_srcs:
                if attempt + 1 >= max_attempts:
                    return None
                await asyncio.sleep(2)
                continue

            break

        if not new_srcs:
            return None

        logger.success("Got new video")
        await _screenshot(page, "06_video_result")

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / f"clip_{index:03d}.mp4"
        src = new_srcs[0]
        try:
            if src.startswith("blob:"):
                vid_bytes = await _download_blob(page, src)
            elif src.startswith("data:"):
                vid_bytes = base64.b64decode(src.split(",", 1)[1])
            else:
                response = await page.request.get(src)
                vid_bytes = await response.body()

            dest.write_bytes(vid_bytes)
            logger.success(f"Saved video: {dest} ({dest.stat().st_size // 1024} KB)")
            return dest
        except Exception as e:
            logger.error(f"Could not save video: {e}")
            return None
        finally:
            try:
                if sel:
                    await page.fill(sel, "")
            except Exception:
                pass


# ── Sync entry point (runs in a separate thread) ───────────────────────────────

def _run_single_image_sync(index: int, prompt: str, output_dir: Path) -> Path | None:
    """Генерация одного изображения в отдельном браузере. Для параллельного запуска."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            paths = await scraper.generate(prompt, output_dir, index=index)
            return paths[0] if paths else None
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_sync(prompts: list[str], output_dir: Path) -> list[Path]:
    """
    Synchronous wrapper that runs Playwright in its own event loop.
    Sequential generation — используется для одиночных промптов (outro и т.п.).

    Must be called via asyncio.to_thread() to avoid conflicts with uvicorn's
    event loop (Playwright's subprocess management can deadlock when sharing
    an existing asyncio loop).
    """
    import asyncio as _asyncio

    async def _inner() -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        scraper = FastGenScraper()
        await scraper.start()
        try:
            all_paths: list[Path] = []
            for prompt in prompts:
                paths = await scraper.generate(prompt, output_dir)
                all_paths.extend(paths)
                await _asyncio.sleep(1)
            return all_paths
        finally:
            await scraper.stop()

    # Create a fresh event loop isolated from uvicorn's loop
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_img2img_chain_sync(
    steps: list[tuple[str, int | None]],
    output_dir: Path,
) -> list[Path]:
    """
    Sequential chain. Each step: (prompt, ref_step_index).
    ref_step_index=None → text2img. ref_step_index=i → img2img using result[i] as ref.
    Returns list of generated image paths.
    """
    import asyncio as _asyncio

    async def _inner() -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        scraper = FastGenScraper()
        await scraper.start()
        result: list[Path] = []
        try:
            for i, (prompt, ref_idx) in enumerate(steps):
                ref_path = Path(result[ref_idx]) if ref_idx is not None else None
                paths = await scraper.generate(
                    prompt, output_dir, index=i, reference_image_path=ref_path
                )
                if paths:
                    result.append(Path(paths[0]))
                else:
                    raise RuntimeError(f"[FastGen] Step {i + 1} failed: no image")
                await _asyncio.sleep(1)
            return result
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_images_parallel_sync(prompts: list[str], output_dir: Path) -> list[Path]:
    """Параллельная генерация изображений — каждое в своём окне браузера (Mode 1 и др.)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)
    workers = min(
        len(prompts),
        max(1, getattr(settings, "fastgen_image_parallel_workers", 5)),
    )
    logger.info(f"[FastGen] Generating {len(prompts)} images in parallel ({workers} workers) ...")

    result: list[Path | None] = [None] * len(prompts)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_single_image_sync, i, prompts[i], output_dir): i
            for i in range(len(prompts))
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result[idx] = future.result()
            except Exception as e:
                logger.error(f"[FastGen] Image {idx} failed: {e}")
                result[idx] = None

    out = [result[i] for i in range(len(result))]
    if None in out:
        raise RuntimeError("[FastGen] Some images failed to generate")
    return out


def _run_single_video_sync(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_path: Path | None,
) -> Path | None:
    """Генерация одного видео в отдельном браузере. Для параллельного запуска."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            # Всегда загружаем reference, если он есть (Mode 3: последний кадр предыдущего клипа)
            upload_ref = bool(reference_image_path)
            return await scraper.generate_video(
                prompt, output_dir, index=index,
                reference_image_path=reference_image_path,
                upload_reference=upload_ref,
            )
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_video_sync(
    prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path | None = None,
) -> list[Path | None]:
    """Генерация видео параллельно — каждое в своём окне браузера."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)
    ref = Path(reference_image_path) if reference_image_path else None
    workers = min(
        len(prompts),
        max(1, getattr(settings, "fastgen_video_parallel_workers", 10)),
    )
    logger.info(f"[FastGen] Generating {len(prompts)} videos in parallel ({workers} workers) ...")

    result: list[Path | None] = [None] * len(prompts)  # preserve order

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_single_video_sync,
                i, prompts[i], output_dir, ref,
            ): i
            for i in range(len(prompts))
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result[idx] = future.result()
            except Exception as e:
                logger.error(f"[FastGen] Video {idx} failed: {e}")
                result[idx] = None

    return result


async def generate_videos_fastgen(
    prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path | None = None,
) -> list[Path | None]:
    """Generate videos via fast-gen.ai Video tab. Returns list of paths or None for failures."""
    logger.info("[FastGen] Starting video generation in isolated thread ...")
    return await asyncio.to_thread(
        _run_fastgen_video_sync, prompts, output_dir, reference_image_path
    )


async def generate_single_video_fastgen(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_path: str | Path | None,
) -> Path | None:
    """Сгенерировать одно видео с заданным reference. Для цепочки."""
    return await asyncio.to_thread(
        _run_single_video_sync,
        index, prompt, output_dir, Path(reference_image_path) if reference_image_path else None,
    )


# ── Mode 6: Multiple references support ───────────────────────────────────────

def _run_single_video_multi_ref_sync(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_paths: list[Path],
) -> Path | None:
    """Generate video with MULTIPLE reference images (for Mode 6)."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            return await scraper.generate_video_with_references(
                prompt, output_dir, index=index,
                reference_image_paths=reference_image_paths,
            )
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_video_multi_ref_sync(
    prompts: list[str],
    output_dir: Path,
    reference_image_paths: list[Path],
) -> list[Path | None]:
    """Generate videos in parallel with MULTIPLE reference images per video."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)
    workers = min(
        len(prompts),
        max(1, getattr(settings, "fastgen_video_parallel_workers", 10)),
    )
    logger.info(f"[FastGen] Generating {len(prompts)} videos with {len(reference_image_paths)} refs each ({workers} workers) ...")

    result: list[Path | None] = [None] * len(prompts)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_single_video_multi_ref_sync,
                i, prompts[i], output_dir, reference_image_paths,
            ): i
            for i in range(len(prompts))
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result[idx] = future.result()
            except Exception as e:
                logger.error(f"[FastGen] Video {idx} failed: {e}")
                result[idx] = None

    return result


async def generate_videos_fastgen_multi_ref(
    prompts: list[str],
    output_dir: Path,
    reference_image_paths: list[Path],
) -> list[Path | None]:
    """
    Generate videos via fast-gen.ai with MULTIPLE reference images.
    Each video gets ALL reference images uploaded.
    For Mode 6: Cartoon Drama with multiple character references.
    """
    logger.info(f"[FastGen] Starting parallel video generation with {len(reference_image_paths)} references per video ...")
    return await asyncio.to_thread(
        _run_fastgen_video_multi_ref_sync, prompts, output_dir, reference_image_paths
    )


async def generate_single_video_multi_ref(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_paths: list[Path],
) -> Path | None:
    """
    Generate SINGLE video with MULTIPLE reference images.
    For Mode 6: Each scene with its specific characters.
    """
    return await asyncio.to_thread(
        _run_single_video_multi_ref_sync,
        index, prompt, output_dir, reference_image_paths,
    )


# ── Async entry point ──────────────────────────────────────────────────────────

async def generate_images_chain_fastgen(
    steps: list[tuple[str, int | None]],
    output_dir: Path,
) -> list[Path]:
    """Run img2img chain: steps = [(prompt, ref_step_index), ...]. ref_step_index=None = text2img."""
    return await asyncio.to_thread(_run_img2img_chain_sync, steps, output_dir)


async def generate_images_fastgen(
    prompts: list[str], output_dir: Path, parallel: bool = True
) -> list[Path]:
    """
    Generate images via fast-gen.ai.
    - parallel=True и len(prompts)>1: параллельная генерация (несколько браузеров).
    - parallel=False или 1 промпт: последовательная генерация (один браузер).

    Mode 3 (цепочка) вызывает с parallel=False. Mode 1 и др. — с parallel=True.
    """
    if parallel and len(prompts) > 1:
        logger.info("[FastGen] Starting parallel image generation ...")
        return await asyncio.to_thread(
            _run_fastgen_images_parallel_sync, prompts, output_dir
        )
    logger.info("[FastGen] Starting sequential image generation ...")
    return await asyncio.to_thread(_run_fastgen_sync, prompts, output_dir)