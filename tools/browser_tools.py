
import logging, os
log = logging.getLogger("ch8.browser")

def browser_navigate(url: str) -> dict:
    """Navega para uma URL e retorna o texto da página."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until='domcontentloaded')
            title = page.title()
            text = page.inner_text('body')[:5000]
            browser.close()
            return {"ok": True, "url": url, "title": title, "text": text}
    except ImportError:
        return {"ok": False, "error": "playwright not installed. Run: pip install playwright && playwright install chromium --no-sandbox"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def browser_snapshot(url: str = None) -> dict:
    """Tira screenshot da página atual ou de uma URL."""
    try:
        from playwright.sync_api import sync_playwright
        import base64
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            if url:
                page.goto(url, timeout=30000)
            screenshot = page.screenshot(type='png')
            browser.close()
            return {"ok": True, "screenshot_b64": base64.b64encode(screenshot).decode()}
    except ImportError:
        return {"ok": False, "error": "playwright not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def browser_extract(url: str) -> dict:
    """Extrai links e texto de uma URL usando Playwright."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.goto(url, timeout=30000)
            links = page.eval_on_selector_all('a[href]', 'els => els.map(e => ({text:e.textContent.trim(), href:e.href}))')
            text = page.inner_text('body')[:3000]
            browser.close()
            return {"ok": True, "url": url, "text": text, "links": links[:20]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
