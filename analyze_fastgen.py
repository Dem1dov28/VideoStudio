"""Analyze fast-gen.ai page structure for model selection."""
import asyncio
from playwright.async_api import async_playwright

async def analyze_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print('Navigating to fast-gen.ai...')
        await page.goto('https://fast-gen.ai/generator', wait_until='networkidle')
        await asyncio.sleep(3)
        
        # Analyze combobox structure
        print('\n=== COMBOBOX ANALYSIS ===')
        combobox = page.locator('button[role="combobox"]').first
        if await combobox.count() > 0:
            print('Found combobox button')
            print(f'Visible: {await combobox.is_visible()}')
            print(f'Enabled: {await combobox.is_enabled()}')
            outer_html = await combobox.evaluate('el => el.outerHTML')
            print(f'Outer HTML (first 500 chars): {outer_html[:500]}')
        
        # Analyze select element
        print('\n=== SELECT ELEMENT ANALYSIS ===')
        select_el = page.locator('select').first
        if await select_el.count() > 0:
            print('Found select element')
            print(f'Visible: {await select_el.is_visible()}')
            outer_html = await select_el.evaluate('el => el.outerHTML')
            print(f'Outer HTML: {outer_html[:500]}')
            
            # Get options
            options = await select_el.locator('option').all()
            print(f'\nOptions ({len(options)} total):')
            for opt in options:
                val = await opt.get_attribute('value')
                text = await opt.text_content()
                print(f'  value="{val}" text="{text}"')
        
        # Click combobox and analyze again
        print('\n=== AFTER CLICKING COMBOBOX ===')
        await combobox.click()
        await asyncio.sleep(1)
        
        # Check for dropdown
        dropdown = page.locator('[role="listbox"], [data-radix-popper-content-wrapper], .radix-select-content')
        print(f'Dropdown visible elements: {await dropdown.count()}')
        
        # Check select again
        print(f'Select visible after click: {await select_el.is_visible()}')
        
        # Try to find visible options
        visible_options = page.locator('[role="option"]')
        print(f'Visible options count: {await visible_options.count()}')
        
        if await visible_options.count() > 0:
            for i, opt in enumerate(await visible_options.all()[:5]):
                text = await opt.text_content()
                print(f'  Option {i}: {text}')
        
        await asyncio.sleep(5)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(analyze_page())
