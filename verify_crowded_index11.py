import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(8)  # Wait for initial data load

        # Look for the text we added to scroll it into view
        element = page.locator("text=Performance: The index is formed as an equally-weighted portfolio")
        await element.scroll_into_view_if_needed()
        await asyncio.sleep(2)

        await page.screenshot(path="/home/jules/verification/tab1_text.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
