#!/usr/bin/env python3
"""
Stock Prediction System - Multi-Signal Analysis

Combines technical analysis, news sentiment (FinBERT), social media (Reddit),
geopolitical events (GDELT), and influential figure monitoring to generate
stock predictions.

Usage:
    python main.py                    # Predict all default symbols
    python main.py TSLA AAPL NVDA     # Predict specific stocks
    python main.py --news             # Show latest market news
    python main.py --geopolitical     # Show geopolitical events
    python main.py --trending         # Show trending tickers on Reddit
"""

import sys
import argparse
from datetime import datetime


def print_header():
    print()
    print("=" * 60)
    print("  STOCK PREDICTION SYSTEM")
    print("  Multi-Signal Analysis Engine")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    print("  Data Sources:")
    print("    • Yahoo Finance  — Historical prices & technicals")
    print("    • Finnhub        — Real-time quotes & news")
    print("    • FinBERT        — AI sentiment analysis")
    print("    • GDELT          — Geopolitical event tracking")
    print("    • Reddit         — Social media sentiment")
    print()


def cmd_predict(symbols: list[str]):
    """Run predictions for given symbols."""
    from src.analysis.predictor import predict

    for symbol in symbols:
        print(f"\n{'─'*60}")
        print(f"  Analyzing {symbol}...")
        print(f"{'─'*60}")

        try:
            result = predict(symbol)
            print()
            print(result.summary())
        except Exception as e:
            print(f"  Error analyzing {symbol}: {e}")

    print()
    print("  DISCLAIMER: This is for educational purposes only.")
    print("  Do NOT make investment decisions based solely on this tool.")
    print()


def cmd_news():
    """Show latest market news with sentiment."""
    from src.data_sources.news_sentiment import fetch_market_news

    print("  Fetching latest market news...\n")
    articles = fetch_market_news()

    if not articles or "error" in articles[0]:
        print(f"  {articles[0].get('error', 'No news available')}")
        return

    for i, article in enumerate(articles[:15], 1):
        sentiment = article["sentiment"]
        icon = "🟢" if sentiment["label"] == "positive" else "🔴" if sentiment["label"] == "negative" else "⚪"
        print(f"  {i:2d}. {icon} [{article['source']}] {article['headline']}")
        print(f"      Sentiment: {sentiment['label']} ({sentiment['score']:+.3f})")
        print(f"      {article['datetime']}")
        print()


def cmd_geopolitical():
    """Show geopolitical events and their market impact."""
    from src.data_sources.geopolitical import fetch_geopolitical_events, get_geopolitical_signal

    print("  Fetching geopolitical events...\n")

    signal = get_geopolitical_signal()
    print(f"  Overall Signal: {signal['signal'].upper()}")
    print(f"  Average Tone:   {signal.get('avg_tone', 'N/A')}")
    print(f"  Events Found:   {signal['event_count']}")
    print()

    if signal.get("keyword_breakdown"):
        print("  Events by Category:")
        for kw, count in signal["keyword_breakdown"].items():
            print(f"    • {kw}: {count} events")
        print()

    print("  Key Events:")
    for reason in signal.get("reasons", []):
        print(f"    • {reason}")
    print()


def cmd_trending():
    """Show trending stock tickers on Reddit."""
    from src.data_sources.social_media import fetch_trending_tickers

    print("  Scanning Reddit for trending tickers...\n")
    trending = fetch_trending_tickers()

    if isinstance(trending, dict) and "error" in trending:
        print(f"  {trending['error']}")
        return

    print(f"  {'Rank':<6} {'Ticker':<10} {'Mentions':<10}")
    print(f"  {'─'*30}")
    for i, (ticker, count) in enumerate(trending.items(), 1):
        print(f"  {i:<6} ${ticker:<9} {count}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Stock Prediction System - Multi-Signal Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    Predict all default symbols
  python main.py TSLA AAPL          Predict specific stocks
  python main.py --news             Show latest market news
  python main.py --geopolitical     Show geopolitical events
  python main.py --trending         Show trending Reddit tickers
        """,
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        help="Stock symbols to analyze (e.g., TSLA AAPL NVDA)",
    )
    parser.add_argument(
        "--news",
        action="store_true",
        help="Show latest market news with sentiment analysis",
    )
    parser.add_argument(
        "--geopolitical", "--geo",
        action="store_true",
        help="Show geopolitical events and market impact",
    )
    parser.add_argument(
        "--trending",
        action="store_true",
        help="Show trending stock tickers on Reddit",
    )

    args = parser.parse_args()
    print_header()

    if args.news:
        cmd_news()
    elif args.geopolitical:
        cmd_geopolitical()
    elif args.trending:
        cmd_trending()
    else:
        from config.settings import DEFAULT_SYMBOLS
        symbols = args.symbols if args.symbols else DEFAULT_SYMBOLS
        cmd_predict(symbols)


if __name__ == "__main__":
    main()
