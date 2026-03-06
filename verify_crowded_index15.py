import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Using an extremely tall viewport
        page = await browser.new_page(viewport={'width': 1200, 'height': 5000})
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(8)  # Wait for initial data load

        # Take a screenshot of the whole tall page
        await page.screenshot(path="/home/jules/verification/tab1_very_tall.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
