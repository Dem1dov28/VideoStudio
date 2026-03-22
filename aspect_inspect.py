import asyncio, json
from playwright.async_api import async_playwright

FASTGEN_API_KEY = "SfWZC5Lgh8g5fqdYFdyjIVdZQZwU5Abp"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://fast-gen.ai/generator", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Auth
        inp = page.locator("input[type='password']").first
        await inp.fill(FASTGEN_API_KEY)
        await page.locator("button:has-text('Проверить')").first.click()
        await asyncio.sleep(4)

        # Dump all buttons and selects to find aspect ratio controls
        buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, [role=button], select, input[type=radio]'))
                .map(el => ({
                    tag: el.tagName,
                    text: el.innerText?.trim().slice(0, 60),
                    value: el.value,
                    ariaLabel: el.getAttribute('aria-label'),
                    title: el.getAttribute('title'),
                    dataValue: el.getAttribute('data-value'),
                    cls: el.className?.slice(0, 80)
                }))
                .filter(el => el.text || el.ariaLabel || el.title || el.value)
        }""")
        for b in buttons:
            print(json.dumps(b, ensure_ascii=False))

        await page.screenshot(path="output/debug_screenshots/aspect_inspect.png", full_page=True)
        print("Screenshot saved")
        await browser.close()

asyncio.run(main())