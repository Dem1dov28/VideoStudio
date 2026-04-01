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
import threading
import time
from pathlib import Path

from loguru import logger
from playwright.async_api import (
    Browser, BrowserContext, Page, async_playwright,
    Error as PlaywrightError,
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
    1. Click to focus (with force=True to bypass overlays)
    2. Select all & delete existing text
    3. Use nativeInputValueSetter to set value
    4. Dispatch 'input' and 'change' events so React state updates
    """
    # Try force click first (bypasses overlay interception like <html> intercepts pointer events)
    try:
        await page.click(selector, force=True)
    except Exception:
        # Fallback: JS-based focus and click
        try:
            await page.evaluate("""(sel) => {
                const el = document.querySelector(sel);
                if (el) { el.focus(); el.click(); }
            }""", selector)
        except Exception:
            pass
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


async def _count_error_blocks(page: Page) -> int:
    """
    Count error blocks in the error container.
    """
    try:
        count = await page.evaluate("""() => {
            const errorDivs = document.querySelectorAll('div[data-slot="scroll-area"] div[class*="bg-destructive"]');
            return errorDivs.length;
        }""")
        return int(count) if count else 0
    except Exception as e:
        if not _is_browser_closed_error(e):
            logger.debug(f"[FastGen] Could not count error blocks: {e}")
        return 0


async def _wait_for_error_count_increase(page: Page, initial_count: int, timeout_s: int = 60) -> bool:
    """
    Wait until the error count on page increases.
    Returns True if error count increased, False if timeout.
    """
    deadline = time.monotonic() + timeout_s
    check_interval = 2
    
    while time.monotonic() < deadline:
        current_count = await _count_error_blocks(page)
        if current_count > initial_count:
            logger.info(f"[FastGen] Error count increased: {initial_count} → {current_count}")
            return True
        await asyncio.sleep(check_interval)
    
    logger.warning(f"[FastGen] Error count did not increase within {timeout_s}s (still {initial_count})")
    return False


class VideoGenerationError(RuntimeError):
    """Ошибка генерации, обнаруженная на странице (можно перегенерировать)."""
    pass


class FastGenCancelled(Exception):
    """Пользователь отменил пайплайн — закрыть Chromium в worker-потоке."""
    pass


def _cancel_requested(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _is_browser_closed_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "has been closed" in msg
        or "target closed" in msg
        or "browser has been closed" in msg
        or "context has been closed" in msg
        or "connection closed" in msg
    )


# Время через которое нужно нажать кнопку генерации снова (7 минут = 420 секунд)
REGEN_INTERVAL_SECONDS = 420  # 7 минут


async def _wait_for_new_video_with_regen(
    page: Page,
    before: set[str],
    timeout_s: int = 600,
    gen_button_el = None,
    gen_button_sel: str = None,
) -> list[str]:
    """
    Wait for video generation with error-count-based retry.
    
    Logic:
    1. Get initial error count at start
    2. Wait for video to appear
    3. If error detected: wait for error count to increase, then click Generate
    
    IMPORTANT: Only click Generate when error count increases.
    This prevents queue overflow from multiple rapid clicks.
    """
    logger.info(f"[FastGen] Waiting for video generation (timeout {timeout_s}s) ...")
    
    # Get initial error count
    initial_error_count = await _count_error_blocks(page)
    logger.info(f"[FastGen] Initial error count: {initial_error_count}")
    
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    last_error_check = time.monotonic()
    elapsed = 0
    ERROR_CHECK_INTERVAL = 10
    
    while time.monotonic() < deadline:
        current = await _collect_video_srcs(page)
        new = current - before
        if new:
            logger.success(f"[FastGen] Video ready after ~{int(elapsed)}s")
            return list(new)

        # Check for errors every 10 seconds
        if time.monotonic() - last_error_check >= ERROR_CHECK_INTERVAL:
            current_error_count = await _count_error_blocks(page)
            if current_error_count > initial_error_count:
                logger.warning(f"[FastGen] Error count increased ({initial_error_count} -> {current_error_count}). UI regen aborted.")
                raise VideoGenerationError("FastGen error block detected, UI regen aborted.")
            
            # Additional check for generic textual errors
            err = await _check_video_page_errors(page)
            if err:
                logger.warning(f"[FastGen] Textual error detected: {err}. UI regen aborted.")
                raise VideoGenerationError("FastGen textual error detected, UI regen aborted.")
                
            last_error_check = time.monotonic()

        await asyncio.sleep(4)
        elapsed += 4
        if time.monotonic() - last_log >= 20:
            remaining = int(deadline - time.monotonic())
            logger.info(f"[FastGen] Still generating video ... {int(elapsed)}s elapsed, {remaining}s left")
            last_log = time.monotonic()
            
    raise TimeoutError(f"[FastGen] No video appeared within {timeout_s}s")


async def _wait_for_new_image_with_regen(
    page: Page,
    before: set[str],
    timeout_s: int = 600,
    gen_button_el = None,
    gen_button_sel: str = None,
) -> list[str]:
    """
    Wait for image generation with error-count-based retry.
    
    Logic:
    1. Get initial error count at start
    2. Wait for image to appear
    3. If error detected: wait for error count to increase, then click Generate
    
    IMPORTANT: Only click Generate when error count increases.
    This prevents queue overflow from multiple rapid clicks.
    """
    logger.info(f"[FastGen] Waiting for image generation (timeout {timeout_s}s) ...")
    
    # Get initial error count
    initial_error_count = await _count_error_blocks(page)
    logger.info(f"[FastGen] Initial error count: {initial_error_count}")
    
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    last_error_check = time.monotonic()
    elapsed = 0
    ERROR_CHECK_INTERVAL = 10
    
    while time.monotonic() < deadline:
        current = await _collect_image_srcs(page)
        new = current - before
        if new:
            logger.success(f"[FastGen] Image ready after ~{int(elapsed)}s")
            return list(new)
        
        # Check for errors every 10 seconds
        if time.monotonic() - last_error_check >= ERROR_CHECK_INTERVAL:
            current_error_count = await _count_error_blocks(page)
            if current_error_count > initial_error_count:
                logger.warning(f"[FastGen] Error count increased ({initial_error_count} -> {current_error_count}). UI regen aborted.")
                raise VideoGenerationError("FastGen error block detected, UI regen aborted.")
            
            # Additional check for generic textual errors
            err = await _check_video_page_errors(page)
            if err:
                logger.warning(f"[FastGen] Textual error detected: {err}. UI regen aborted.")
                raise VideoGenerationError("FastGen textual error detected, UI regen aborted.")
                
            last_error_check = time.monotonic()
        
        await asyncio.sleep(3)
        elapsed += 3
        if time.monotonic() - last_log >= 15:
            remaining = int(deadline - time.monotonic())
            logger.info(f"[FastGen] Still generating ... {int(elapsed)}s elapsed, {remaining}s left")
            last_log = time.monotonic()
            
    raise TimeoutError(f"[FastGen] No image appeared within {timeout_s}s")


async def _wait_for_new_video(
    page: Page,
    before: set[str],
    timeout_s: int = 300,
    cancel_event: threading.Event | None = None,
) -> list[str]:
    logger.info(f"[FastGen] Waiting for video generation (timeout {timeout_s}s) ...")
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    last_error_check = time.monotonic()
    elapsed = 0
    ERROR_CHECK_INTERVAL = 10  # проверка на ошибки раз в 10 секунд
    tick = 1.0 if cancel_event is not None else 4.0
    while time.monotonic() < deadline:
        if _cancel_requested(cancel_event):
            raise FastGenCancelled()
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

        await asyncio.sleep(tick)
        elapsed += tick
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

async def _upload_reference_images(page: Page, image_paths: list[Path]) -> bool:
    """
    Upload one or more images into «Референсные изображения» (0/3).
    Uses multi-file set_input_files when possible.
    """
    paths = [Path(p) for p in image_paths if p and Path(p).exists()]
    if not paths:
        return False
    resolved = [str(p.resolve()) for p in paths]
    names = ", ".join(p.name for p in paths)
    # 1) Try direct file input (including inside reference images section)
    for sel in _IMAGE_UPLOAD_SELECTORS:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="attached", timeout=2000)
            if "input" in sel:
                if len(resolved) == 1:
                    await loc.set_input_files(resolved[0])
                else:
                    await loc.set_input_files(resolved)
            else:
                await loc.click()
                await asyncio.sleep(0.3)
                inp = page.locator("input[type='file']").first
                if len(resolved) == 1:
                    await inp.set_input_files(resolved[0])
                else:
                    await inp.set_input_files(resolved)
            logger.info(f"[FastGen] Reference image(s) uploaded ({len(paths)}): {names}")
            await asyncio.sleep(1.5 + 0.5 * (len(paths) - 1))
            return True
        except Exception as e:
            logger.debug(f"[FastGen] Selector {sel} failed: {e}")
            continue
    # 2) Fallback: sequential single-file uploads
    for btn in [
        "label:has-text('Перетащите')",
        "div:has-text('Перетащите референсные изображения')",
        "button:has-text('Upload')", "button:has-text('Загрузить')",
        "label:has(input[type='file'])", "[data-dropzone]",
    ]:
        try:
            ok = 0
            for one in resolved:
                el = page.locator(btn).first
                await el.wait_for(state="visible", timeout=1500)
                await el.click()
                await asyncio.sleep(0.4)
                inp = page.locator("input[type='file']").first
                await inp.wait_for(state="attached", timeout=2000)
                await inp.set_input_files(one)
                await asyncio.sleep(1.2)
                ok += 1
            if ok == len(resolved):
                logger.info(f"[FastGen] Reference image(s) uploaded sequentially: {names}")
                return True
        except Exception:
            continue
    logger.warning("[FastGen] Could not find image upload UI — proceeding without reference image")
    return False


async def _upload_reference_image(page: Page, image_path: Path) -> bool:
    """Upload single image (wrapper)."""
    return await _upload_reference_images(page, [image_path])


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


async def _try_apply_img2img_strength(page: Page, strength_raw: float) -> bool:
    """
    Пытается выставить силу img2img на странице FastGen (range slider).
    strength_raw: 0–1 (как denoise в SD) или 0–100 (трактуем как проценты слайдера).
    Источник рекомендаций: низкая сила лучше сохраняет геометрию (типично 0.15–0.35 для SD).
    """
    try:
        frac = strength_raw / 100.0 if strength_raw > 1.0 else float(strength_raw)
        frac = max(0.02, min(0.95, frac))
        applied = await page.evaluate(
            """(frac) => {
            const bad = ['volume','громкость','zoom','масштаб','opacity','прозрач'];
            const good = [
              'strength','denois','шум','сила','референс','reference','creativity',
              'креатив','влияние','similarity','similar','match','img2img','image strength'
            ];
            const ranges = Array.from(document.querySelectorAll('input[type="range"]'));
            if (ranges.length === 0) return { ok: false, reason: 'no range inputs' };
            let best = null;
            let bestScore = -1;
            if (ranges.length === 1) {
              best = ranges[0];
            } else {
              for (const r of ranges) {
                const rct = r.getBoundingClientRect();
                if (rct.width < 8 || rct.height < 4) continue;
                let ctx = '';
                let el = r;
                for (let d = 0; d < 6 && el; d++) {
                  ctx += ' ' + (el.innerText || '').slice(0, 400).toLowerCase();
                  el = el.parentElement;
                }
                const al = ((r.getAttribute('aria-label') || '') + ' ' + (r.name || '')).toLowerCase();
                ctx = (ctx + ' ' + al).toLowerCase();
                if (bad.some(b => ctx.includes(b))) continue;
                const hits = good.filter(g => ctx.includes(g)).length;
                const score = hits;
                if (score > bestScore) { bestScore = score; best = r; }
              }
              if (!best || bestScore < 1) return { ok: false, reason: 'ambiguous sliders' };
            }
            const mx = parseFloat(best.max);
            const mn = parseFloat(best.min) || 0;
            const maxV = Number.isFinite(mx) && mx > 0 ? mx : 1;
            let v = maxV <= 1 ? frac : frac * 100;
            v = Math.min(maxV, Math.max(mn, v));
            best.value = String(v);
            best.dispatchEvent(new Event('input', { bubbles: true }));
            best.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: true, value: v, max: maxV };
        }""",
            frac,
        )
        if applied and applied.get("ok"):
            logger.info(
                f"[FastGen] Img2img strength slider set (~{frac:.2f} logical) → UI value {applied.get('value')}/{applied.get('max')}"
            )
            await asyncio.sleep(0.4)
            return True
        logger.debug(f"[FastGen] Img2img strength slider not applied: {applied}")
    except Exception as e:
        logger.debug(f"[FastGen] Img2img strength UI tweak skipped: {e}")
    return False


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
    page: Page,
    before: set[str],
    timeout_s: int = 180,
    cancel_event: threading.Event | None = None,
) -> list[str]:
    logger.info(f"[FastGen] Waiting for image generation (timeout {timeout_s}s) ...")
    deadline = time.monotonic() + timeout_s
    last_log = time.monotonic()
    elapsed = 0
    tick = 1.0 if cancel_event is not None else 3.0
    while time.monotonic() < deadline:
        if _cancel_requested(cancel_event):
            raise FastGenCancelled()
        current = await _collect_image_srcs(page)
        new = current - before
        if new:
            logger.success(f"[FastGen] Image ready after ~{int(elapsed)}s")
            return list(new)
        await asyncio.sleep(tick)
        elapsed += tick
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
        """Stop browser and playwright with proper error handling for shutdown scenarios."""
        # Close browser first
        if self._browser:
            try:
                # Check if browser is still connected before closing
                if hasattr(self._browser, 'is_connected') and self._browser.is_connected():
                    await self._browser.close()
                    logger.debug("[FastGen] Browser closed successfully")
                else:
                    logger.debug("[FastGen] Browser already disconnected, skipping close")
            except Exception as e:
                # Ignore errors during shutdown - browser may already be closed
                logger.debug(f"[FastGen] Browser close error (expected during shutdown): {e}")
            finally:
                self._browser = None
        
        # Close context if exists
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        
        # Close page if exists
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        
        # Stop playwright last
        if getattr(self, "_playwright", None):
            try:
                await self._playwright.stop()
                logger.debug("[FastGen] Playwright stopped successfully")
            except Exception as e:
                # Ignore errors during shutdown
                logger.debug(f"[FastGen] Playwright stop error (expected during shutdown): {e}")
            finally:
                self._playwright = None

    async def _recover_page_in_same_browser(self) -> bool:
        """
        Вкладка закрылась, но процесс Chromium ещё жив — открываем новую вкладку в том же окне,
        без stop()+start() (иначе пользователь видит «закрыли окно и открыли новое»).
        """
        try:
            br = self._browser
            ctx = self._context
            if not br or not ctx:
                return False
            try:
                if not br.is_connected():
                    return False
            except Exception:
                return False
            if self._page is not None:
                try:
                    await self._page.close()
                except Exception:
                    pass
            self._page = await ctx.new_page()
            self._authenticated = False
            self._prompt_selector = None
            logger.info("[FastGen] Новая вкладка в том же браузере (Chromium не перезапускаем)")
            return True
        except Exception as e:
            logger.warning(f"[FastGen] Не удалось открыть вкладку в том же браузере: {e}")
            return False

    async def _restart_playwright_session(self) -> None:
        """Полный перезапуск Chromium — только если браузер мёртв или нельзя восстановить вкладку."""
        logger.warning("[FastGen] Restarting Playwright session (full browser restart) ...")
        await self.stop()
        self._authenticated = False
        self._prompt_selector = None
        await self.start()

    async def restart_browser(self) -> None:
        """Safely restart only the browser context without killing the Playwright driver."""
        logger.info("[FastGen] Completely restarting browser context (Soft Restart)...")
        if self._page:
            try: await self._page.close()
            except Exception: pass
            self._page = None
            
        if self._context:
            try: await self._context.close()
            except Exception: pass
            self._context = None
            
        self._authenticated = False
        self._prompt_selector = None
        
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
        logger.info("[FastGen] New clean Browser context ready.")

    async def _authenticate(self) -> None:
        page = self._page
        assert page is not None
        logger.info(f"[FastGen] Navigating to {_URL} ...")
        
        # Retry navigation with increased timeout
        for nav_attempt in range(3):
            try:
                await page.goto(_URL, wait_until="domcontentloaded", timeout=90000)
                # Wait a bit for network to settle, but don't require full networkidle
                await asyncio.sleep(5)
                break
            except Exception as e:
                logger.warning(f"[FastGen] Navigation attempt {nav_attempt+1}/3 failed: {e}")
                if nav_attempt == 2:
                    raise
                await asyncio.sleep(3)
        
        await _screenshot(page, "01_login_page")

        body = (await page.evaluate("() => document.body.innerText")).lower()
        if any(kw in body for kw in _SUCCESS_KW):
            logger.info("Already authenticated")
            self._authenticated = True
            # Wait for page to fully load before proceeding
            # Purpose: Ensure Radix UI components are initialized
            # Trigger: After detecting already authenticated state
            # Termination: Proceeds after networkidle or 5s timeout
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(1)
            return

        # Wait for the page to fully load with retry
        logger.info("[FastGen] Waiting for login form...")
        for attempt in range(3):
            try:
                inp = page.locator(_KEY_INPUT).first
                await inp.wait_for(state="visible", timeout=15000)
                break
            except Exception as e:
                logger.warning(f"[FastGen] Login form not ready (attempt {attempt+1}/3): {e}")
                await asyncio.sleep(2)
                await page.reload(wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(3)
        else:
            raise TimeoutError("[FastGen] Could not find API key input field after 3 attempts")
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
        # Wait for page to fully load after authentication
        # Purpose: Ensure all UI components (including combobox) are initialized
        # Trigger: After successful authentication
        # Termination: Proceeds after networkidle or 5s timeout
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await asyncio.sleep(1)

    async def _select_model(self) -> None:
        """Select model from FastGen dropdown (Radix UI combobox) with retry logic.
        
        FastGen uses Radix UI Select which renders:
        - A visible <button role="combobox"> (may be obscured by overlays)
        - A hidden <select aria-hidden="true" tabindex="-1"> with 1px size
        - A dropdown with [role="option"] items when opened
        
        Strategy:
        1. Try JavaScript-based value selection on the hidden <select> + dispatch change event
        2. Try force-clicking the combobox button to open dropdown, then click the option
        3. Fall back to keyboard navigation
        """
        model = settings.fastgen_model
        if not model:
            return
        page = self._page
        assert page is not None
        
        # Wait for page to be fully loaded before attempting model selection
        await asyncio.sleep(2)
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"[FastGen] Model selection attempt {attempt}/{max_retries}")
                
                # Log available options from hidden <select> for debugging
                try:
                    sel_el = page.locator("select").first
                    await sel_el.wait_for(state="attached", timeout=3000)
                    options_info = await page.evaluate("""() => {
                        const sel = document.querySelector('select');
                        if (!sel) return [];
                        return Array.from(sel.options).map(o => ({
                            value: o.value, 
                            label: o.textContent.trim()
                        }));
                    }""")
                    logger.info(f"[FastGen] Available model options: {options_info}")
                except Exception as e:
                    logger.debug(f"[FastGen] Could not read select options: {e}")
                    options_info = []
                
                # Step 1: Try JavaScript-based selection on hidden <select>
                # This bypasses all visibility/actionability checks
                # The model value can be either a value attribute (e.g. "GEM_PIX_2") 
                # or a label text (e.g. "Nano Banana Pro - Flow")
                try:
                    js_result = await page.evaluate("""(modelQuery) => {
                        const sel = document.querySelector('select');
                        if (!sel) return {ok: false, error: 'no select element'};
                        
                        // Try to find option by value first
                        let option = sel.querySelector(`option[value="${modelQuery}"]`);
                        
                        // Try by label text (partial match)
                        if (!option) {
                            for (const opt of sel.options) {
                                if (opt.textContent.trim().includes(modelQuery) || 
                                    modelQuery.includes(opt.textContent.trim())) {
                                    option = opt;
                                    break;
                                }
                            }
                        }
                        
                        // Try by value partial match
                        if (!option) {
                            for (const opt of sel.options) {
                                if (opt.value.includes(modelQuery) || 
                                    modelQuery.includes(opt.value)) {
                                    option = opt;
                                    break;
                                }
                            }
                        }
                        
                        if (!option) return {ok: false, error: 'option not found'};
                        
                        // Set the value
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLSelectElement.prototype, 'value'
                        ).set;
                        nativeInputValueSetter.call(sel, option.value);
                        
                        // Dispatch events to trigger React state update
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        sel.dispatchEvent(new Event('input', {bubbles: true}));
                        
                        return {ok: true, value: option.value, label: option.textContent.trim()};
                    }""", model)
                    
                    if js_result.get("ok"):
                        logger.info(f"[FastGen] Model selected via JS: value='{js_result['value']}', label='{js_result['label']}'")
                        await asyncio.sleep(0.5)
                        # Verify selection took effect by checking combobox text
                        # If not, continue to combobox click approach
                except Exception as e:
                    logger.debug(f"[FastGen] JS select approach failed: {e}")
                
                # Step 2: Click the combobox button with force=True to open dropdown
                # force=True bypasses Playwright's actionability checks (visibility, overlay)
                combobox = page.locator('button[role="combobox"]').first
                await combobox.wait_for(state="attached", timeout=5000)
                
                # Try force click first (bypasses overlay/visibility issues)
                try:
                    await combobox.click(force=True)
                    logger.debug("[FastGen] Combobox force-clicked, waiting for dropdown...")
                except Exception as e:
                    logger.debug(f"[FastGen] Force click failed: {e}, trying JS click...")
                    # Fallback: JavaScript click bypasses all Playwright checks
                    await page.evaluate("""() => {
                        const btn = document.querySelector('button[role="combobox"]');
                        if (btn) btn.click();
                    }""")
                    logger.debug("[FastGen] Combobox clicked via JS")
                
                # Wait for dropdown to open
                await asyncio.sleep(1.5)
                
                # Step 3: Try to click the desired option in the opened dropdown
                # Radix dropdown renders [role="option"] items
                try:
                    # Try exact text match first, then partial
                    for selector in [
                        f'[role="option"]:has-text("{model}")',
                        f'[role="listbox"] [role="option"]:has-text("{model}")',
                        f'div[data-radix-popper-content-wrapper] [role="option"]:has-text("{model}")',
                    ]:
                        try:
                            option = page.locator(selector).first
                            await option.wait_for(state="visible", timeout=2000)
                            await option.click()
                            logger.info(f"[FastGen] Model '{model}' selected via dropdown option click")
                            await asyncio.sleep(0.5)
                            return
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"[FastGen] Dropdown option click failed: {e}")
                
                # Step 4: Try selecting by value on hidden select with Playwright
                try:
                    sel_el = page.locator("select").first
                    await sel_el.wait_for(state="attached", timeout=2000)
                    # Try by value attribute (e.g. "GEM_PIX_2")
                    await sel_el.select_option(value=model, timeout=2000)
                    logger.info(f"[FastGen] Model '{model}' selected via native select value")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    return
                except Exception:
                    pass
                
                # Try by label
                try:
                    sel_el = page.locator("select").first
                    await sel_el.select_option(label=model, timeout=2000)
                    logger.info(f"[FastGen] Model '{model}' selected via native select label")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    return
                except Exception:
                    pass
                
                # Step 5: Close dropdown and check if JS selection from Step 1 worked
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                
                # If JS approach succeeded earlier, we're good
                if js_result and js_result.get("ok"):
                    logger.info(f"[FastGen] Using JS-selected model: {js_result['label']}")
                    return
                
                raise Exception(f"Could not select model '{model}' via any method")
                    
            except Exception as e:
                logger.warning(f"[FastGen] Model selection attempt {attempt} failed: {e}")
                # Close any open dropdown before retry
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                    
                if attempt < max_retries:
                    wait_time = 2 * attempt
                    logger.info(f"[FastGen] Retrying model selection in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[FastGen] Failed to select model after {max_retries} attempts")
                    try:
                        all_options = await page.locator('select option').all_inner_texts()
                        logger.info(f"[FastGen] Available model options: {all_options}")
                    except Exception:
                        pass

    async def _activate_image_tab(self) -> None:
        page = self._page
        assert page is not None
        for sel in ["button:has-text('Image')", "button:has-text('Изображение')",
                    "[role='tab']:has-text('Image')"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=2000)
                await el.click()
                # Wait for tab content to load
                # Purpose: Ensure Image tab UI (including model combobox) is ready
                # Trigger: After clicking Image tab
                # Termination: Proceeds after networkidle or 3s timeout, plus 0.5s delay
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
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
        cancel_event: threading.Event | None = None,
    ) -> list[Path]:
        """Generate image. If reference_image_path provided, uses img2img (reference + prompt)."""
        page = self._page
        assert page is not None, "Call start() first"

        if _cancel_requested(cancel_event):
            raise FastGenCancelled()

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
            strength = getattr(settings, "fastgen_img2img_strength", None)
            if strength is not None:
                await _try_apply_img2img_strength(page, float(strength))
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
            if _cancel_requested(cancel_event):
                raise FastGenCancelled()
            if attempt > 0:
                gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                if not gen_el:
                    await _screenshot(page, "error_no_gen_btn_retry")
                    raise RuntimeError("Generate button not found on retry.")
            
            # Snapshot right before each click (new img src must differ from this set)
            images_before = await _collect_image_srcs(page)
            
            # Wait up to 5s for button to become enabled
            for _ in range(10):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                disabled = await gen_el.get_attribute("disabled")
                if disabled is None:
                    break
                await asyncio.sleep(0.5)
            
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            
            if attempt > 0:
                # After TimeoutError: check if button is still disabled (generation in progress)
                # This can happen if _wait_for_new_image_with_regen clicked Generate recently
                disabled = await gen_el.get_attribute("disabled")
                if disabled is not None:
                    logger.warning("[FastGen] Generate button still disabled after timeout - generation may still be in progress")
                    # Wait a bit more for the button to become enabled
                    for _ in range(10):
                        disabled = await gen_el.get_attribute("disabled")
                        if disabled is None:
                            break
                        await asyncio.sleep(0.5)
                    if disabled is not None:
                        logger.warning("[FastGen] Button still disabled after 5s - skipping retry click")
                        await asyncio.sleep(2)
                        continue
                            
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
                if cancel_event is not None:
                    new_srcs = await _wait_for_new_image(
                        page, images_before, timeout_s=timeout_s, cancel_event=cancel_event
                    )
                else:
                    new_srcs = await _wait_for_new_image_with_regen(
                        page, images_before, timeout_s=timeout_s,
                        gen_button_el=gen_el, gen_button_sel=gen_sel
                    )
                break
            except FastGenCancelled:
                raise
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

    async def generate_with_multiple_references(
        self,
        prompt: str,
        output_dir: Path,
        index: int | None = None,
        reference_image_paths: list[Path] | None = None,
    ) -> list[Path]:
        """
        Generate image with MULTIPLE reference images (character photos).
        Uploads all character images as references for consistent appearance.
        """
        page = self._page
        assert page is not None, "Call start() first"

        num_refs = len(reference_image_paths) if reference_image_paths else 0
        logger.info(f"[FastGen] Generating image with {num_refs} reference(s): {prompt[:80]}...")
        if not self._authenticated:
            await self._authenticate()

        await self._activate_image_tab()
        await self._select_model()
        await self._select_aspect_ratio()

        # Upload ALL reference images (character photos)
        if reference_image_paths:
            valid_paths = [p for p in reference_image_paths if p.exists()]
            if valid_paths:
                await _upload_multiple_reference_images(page, valid_paths)
                await asyncio.sleep(1)
        else:
            await _clear_reference_image(page)

        await _screenshot(page, "03_ready_multi_ref")

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
                # After TimeoutError: check if button is still disabled (generation in progress)
                # This can happen if _wait_for_new_image_with_regen clicked Generate recently
                disabled = await gen_el.get_attribute("disabled")
                if disabled is not None:
                    logger.warning("[FastGen] Generate button still disabled after timeout - generation may still be in progress")
                    # Wait a bit more for the button to become enabled
                    for _ in range(10):
                        disabled = await gen_el.get_attribute("disabled")
                        if disabled is None:
                            break
                        await asyncio.sleep(0.5)
                    if disabled is not None:
                        logger.warning("[FastGen] Button still disabled after 5s - skipping retry click")
                        await asyncio.sleep(2)
                        continue
                            
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
                new_srcs = await _wait_for_new_image_with_regen(
                    page, images_before, timeout_s=timeout_s,
                    gen_button_el=gen_el, gen_button_sel=gen_sel
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
            videos_before = await _collect_video_srcs(page)

            # First attempt: click Generate to start
            # Subsequent attempts (after TimeoutError): click Generate for retry
            # Error-triggered retries: handled by _wait_for_new_video_with_regen
            if attempt == 0:
                for _ in range(10):
                    disabled = await gen_el.get_attribute("disabled")
                    if disabled is None:
                        break
                    await asyncio.sleep(0.5)

                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)

                await gen_el.click()
                await asyncio.sleep(2)
                await _screenshot(page, "05_video_generating")
                logger.info(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} started")

            try:
                new_srcs = await _wait_for_new_video_with_regen(
                    page, videos_before, timeout_s=timeout_s,
                    gen_button_el=gen_el, gen_button_sel=gen_sel
                )
            except TimeoutError as e:
                await _screenshot(page, f"timeout_video{'_retry' + str(attempt) if attempt > 0 else ''}")
                logger.warning(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} timeout: {e}")
                if attempt + 1 >= max_attempts:
                    logger.error(f"[FastGen] All {max_attempts} attempts exhausted, giving up")
                    return None
                # Timeout means: after last Generate click, no video appeared within timeout
                # This is a genuine retry situation - click Generate for next attempt
                logger.info(f"[FastGen] Clicking Generate for retry {attempt + 2}...")
                try:
                    gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                    if gen_el:
                        disabled = await gen_el.get_attribute("disabled")
                        if disabled is None:
                            await gen_el.click()
                            logger.info("[FastGen] Generate button clicked for retry")
                        else:
                            logger.warning("[FastGen] Generate button is disabled")
                except Exception as click_err:
                    logger.warning(f"[FastGen] Could not click Generate: {click_err}")
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
        reference_image_paths: list[Path | str] | None = None,
        upload_reference: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> Path | None:
        """
        Generate video via fast-gen.ai Video tab.
        reference_image_paths: несколько референсов (напр. экстерьер + интерьер для финала).
        Если задан reference_image_paths — он приоритетнее reference_image_path.
        Returns path to saved .mp4 or None on failure.
        """
        page = self._page
        assert page is not None, "Call start() first"

        logger.info(f"[FastGen] Generating video for prompt: {prompt[:80]}...")

        if _cancel_requested(cancel_event):
            return None

        # Референс(ы) — при полном переоткрытии UI загружаем снова
        ref_list: list[Path] = []
        if reference_image_paths:
            ref_list = [Path(p) for p in reference_image_paths if p and Path(p).exists()]
        elif reference_image_path:
            p = Path(reference_image_path)
            if p.exists():
                ref_list = [p]

        timeout_s = max(120, settings.fastgen_image_timeout * 2)
        max_attempts = max(1, settings.fastgen_max_attempts)
        new_srcs: list[str] = []
        sel: str | None = None

        for attempt in range(max_attempts):
            if _cancel_requested(cancel_event):
                logger.info("[FastGen] Video generation cancelled before attempt")
                return None
            if self._page is None or self._page.is_closed():
                if not await self._recover_page_in_same_browser():
                    await self._restart_playwright_session()

            page = self._page
            assert page is not None
            # После _restart_playwright_session() _authenticated == False → полный UI заново
            do_full_ui = attempt == 0 or not self._authenticated

            if do_full_ui:
                if not self._authenticated:
                    await self._authenticate()
                if _cancel_requested(cancel_event):
                    return None
                await self._activate_video_tab()
                await self._select_video_settings()
                await _screenshot(page, "03_video_ready" if attempt == 0 else "03_video_ready_recover")
                if ref_list and upload_reference:
                    await _upload_reference_images(page, ref_list)
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
            else:
                assert sel is not None
                # Повтор без полного UI: страница могла сбросить референс — загрузить снова
                if ref_list and upload_reference:
                    await _upload_reference_images(page, ref_list)
                    await asyncio.sleep(0.8)
                    await _screenshot(page, "03b_video_ref_reupload_retry")
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

            gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
            if not gen_el:
                raise RuntimeError(
                    "Generate button not found." + (" On retry, browser may have closed." if attempt else "")
                )

            videos_before = await _collect_video_srcs(page)

            for _ in range(10):
                if _cancel_requested(cancel_event):
                    return None
                disabled = await gen_el.get_attribute("disabled")
                if disabled is None:
                    break
                await asyncio.sleep(0.5)

            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            await gen_el.click()
            await asyncio.sleep(2)
            await _screenshot(page, "05_video_generating")
            logger.info(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} started")

            try:
                if cancel_event is not None:
                    new_srcs = await _wait_for_new_video(
                        page, videos_before, timeout_s=timeout_s, cancel_event=cancel_event
                    )
                else:
                    new_srcs = await _wait_for_new_video_with_regen(
                        page, videos_before, timeout_s=timeout_s,
                        gen_button_el=gen_el, gen_button_sel=gen_sel
                    )
            except FastGenCancelled:
                logger.info("[FastGen] Video wait cancelled — closing browser")
                return None
            except PlaywrightError as e:
                if not _is_browser_closed_error(e):
                    raise
                logger.warning(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} — session lost: {e}")
                if attempt + 1 >= max_attempts:
                    logger.error(f"[FastGen] All {max_attempts} attempts exhausted, giving up")
                    return None
                self._authenticated = False
                self._prompt_selector = None
                await asyncio.sleep(2)
                continue
            except (TimeoutError, VideoGenerationError) as e:
                err_type = "error" if isinstance(e, VideoGenerationError) else "timeout"
                await _screenshot(page, f"{err_type}_video{'_retry' + str(attempt) if attempt > 0 else ''}")
                logger.warning(f"[FastGen] Video attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt + 1 >= max_attempts:
                    logger.error(f"[FastGen] All {max_attempts} attempts exhausted, giving up")
                    return None
                if page.is_closed():
                    self._authenticated = False
                    self._prompt_selector = None
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

        page = self._page
        assert page is not None

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
                if sel and self._page and not self._page.is_closed():
                    await self._page.fill(sel, "")
            except Exception:
                pass


# ── Sync entry point (runs in a separate thread) ───────────────────────────────

def _run_single_image_sync(
    index: int,
    prompt: str,
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Генерация одного изображения в отдельном браузере. Для параллельного запуска."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            if _cancel_requested(cancel_event):
                return None
            paths = await scraper.generate(
                prompt, output_dir, index=index, cancel_event=cancel_event
            )
            return paths[0] if paths else None
        except FastGenCancelled:
            return None
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_single_image_with_refs_sync(
    index: int,
    prompt: str,
    reference_image_paths: list[Path],
    output_dir: Path,
) -> Path | None:
    """Генерация одного изображения с multiple references в отдельном браузере."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            for attempt in range(3):
                try:
                    paths = await scraper.generate_with_multiple_references(
                        prompt=prompt,
                        output_dir=output_dir,
                        index=index,
                        reference_image_paths=reference_image_paths,
                    )
                    return paths[0] if paths else None
                except VideoGenerationError as e:
                    logger.warning(f"[FastGen] Error caught during image generation (attempt {attempt+1}/3), restarting browser: {e}")
                    await scraper.restart_browser()
                    continue
            return None
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_sync(
    prompts: list[str],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
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
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                paths = await scraper.generate(prompt, output_dir, cancel_event=cancel_event)
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
    cancel_event: threading.Event | None = None,
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
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                ref_path = Path(result[ref_idx]) if ref_idx is not None else None
                paths = await scraper.generate(
                    prompt,
                    output_dir,
                    index=i,
                    reference_image_path=ref_path,
                    cancel_event=cancel_event,
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


def _run_img2img_chain_from_seed_sync(
    seed_image: Path,
    steps: list[tuple[str, int]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """
    Цепочка img2img от уже существующего кадра (не text2img).
    steps: (prompt, ref_index) — ref_index в массиве [seed, gen0, gen1, ...].
    Первый шаг обычно ref_index=0 (seed). Возвращает только сгенерированные пути.
    """
    import asyncio as _asyncio

    async def _inner() -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        scraper = FastGenScraper()
        await scraper.start()
        chain: list[Path] = [Path(seed_image).resolve()]
        generated: list[Path] = []
        try:
            for i, (prompt, ref_idx) in enumerate(steps):
                if _cancel_requested(cancel_event):
                    raise FastGenCancelled()
                if ref_idx < 0 or ref_idx >= len(chain):
                    raise ValueError(f"[FastGen] Invalid ref_idx {ref_idx} for chain len {len(chain)}")
                ref_path = chain[ref_idx]
                paths = await scraper.generate(
                    prompt,
                    output_dir,
                    index=200 + i,
                    reference_image_path=ref_path,
                    cancel_event=cancel_event,
                )
                if not paths:
                    raise RuntimeError(f"[FastGen] From-seed step {i + 1} failed: no image")
                new_p = Path(paths[0])
                chain.append(new_p)
                generated.append(new_p)
                await _asyncio.sleep(1)
            return generated
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _run_fastgen_images_parallel_sync(
    prompts: list[str],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
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
            executor.submit(
                _run_single_image_sync, i, prompts[i], output_dir, cancel_event
            ): i
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
        if _cancel_requested(cancel_event):
            raise FastGenCancelled()
        raise RuntimeError("[FastGen] Some images failed to generate")
    return out


def _run_fastgen_images_with_refs_parallel_sync(
    prompts_with_refs: list[tuple[str, list[Path]]],
    output_dir: Path,
    max_workers: int | None = None,
) -> list[Path]:
    """
    Параллельная генерация изображений с multiple references — каждое в своём окне браузера.
    Каждый prompt генерируется со своими reference изображениями (фото персонажей).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use provided max_workers or fall back to settings
    if max_workers is not None:
        workers = min(len(prompts_with_refs), max(1, max_workers))
    else:
        workers = min(
            len(prompts_with_refs),
            max(1, getattr(settings, "fastgen_image_parallel_workers", 5)),
        )
    logger.info(f"[FastGen] Generating {len(prompts_with_refs)} images with references in parallel ({workers} workers) ...")

    result: list[Path | None] = [None] * len(prompts_with_refs)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_single_image_with_refs_sync,
                i,
                prompts_with_refs[i][0],  # prompt
                prompts_with_refs[i][1],  # reference_image_paths
                output_dir,
            ): i
            for i in range(len(prompts_with_refs))
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result[idx] = future.result()
            except Exception as e:
                logger.error(f"[FastGen] Image {idx} with references failed: {e}")
                result[idx] = None

    out = [result[i] for i in range(len(result))]
    # Log summary of failures but don't raise - let caller handle partial results
    failed_count = sum(1 for r in out if r is None)
    if failed_count > 0:
        logger.warning(f"[FastGen] {failed_count}/{len(out)} images failed to generate")
    return out


def _run_single_video_sync(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_path: Path | None,
    reference_image_paths: list[Path] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """Генерация одного видео в отдельном браузере. Для параллельного запуска."""
    import asyncio as _asyncio

    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            if _cancel_requested(cancel_event):
                return None
            upload_ref = bool(reference_image_paths) or bool(reference_image_path)
            for attempt in range(3):
                try:
                    if _cancel_requested(cancel_event):
                        return None
                    return await scraper.generate_video(
                        prompt,
                        output_dir,
                        index=index,
                        reference_image_path=reference_image_path,
                        reference_image_paths=reference_image_paths,
                        upload_reference=upload_ref,
                        cancel_event=cancel_event,
                    )
                except VideoGenerationError as e:
                    logger.warning(
                        f"[FastGen] Video generation error (attempt {attempt + 1}/3), restarting browser: {e}"
                    )
                    if attempt >= 2:
                        return None
                    await scraper.restart_browser()
            return None
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
    cancel_event: threading.Event | None = None,
) -> list[Path | None]:
    """Генерация видео параллельно — каждое в своём окне браузера."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)
    ref = Path(reference_image_path) if reference_image_path else None
    if ref and ref.exists():
        logger.info(f"[FastGen] Reference image for all parallel clips: {ref.resolve()}")
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
                i,
                prompts[i],
                output_dir,
                ref,
                None,
                cancel_event,
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
    cancel_event: threading.Event | None = None,
) -> list[Path | None]:
    """Generate videos via fast-gen.ai Video tab. Returns list of paths or None for failures."""
    logger.info("[FastGen] Starting video generation in isolated thread ...")
    try:
        return await asyncio.to_thread(
            _run_fastgen_video_sync,
            prompts,
            output_dir,
            reference_image_path,
            cancel_event,
        )
    except FastGenCancelled:
        raise asyncio.CancelledError("FastGen cancelled") from None


async def generate_single_video_fastgen(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_path: str | Path | None = None,
    *,
    reference_image_paths: list[str | Path] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    """
    Сгенерировать одно видео с reference.
    reference_image_paths: несколько файлов (приоритетнее одного reference_image_path).
    """
    paths_arg: list[Path] | None = None
    if reference_image_paths:
        paths_arg = [Path(p) for p in reference_image_paths if p and Path(p).exists()]
        if not paths_arg:
            paths_arg = None
    single = Path(reference_image_path) if reference_image_path else None
    try:
        return await asyncio.to_thread(
            _run_single_video_sync,
            index,
            prompt,
            output_dir,
            single,
            paths_arg,
            cancel_event,
        )
    except FastGenCancelled:
        raise asyncio.CancelledError("FastGen cancelled") from None


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
            for attempt in range(3):
                try:
                    return await scraper.generate_video_with_references(
                        prompt, output_dir, index=index,
                        reference_image_paths=reference_image_paths,
                    )
                except VideoGenerationError as e:
                    logger.warning(f"[FastGen] Error caught during multi-ref video generation (attempt {attempt+1}/3), restarting browser: {e}")
                    await scraper.restart_browser()
                    continue
            return None
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


# ── Keyframe Video Generation (start + end frame) ────────────────────────────────

async def _toggle_keyframes_mode(page: Page) -> bool:
    """
    Enable keyframes mode on fast-gen.ai Video tab.
    Supports both old switch UI and new segmented-button UI.
    Returns True if successfully toggled to keyframes mode.
    """
    try:
        # Wait for page to be ready
        await asyncio.sleep(1)
        
        # Multiple selectors for the keyframes toggle
        toggle_selectors = [
            'button[role="switch"][id="use-keyframes"]',
            'button[role="switch"][data-state]',
            'button[role="switch"]',
            '[data-state][role="switch"]',
            'button[id*="keyframe"]',
            'button[id*="key-frame"]',
            # FastGen might use different selectors
            'button[class*="switch"]',
            'button[class*="toggle"]',
            'label:has(input[type="checkbox"])',
        ]
        
        for sel in toggle_selectors:
            try:
                switch = page.locator(sel).first
                if await switch.is_visible(timeout=2000):
                    # Check if this is the keyframes toggle
                    aria_checked = await switch.get_attribute("aria-checked")
                    data_state = await switch.get_attribute("data-state")
                    
                    # Click to enable if not already enabled
                    if aria_checked == "true" or data_state == "checked":
                        logger.info(f"[FastGen Keyframes] Already in keyframes mode (selector: {sel})")
                        return True
                    
                    await switch.click()
                    await asyncio.sleep(0.5)
                    
                    # Verify it's now checked
                    aria_checked = await switch.get_attribute("aria-checked")
                    data_state = await switch.get_attribute("data-state")
                    if aria_checked == "true" or data_state == "checked":
                        logger.info(f"[FastGen Keyframes] Keyframes mode enabled (selector: {sel})")
                        return True
            except Exception as e:
                logger.debug(f"[FastGen Keyframes] Toggle selector {sel} failed: {e}")
                continue

        # New FastGen UI: segmented control with "Ключ. кадры"/"Keyframes" button
        try:
            segmented_candidates = [
                'div.flex.rounded-lg.bg-secondary\\/50.p-0\\.5 button',
                'div[class*="rounded-lg"][class*="bg-secondary"] button',
                # New observed FastGen buttons (segmented control items)
                'button.flex-1.rounded-md.px-3.py-1\\.5.text-xs.font-medium.transition-colors[data-state]',
                'button[class*="rounded-md"][class*="px-3"][class*="py-1.5"][class*="text-xs"][data-state]',
            ]

            for container_sel in segmented_candidates:
                buttons = page.locator(container_sel)
                count = await buttons.count()
                if count == 0:
                    continue

                for i in range(count):
                    btn = buttons.nth(i)
                    try:
                        btn_text = ((await btn.inner_text()) or "").strip().lower()
                    except Exception:
                        continue

                    if (
                        "ключ" in btn_text
                        or "keyframe" in btn_text
                        or ("key" in btn_text and "frame" in btn_text)
                    ):
                        data_state = await btn.get_attribute("data-state")
                        aria_pressed = await btn.get_attribute("aria-pressed")
                        aria_selected = await btn.get_attribute("aria-selected")

                        is_active = (
                            data_state in {"open", "active", "checked"}
                            or aria_pressed == "true"
                            or aria_selected == "true"
                        )
                        if is_active:
                            logger.info("[FastGen Keyframes] Already in keyframes mode (segmented button)")
                            return True

                        await btn.click(force=True, timeout=2000)
                        await asyncio.sleep(0.4)

                        data_state = await btn.get_attribute("data-state")
                        aria_pressed = await btn.get_attribute("aria-pressed")
                        aria_selected = await btn.get_attribute("aria-selected")
                        is_active = (
                            data_state in {"open", "active", "checked"}
                            or aria_pressed == "true"
                            or aria_selected == "true"
                            or data_state != "closed"
                        )
                        if is_active:
                            logger.info("[FastGen Keyframes] Keyframes mode enabled (segmented button)")
                            return True
                        # FastGen sometimes keeps data-state="closed" even after successful click.
                        logger.info("[FastGen Keyframes] Keyframes button clicked (state did not update, proceeding)")
                        return True

            # Fallback for encoding/localization edge cases:
            # if we can detect segmented buttons with data-state, switch to a "closed" option.
            generic_segmented = page.locator(
                'button.flex-1.rounded-md.px-3.py-1\\.5.text-xs.font-medium.transition-colors[data-state]'
            )
            generic_count = await generic_segmented.count()
            if generic_count >= 2:
                for i in range(generic_count):
                    btn = generic_segmented.nth(i)
                    try:
                        data_state = await btn.get_attribute("data-state")
                        if data_state == "closed":
                            await btn.click(force=True, timeout=2000)
                            await asyncio.sleep(0.4)
                            new_state = await btn.get_attribute("data-state")
                            if new_state in {"open", "active", "checked"} or new_state != "closed":
                                logger.info("[FastGen Keyframes] Keyframes mode enabled (generic segmented fallback)")
                                return True
                            logger.info("[FastGen Keyframes] Generic segmented keyframes button clicked (state unchanged)")
                            return True
                    except Exception:
                        continue
            logger.debug("[FastGen Keyframes] Segmented keyframes button not found/activated")
        except Exception as e:
            logger.debug(f"[FastGen Keyframes] Segmented button detection failed: {e}")

        # Last resort: try clicking any switch-like element in the video settings area
        logger.warning("[FastGen Keyframes] Trying fallback approach for keyframes toggle")
        try:
            # Look for any element with "key" in text near a switch
            key_text = page.locator('text=/keyframe|key.*frame|кадр/i').first
            if await key_text.is_visible(timeout=2000):
                # Find nearby switch
                parent = key_text.locator('xpath=ancestor::div[1] | ancestor::label[1]')
                switch = parent.locator('button[role="switch"], input[type="checkbox"]').first
                if await switch.is_visible(timeout=1000):
                    await switch.click()
                    logger.info("[FastGen Keyframes] Keyframes mode enabled via text proximity")
                    return True
        except Exception as e:
            logger.debug(f"[FastGen Keyframes] Fallback toggle failed: {e}")
        
        logger.warning("[FastGen Keyframes] Keyframes toggle not found")
        return False
    except Exception as e:
        logger.warning(f"[FastGen Keyframes] Failed to toggle keyframes mode: {e}")
        return False


async def _upload_keyframe_start(page: Page, image_path: Path) -> bool:
    """
    Upload start frame for keyframe video generation.
    FastGen UI: First drop zone with class 'h-24' (smaller horizontal rectangle).
    """
    if not image_path or not image_path.exists():
        logger.warning("[FastGen Keyframes] Start frame image not found")
        return False
    
    resolved = str(image_path.resolve())
    
    # Wait for UI to render after toggling keyframes mode
    await asyncio.sleep(1.5)
    
    # Take a screenshot for debugging
    await _screenshot(page, "kf_before_start_upload")
    
    # Count file inputs on page for debugging
    try:
        all_file_inputs = await page.locator("input[type='file']").all()
        logger.info(f"[FastGen Keyframes] Found {len(all_file_inputs)} file inputs on page")
    except Exception:
        pass
    
    # Method 1: Look specifically for h-24 drop zone (start frame is smaller/horizontal)
    try:
        start_zone = page.locator("div.h-24[class*='border-dashed'], div.h-24.border-2").first
        if await start_zone.is_visible(timeout=2000):
            file_input = start_zone.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(resolved)
                logger.info("[FastGen Keyframes] Start frame uploaded to h-24 drop zone")
                await asyncio.sleep(1)
                await _screenshot(page, "kf_after_start_upload")
                return True
            else:
                # Try clicking the drop zone to trigger file chooser
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    await start_zone.click()
                fc = await fc_info.value
                await fc.set_files(resolved)
                logger.info("[FastGen Keyframes] Start frame uploaded via h-24 click")
                await asyncio.sleep(1)
                return True
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] h-24 drop zone search failed: {e}")
    
    # Method 2: Find all drop zones and use the first one
    try:
        drop_zones = page.locator("div[class*='border-dashed']")
        all_zones = await drop_zones.all()
        logger.info(f"[FastGen Keyframes] Found {len(all_zones)} drop zones with border-dashed")
        
        for i, dz in enumerate(all_zones[:3]):
            try:
                if await dz.is_visible(timeout=500):
                    # Check if this is NOT aspect-square (that's end frame)
                    classes = await dz.get_attribute("class") or ""
                    if "aspect-square" in classes:
                        continue  # Skip end frame zone
                    
                    file_input = dz.locator("input[type='file']")
                    if await file_input.count() > 0:
                        await file_input.first.set_input_files(resolved)
                        logger.info(f"[FastGen Keyframes] Start frame uploaded to drop zone #{i+1}")
                        await asyncio.sleep(1)
                        await _screenshot(page, "kf_after_start_upload")
                        return True
            except Exception as e:
                logger.debug(f"[FastGen Keyframes] Drop zone #{i+1} failed: {e}")
                continue
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] Drop zone search failed: {e}")
    
    # Fallback: Try first file input
    try:
        first_input = page.locator("input[type='file']").first
        await first_input.set_input_files(resolved)
        logger.info("[FastGen Keyframes] Start frame uploaded via first file input")
        await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] First file input failed: {e}")
    
    logger.warning("[FastGen Keyframes] Could not find start frame upload UI")
    return False


async def _upload_keyframe_end(page: Page, image_path: Path) -> bool:
    """
    Upload end frame for keyframe video generation.
    FastGen UI: SECOND drop zone with class 'w-full aspect-square' (square, right of start frame).
    """
    if not image_path or not image_path.exists():
        logger.warning("[FastGen Keyframes] End frame image not found")
        return False
    
    resolved = str(image_path.resolve())
    
    # Wait for UI to render
    await asyncio.sleep(1)
    
    # Take a screenshot for debugging
    await _screenshot(page, "kf_before_end_upload")
    
    # Count file inputs for debugging
    try:
        all_file_inputs = await page.locator("input[type='file']").all()
        logger.info(f"[FastGen Keyframes] End frame: Found {len(all_file_inputs)} file inputs")
    except Exception:
        pass
    
    # Method 1: Look specifically for aspect-square drop zone (end frame is square, right of start)
    try:
        end_zone = page.locator("div.aspect-square[class*='border-dashed'], div.aspect-square.border-2").first
        if await end_zone.is_visible(timeout=2000):
            file_input = end_zone.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(resolved)
                logger.info("[FastGen Keyframes] End frame uploaded to aspect-square drop zone")
                await asyncio.sleep(1)
                await _screenshot(page, "kf_after_end_upload")
                return True
            else:
                # Try clicking the drop zone to trigger file chooser
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    await end_zone.click()
                fc = await fc_info.value
                await fc.set_files(resolved)
                logger.info("[FastGen Keyframes] End frame uploaded via aspect-square click")
                await asyncio.sleep(1)
                return True
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] aspect-square drop zone search failed: {e}")
    
    # Method 2: Look for w-full aspect-square (full width square)
    try:
        end_zone = page.locator("div.w-full.aspect-square").first
        if await end_zone.is_visible(timeout=2000):
            file_input = end_zone.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(resolved)
                logger.info("[FastGen Keyframes] End frame uploaded to w-full.aspect-square drop zone")
                await asyncio.sleep(1)
                return True
            else:
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    await end_zone.click()
                fc = await fc_info.value
                await fc.set_files(resolved)
                logger.info("[FastGen Keyframes] End frame uploaded via w-full.aspect-square click")
                return True
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] w-full.aspect-square drop zone search failed: {e}")
    
    # Method 3: Find all drop zones, skip h-24 (start), use the one with aspect-square
    try:
        drop_zones = page.locator("div[class*='border-dashed']")
        all_zones = await drop_zones.all()
        logger.info(f"[FastGen Keyframes] End frame: Found {len(all_zones)} drop zones")
        
        for i, dz in enumerate(all_zones):
            try:
                if await dz.is_visible(timeout=500):
                    classes = await dz.get_attribute("class") or ""
                    logger.debug(f"[FastGen Keyframes] Drop zone #{i+1} classes: {classes[:80]}...")
                    
                    # Look for aspect-square (end frame)
                    if "aspect-square" in classes:
                        file_input = dz.locator("input[type='file']")
                        if await file_input.count() > 0:
                            await file_input.first.set_input_files(resolved)
                            logger.info(f"[FastGen Keyframes] End frame uploaded to aspect-square zone #{i+1}")
                            await asyncio.sleep(1)
                            await _screenshot(page, "kf_after_end_upload")
                            return True
            except Exception as e:
                logger.debug(f"[FastGen Keyframes] End drop zone #{i+1} failed: {e}")
                continue
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] End drop zone search failed: {e}")
    
    # Fallback: Try second file input
    try:
        all_inputs = await page.locator("input[type='file']").all()
        if len(all_inputs) >= 2:
            await all_inputs[1].set_input_files(resolved)
            logger.info("[FastGen Keyframes] End frame uploaded via 2nd file input")
            await asyncio.sleep(1)
            return True
        else:
            logger.warning(f"[FastGen Keyframes] Only {len(all_inputs)} file inputs found, need 2")
    except Exception as e:
        logger.debug(f"[FastGen Keyframes] Second file input failed: {e}")
    
    logger.warning("[FastGen Keyframes] Could not find end frame upload UI")
    return False


