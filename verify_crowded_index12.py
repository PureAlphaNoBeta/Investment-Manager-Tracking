import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(8)  # Wait for initial data load

        # Look for the exact text we added
        await page.evaluate("""
            const elements = Array.from(document.querySelectorAll('*'));
            const match = elements.find(el => el.textContent && el.textContent.includes('Performance: We track how these 5 stocks perform as an equally-weighted portfolio over the next quarter'));
            if (match) {
                match.scrollIntoView();
            }
        """)
        await asyncio.sleep(2)

        await page.screenshot(path="/home/jules/verification/tab1_text.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
