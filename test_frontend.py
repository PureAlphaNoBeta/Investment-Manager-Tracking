from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Using a much taller viewport to capture the whole page
        context = browser.new_context(viewport={'width': 1280, 'height': 4000})
        page = context.new_page()
        page.goto("http://localhost:8501")
        # Wait until the 'Universe Snapshot' text appears, ensuring the page fully rendered
        page.get_by_text("Universe Snapshot").wait_for(state="visible", timeout=60000)
        page.wait_for_timeout(5000) # give it extra time to paint

        # Take full page screenshot
        page.screenshot(path="frontend_test11.png", full_page=True)
        browser.close()

if __name__ == "__main__":
    run()
