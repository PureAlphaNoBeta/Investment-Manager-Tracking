import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Wait a bit longer to ensure Streamlit is fully loaded
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(5)  # Wait for initial data load

        # Try scrolling the main container where content lives
        await page.evaluate("""
            const container = document.querySelector('.main .block-container') || document.documentElement;
            container.scrollTop = container.scrollHeight;
        """)
        await asyncio.sleep(2)  # Wait for rendering after scroll

        # Scroll a bit more or focus on the exact text if possible
        await page.screenshot(path="/home/jules/verification/tab1_bottom6.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