async def generate_video_from_keyframes(
    prompt: str,
    output_dir: Path,
    start_frame_path: Path,
    end_frame_path: Path,
    index: int = 0,
) -> Path | None:
    """
    Generate video via fast-gen.ai Video tab using keyframes (start + end frame).
    This enables image-to-video with transition from start to end frame.
    
    Args:
        prompt: Text prompt describing the video/transition
        output_dir: Directory to save the generated video
        start_frame_path: Path to the start frame image
        end_frame_path: Path to the end frame image
        index: Index for output filename
    
    Returns:
        Path to generated video or None on failure
    """
    return await asyncio.to_thread(
        _run_keyframe_video_sync,
        prompt, output_dir, start_frame_path, end_frame_path, index,
    )


def _run_keyframe_video_sync(
    prompt: str,
    output_dir: Path,
    start_frame_path: Path,
    end_frame_path: Path,
    index: int,
) -> Path | None:
    """Sync wrapper for keyframe video generation."""
    import asyncio as _asyncio
    
    async def _inner_attempt(scraper: FastGenScraper) -> Path | None:
        try:
            page = scraper._page
            assert page is not None
            
            logger.info(f"[FastGen Keyframes] Generating video from keyframes: {prompt[:60]}...")

            if not scraper._authenticated:
                await scraper._authenticate()
            
            await scraper._activate_video_tab()
            await scraper._select_video_settings()
            await _screenshot(page, "kf_01_video_tab")
            
            # Debug: log all visible buttons and switches
            try:
                all_buttons = await page.locator('button').all()
                logger.info(f"[FastGen Keyframes] Found {len(all_buttons)} buttons on page")
                all_switches = await page.locator('button[role="switch"]').all()
                logger.info(f"[FastGen Keyframes] Found {len(all_switches)} switch buttons")
                all_file_inputs = await page.locator('input[type="file"]').all()
                logger.info(f"[FastGen Keyframes] Found {len(all_file_inputs)} file inputs")
            except Exception as e:
                logger.debug(f"[FastGen Keyframes] Could not count elements: {e}")
            
            # Enable keyframes mode
            keyframes_enabled = await _toggle_keyframes_mode(page)
            if not keyframes_enabled:
                logger.error("[FastGen Keyframes] Could not enable keyframes mode")
                return None
            
            await _screenshot(page, "kf_02_keyframes_enabled")
            
            # Upload start frame
            start_uploaded = await _upload_keyframe_start(page, Path(start_frame_path))
            if not start_uploaded:
                logger.error("[FastGen Keyframes] Failed to upload start frame")
                return None
            
            await _screenshot(page, "kf_03_start_frame_uploaded")
            
            # Upload end frame
            end_uploaded = await _upload_keyframe_end(page, Path(end_frame_path))
            if not end_uploaded:
                logger.error("[FastGen Keyframes] Failed to upload end frame")
                return None
            
            await _screenshot(page, "kf_04_end_frame_uploaded")
            
            # Find and fill prompt
            if scraper._prompt_selector:
                sel = scraper._prompt_selector
            else:
                _, sel = await _find_first(page, _PROMPT_SELECTORS, timeout=10000)
                if not sel:
                    raise RuntimeError("Prompt input not found.")
                scraper._prompt_selector = sel
            
            # Log prompt length for debugging
            logger.info(f"[FastGen Keyframes] Prompt length: {len(prompt)} chars")
            if len(prompt) > 800:
                logger.warning(f"[FastGen Keyframes] Prompt is too long ({len(prompt)} chars), may cause issues!")
            
            await _react_fill(page, sel, prompt)
            await asyncio.sleep(0.5)
            await _screenshot(page, "kf_05_prompt_typed")
            
            # Find generate button
            gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
            if not gen_el:
                raise RuntimeError("Generate button not found.")
            
            timeout_s = max(300, settings.fastgen_image_timeout * 3)  # Longer for keyframes
            max_attempts = max(1, settings.fastgen_max_attempts)
            new_srcs: list[str] = []
            
            for attempt in range(max_attempts):
                videos_before = await _collect_video_srcs(page)
                
                # First attempt: click Generate to start
                # Subsequent attempts (after TimeoutError): click Generate for retry
                # Error-triggered retries: handled by _wait_for_new_video_with_regen
                if attempt == 0:
                    # Wait for button to be enabled
                    for _ in range(10):
                        disabled = await gen_el.get_attribute("disabled")
                        if disabled is None:
                            break
                        await asyncio.sleep(0.5)
                    
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    
                    await gen_el.click()
                    await asyncio.sleep(2)
                    await _screenshot(page, "kf_06_generating")
                    logger.info(f"[FastGen Keyframes] Attempt {attempt + 1}/{max_attempts} started")
                
                try:
                    new_srcs = await _wait_for_new_video_with_regen(
                        page, videos_before, timeout_s=timeout_s,
                        gen_button_el=gen_el, gen_button_sel=gen_sel
                    )
                except TimeoutError as e:
                    await _screenshot(page, f"kf_timeout{'_retry' + str(attempt) if attempt > 0 else ''}")
                    logger.warning(f"[FastGen Keyframes] Attempt {attempt + 1}/{max_attempts} timeout: {e}")
                    if attempt + 1 >= max_attempts:
                        logger.error(f"[FastGen Keyframes] All {max_attempts} attempts exhausted")
                        return None
                    # Timeout means: after last Generate click, no video appeared within timeout
                    # This is a genuine retry situation - click Generate for next attempt
                    logger.info(f"[FastGen Keyframes] Clicking Generate for retry {attempt + 2}...")
                    try:
                        gen_el, gen_sel = await _find_first(page, _GENERATE_SELECTORS, timeout=5000)
                        if gen_el:
                            disabled = await gen_el.get_attribute("disabled")
                            if disabled is None:
                                await gen_el.click()
                                logger.info("[FastGen Keyframes] Generate button clicked for retry")
                            else:
                                logger.warning("[FastGen Keyframes] Generate button is disabled")
                    except Exception as click_err:
                        logger.warning(f"[FastGen Keyframes] Could not click Generate: {click_err}")
                    await asyncio.sleep(3)
                    continue
                
                if new_srcs:
                    break
            
            if not new_srcs:
                return None
            
            logger.success("[FastGen Keyframes] Video generated")
            await _screenshot(page, "kf_07_result")
            
            # Download video
            output_dir.mkdir(parents=True, exist_ok=True)
            video_url = new_srcs[0]
            out_path = output_dir / f"clip_{index:03d}.mp4"
            
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
                logger.success(f"[FastGen Keyframes] Video saved: {out_path.name}")
                return out_path
            except Exception as e:
                logger.error(f"[FastGen Keyframes] Failed to download video: {e}")
                return None
                
        finally:
            pass # DO NOT STOP SCRAPER HERE! Keep it open for retry logic or cleanup!
            
    async def _inner() -> Path | None:
        scraper = FastGenScraper()
        await scraper.start()
        try:
            for attempt in range(3):
                try:
                    result = await _inner_attempt(scraper)
                    return result
                except asyncio.CancelledError:
                    # Properly handle cancellation - don't restart browser, just cleanup
                    logger.info("[FastGen Keyframes] Generation cancelled, cleaning up...")
                    raise
                except VideoGenerationError as e:
                    logger.warning(f"[FastGen Keyframes] Error caught, restarting browser context (attempt {attempt+1}/3): {e}")
                    await scraper.restart_browser()
                    continue
                except Exception as e:
                    logger.error(f"[FastGen Keyframes] Unknown error: {e}")
                    raise
            return None
        finally:
            await scraper.stop()
    
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


