"""
Article Text Scraper — scrapes full article content for news headlines
that only have titles. Uses Playwright + trafilatura.

Fills the `summary` field in the news table with full article text.

Usage:
    python src/data/scrape_articles.py              # scrape 50 recent articles
    python src/data/scrape_articles.py --limit 200  # scrape 200 articles
    python src/data/scrape_articles.py --all         # scrape all without text
"""

import sys
import os
import logging
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, get_news_without_article_text, update_news_article_text
from src.data_sources.article_scraper import scrape_article, close_browser

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run(limit: int = 50):
    init_db()

    articles = get_news_without_article_text(limit=limit)
    if not articles:
        log.info("No articles need scraping")
        return

    log.info(f"Scraping full text for {len(articles)} articles...")

    scraped = 0
    failed = 0

    for i, article in enumerate(articles, 1):
        url = article["url"]
        if not url or len(url) < 10:
            continue

        result = scrape_article(url)

        if result["success"] and result["chars"] > 50:
            update_news_article_text(article["id"], result["text"])
            scraped += 1
        else:
            failed += 1

        if i % 10 == 0:
            log.info(f"  {i}/{len(articles)} — {scraped} scraped, {failed} failed")

        time.sleep(1)  # be gentle

    close_browser()
    log.info(f"\nDone — {scraped}/{len(articles)} articles scraped ({failed} failed)")


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = 50

    if "--all" in args:
        limit = 10000
    else:
        for i, a in enumerate(args):
            if a == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])

    run(limit=limit)
