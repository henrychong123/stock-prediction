"""
Full Article Scraper — uses Playwright (headless browser) + trafilatura
to extract complete article text from any news URL.

Handles: Google News redirects, Cloudflare protection, JavaScript-rendered pages.

Usage:
    from src.data_sources.article_scraper import scrape_article, scrape_articles_batch

    text = scrape_article("https://news.google.com/rss/articles/...")
    results = scrape_articles_batch([url1, url2, url3])
"""

import logging
import trafilatura

log = logging.getLogger(__name__)

_BROWSER = None
_PLAYWRIGHT = None


def _get_browser():
    """Lazy-launch Playwright headless Chromium. Reuses across calls."""
    global _BROWSER, _PLAYWRIGHT
    if _BROWSER is not None:
        return _BROWSER

    try:
        from playwright.sync_api import sync_playwright
        _PLAYWRIGHT = sync_playwright().start()
        _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True)
        log.info("Playwright browser launched")
        return _BROWSER
    except Exception as e:
        log.warning(f"Playwright not available: {e}")
        return None


def scrape_article(url: str, timeout_ms: int = 15000) -> dict:
    """Scrape full article text from a URL.

    Handles Google News redirects, Cloudflare, JS-rendered pages.

    Returns:
        {url, final_url, text, chars, title, success}
    """
    browser = _get_browser()
    if not browser:
        # Fallback: try trafilatura directly (works for simple sites)
        return _fallback_scrape(url)

    try:
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # let JS render

        final_url = page.url
        title = page.title()
        html = page.content()
        page.close()

        # Extract article text
        text = trafilatura.extract(html) or ""

        return {
            "url": url,
            "final_url": final_url,
            "text": text,
            "chars": len(text),
            "title": title,
            "success": len(text) > 50,
        }
    except Exception as e:
        try:
            page.close()
        except Exception:
            pass
        log.debug(f"Playwright failed for {url}: {e}")
        return _fallback_scrape(url)


def _fallback_scrape(url: str) -> dict:
    """Fallback: use trafilatura directly (no browser, faster but limited)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) if downloaded else ""
        return {
            "url": url,
            "final_url": url,
            "text": text or "",
            "chars": len(text) if text else 0,
            "title": "",
            "success": bool(text and len(text) > 50),
        }
    except Exception:
        return {"url": url, "final_url": url, "text": "", "chars": 0, "title": "", "success": False}


def scrape_articles_batch(urls: list[str], timeout_ms: int = 15000) -> list[dict]:
    """Scrape multiple articles. Reuses browser instance for speed."""
    results = []
    for url in urls:
        result = scrape_article(url, timeout_ms=timeout_ms)
        results.append(result)
    return results


def close_browser():
    """Clean up browser resources."""
    global _BROWSER, _PLAYWRIGHT
    try:
        if _BROWSER:
            _BROWSER.close()
            _BROWSER = None
        if _PLAYWRIGHT:
            _PLAYWRIGHT.stop()
            _PLAYWRIGHT = None
    except Exception:
        pass