# ── Async entry point ──────────────────────────────────────────────────────────

async def generate_images_chain_fastgen(
    steps: list[tuple[str, int | None]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """Run img2img chain: steps = [(prompt, ref_step_index), ...]. ref_step_index=None = text2img."""
    try:
        return await asyncio.to_thread(
            _run_img2img_chain_sync, steps, output_dir, cancel_event
        )
    except FastGenCancelled:
        raise asyncio.CancelledError("FastGen cancelled") from None
    except asyncio.CancelledError:
        # Handle direct cancellation (not via FastGenCancelled)
        logger.info("[FastGen] Image chain generation cancelled")
        raise


async def generate_images_chain_from_seed_fastgen(
    seed_image: Path | str,
    steps: list[tuple[str, int]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """
    Img2img от готового файла: seed + steps [(prompt, ref_idx), ...].
    ref_idx=0 — первый шаг от seed; ref_idx=1 — от первого результата и т.д.
    """
    try:
        return await asyncio.to_thread(
            _run_img2img_chain_from_seed_sync,
            Path(seed_image),
            steps,
            output_dir,
            cancel_event,
        )
    except FastGenCancelled:
        raise asyncio.CancelledError("FastGen cancelled") from None
    except asyncio.CancelledError:
        logger.info("[FastGen] Image chain from seed cancelled")
        raise


async def generate_images_fastgen(
    prompts: list[str],
    output_dir: Path,
    parallel: bool = True,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """
    Generate images via fast-gen.ai.
    - parallel=True и len(prompts)>1: параллельная генерация (несколько браузеров).
    - parallel=False или 1 промпт: последовательная генерация (один браузер).

    Mode 3 (цепочка) вызывает с parallel=False. Mode 1 и др. — с parallel=True.
    """
    try:
        if parallel and len(prompts) > 1:
            logger.info("[FastGen] Starting parallel image generation ...")
            return await asyncio.to_thread(
                _run_fastgen_images_parallel_sync, prompts, output_dir, cancel_event
            )
        logger.info("[FastGen] Starting sequential image generation ...")
        return await asyncio.to_thread(_run_fastgen_sync, prompts, output_dir, cancel_event)
    except FastGenCancelled:
        raise asyncio.CancelledError("FastGen cancelled") from None
    except asyncio.CancelledError:
        logger.info("[FastGen] Image generation cancelled")
        raise


def _run_fastgen_with_refs_sync(
    prompts_with_refs: list[tuple[str, list[Path]]],
    output_dir: Path,
) -> list[Path]:
    """
    Synchronous wrapper for sequential image generation with multiple references.
    Each tuple: (prompt, list_of_reference_image_paths)

    Must be called via asyncio.to_thread() to avoid conflicts with uvicorn's loop.
    """
    import asyncio as _asyncio

    async def _inner() -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        scraper = FastGenScraper()
        await scraper.start()
        try:
            all_paths: list[Path] = []
            for i, (prompt, ref_paths) in enumerate(prompts_with_refs):
                for attempt in range(3):
                    try:
                        paths = await scraper.generate_with_multiple_references(
                            prompt=prompt,
                            output_dir=output_dir,
                            index=i,
                            reference_image_paths=ref_paths,
                        )
                        all_paths.extend(paths)
                        await _asyncio.sleep(1)
                        break
                    except VideoGenerationError as e:
                        logger.warning(f"[FastGen] Error caught during image generation (attempt {attempt+1}/3), restarting browser: {e}")
                        await scraper.restart_browser()
                        continue
            return all_paths
        finally:
            await scraper.stop()

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


async def generate_images_with_references_fastgen(
    prompts_with_refs: list[tuple[str, list[Path]]],
    output_dir: Path,
    parallel: bool = True,
    max_workers: int | None = None,
) -> list[Path]:
    """
    Generate images via fast-gen.ai with MULTIPLE reference images per prompt.

    Args:
        prompts_with_refs: List of tuples (prompt, list_of_reference_image_paths)
        output_dir: Directory to save generated images
        parallel: If True, generate images in parallel using multiple browsers
        max_workers: Maximum number of parallel workers (overrides settings)

    Returns:
        List of paths to generated images
    """
    if parallel and len(prompts_with_refs) > 1:
        logger.info(
            f"[FastGen] Starting PARALLEL image generation with references for {len(prompts_with_refs)} prompts..."
        )
        return await asyncio.to_thread(
            _run_fastgen_images_with_refs_parallel_sync, prompts_with_refs, output_dir, max_workers
        )
    logger.info(
        f"[FastGen] Starting SEQUENTIAL image generation with references for {len(prompts_with_refs)} prompts..."
    )
    return await asyncio.to_thread(_run_fastgen_with_refs_sync, prompts_with_refs, output_dir)
