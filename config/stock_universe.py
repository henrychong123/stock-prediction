"""
Stock Universe — defines the full set of stocks for data collection & training.

Tier 1: All Bursa Malaysia (80) + S&P 500 (503) + Major Indices (5) = ~590
Tier 2 (core): 80 Bursa + 10 US blue chips (for daily sentiment collection)

Usage:
    from config.stock_universe import get_all_stocks, get_core_stocks, get_sp500

    all_stocks = get_all_stocks()       # ~590 stocks for historical collection
    core = get_core_stocks()             # 90 stocks for daily sentiment
    sp500 = get_sp500()                  # 503 S&P 500 tickers
"""

import os
import csv
import io
import logging
from pathlib import Path
from datetime import datetime, timedelta

import requests

from config.settings import BURSA_INDUSTRIES

log = logging.getLogger(__name__)

# Cache S&P 500 list locally to avoid re-fetching every time
_SP500_CACHE_PATH = Path("data/sp500_tickers.csv")
_SP500_CACHE_MAX_AGE = timedelta(days=7)
_SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Major indices to track
INDICES = ["SPY", "QQQ", "DIA", "^GSPC", "^VIX", "^KLSE"]

# Core US stocks (for daily sentiment, always included)
CORE_US = ["TSLA", "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "META", "SPY", "QQQ", "DIA"]


def get_sp500() -> list[dict]:
    """Fetch S&P 500 constituents. Returns list of {symbol, name, sector}.
    Uses local cache (refreshed weekly)."""
    _SP500_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Check cache
    if _SP500_CACHE_PATH.exists():
        mtime = datetime.fromtimestamp(_SP500_CACHE_PATH.stat().st_mtime)
        if datetime.now() - mtime < _SP500_CACHE_MAX_AGE:
            return _read_sp500_cache()

    # Fetch fresh
    try:
        log.info("Fetching S&P 500 list from GitHub...")
        r = requests.get(_SP500_URL, timeout=15)
        r.raise_for_status()
        _SP500_CACHE_PATH.write_text(r.text, encoding="utf-8")
        return _read_sp500_cache()
    except Exception as e:
        log.warning(f"Failed to fetch S&P 500 list: {e}")
        # Try stale cache
        if _SP500_CACHE_PATH.exists():
            return _read_sp500_cache()
        return []


def _read_sp500_cache() -> list[dict]:
    text = _SP500_CACHE_PATH.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    result = []
    for row in reader:
        sym = row.get("Symbol", "").strip()
        if sym:
            result.append({
                "symbol": sym,
                "name": row.get("Name", sym),
                "sector": row.get("Sector", ""),
                "market": "US",
            })
    return result


def get_bursa_stocks() -> list[dict]:
    """Get all Bursa Malaysia stocks from BURSA_INDUSTRIES."""
    result = []
    for industry, data in BURSA_INDUSTRIES.items():
        for s in data["stocks"]:
            result.append({
                "symbol": s["symbol"],
                "name": s["name"],
                "sector": industry,
                "market": "MY",
            })
    return result


def get_all_stocks() -> list[dict]:
    """Get the full stock universe: S&P 500 + Bursa + Indices.
    Returns list of {symbol, name, sector, market}."""
    stocks = []
    seen = set()

    # Bursa stocks
    for s in get_bursa_stocks():
        if s["symbol"] not in seen:
            stocks.append(s)
            seen.add(s["symbol"])

    # S&P 500
    for s in get_sp500():
        if s["symbol"] not in seen:
            stocks.append(s)
            seen.add(s["symbol"])

    # Indices
    for idx in INDICES:
        if idx not in seen:
            stocks.append({
                "symbol": idx,
                "name": idx,
                "sector": "Index",
                "market": "US" if not idx.endswith("KLSE") else "MY",
            })
            seen.add(idx)

    return stocks


def get_core_stocks() -> list[dict]:
    """Get core stocks for daily sentiment collection (80 Bursa + 10 US)."""
    stocks = []
    seen = set()

    for s in get_bursa_stocks():
        if s["symbol"] not in seen:
            stocks.append(s)
            seen.add(s["symbol"])

    for sym in CORE_US:
        if sym not in seen:
            stocks.append({"symbol": sym, "name": sym, "sector": "", "market": "US"})
            seen.add(sym)

    return stocks


# Industry → GDELT keywords mapping — imported from canonical source
from config.industries import GDELT_KEYWORDS as INDUSTRY_GDELT_KEYWORDS  # noqa: F401


if __name__ == "__main__":
    all_stocks = get_all_stocks()
    bursa = [s for s in all_stocks if s["market"] == "MY"]
    us = [s for s in all_stocks if s["market"] == "US"]
    indices = [s for s in all_stocks if s["sector"] == "Index"]

    print(f"Stock Universe:")
    print(f"  Bursa Malaysia: {len(bursa)} stocks")
    print(f"  US (S&P 500):   {len(us)} stocks")
    print(f"  Indices:         {len(indices)}")
    print(f"  Total:           {len(all_stocks)} stocks")
    print(f"\nCore stocks (for sentiment): {len(get_core_stocks())}")
