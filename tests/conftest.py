"""
Shared test fixtures for the stock prediction test suite.

Provides mock data, temporary databases, and patched external APIs
so tests run fast and offline (no network calls).
"""

import os
import sys
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Mock unavailable third-party modules before any src imports ─────
# yfinance and finnhub may not be installed in CI; stub them out.

for mod_name in ("yfinance", "finnhub", "praw", "feedparser", "gdeltdoc",
                  "ib_insync", "transformers", "xgboost", "lightgbm", "joblib"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


# ── Temporary database ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_database(tmp_path, monkeypatch):
    """Redirect all DB operations to a temporary SQLite file."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("src.database.DB_PATH", db_path)

    # Re-initialise tables in the temp DB
    from src.database import init_db
    init_db()

    return db_path


# ── Mock stock price data ───────────────────────────────────────────

def _make_price_df(days: int = 120, start_price: float = 100.0) -> pd.DataFrame:
    """Generate a realistic-looking price DataFrame with technical indicators."""
    np.random.seed(42)
    dates = pd.bdate_range(end=datetime.now(), periods=days)
    n = len(dates)
    returns = np.random.normal(0.0005, 0.015, n)
    prices = start_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "Open": prices * (1 - np.random.uniform(0, 0.01, n)),
        "High": prices * (1 + np.random.uniform(0, 0.02, n)),
        "Low": prices * (1 - np.random.uniform(0, 0.02, n)),
        "Close": prices,
        "Volume": np.random.randint(1_000_000, 50_000_000, n),
    }, index=dates)

    # Technical indicators (mirrors stock_prices.py logic)
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["EMA_12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA_26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df["BB_Middle"] = df["Close"].rolling(20).mean()
    bb_std = df["Close"].rolling(20).std()
    df["BB_Upper"] = df["BB_Middle"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Middle"] - (bb_std * 2)

    df["Daily_Return"] = df["Close"].pct_change()
    df["Volatility"] = df["Daily_Return"].rolling(20).std()

    return df


@pytest.fixture
def mock_price_df():
    """Return a pre-built price DataFrame for tests that need raw data."""
    return _make_price_df()


@pytest.fixture
def patch_yfinance():
    """Patch yfinance.Ticker so no network calls are made."""
    df = _make_price_df()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    mock_ticker.fast_info = MagicMock()

    with patch("yfinance.Ticker", return_value=mock_ticker) as m:
        yield m


@pytest.fixture
def patch_historical_prices():
    """Patch get_historical_prices directly (most common mock)."""
    df = _make_price_df()
    with patch("src.data_sources.stock_prices.get_historical_prices", return_value=df) as m:
        yield m


@pytest.fixture
def patch_realtime_quote():
    """Patch get_realtime_quote to return synthetic data."""
    quote = {
        "symbol": "TEST",
        "current_price": 150.25,
        "change": 2.10,
        "percent_change": 1.42,
        "high": 152.00,
        "low": 147.50,
        "open": 148.00,
        "previous_close": 148.15,
        "timestamp": datetime.now().isoformat(),
    }
    with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=quote) as m:
        yield m


# ── Flask test client ───────────────────────────────────────────────

@pytest.fixture
def patch_news_signal():
    """Patch get_news_signal to return synthetic data."""
    signal = {
        "signal": "bullish",
        "strength": 0.7,
        "avg_sentiment": 0.4,
        "article_count": 5,
        "reasons": ["Apple beats earnings expectations"],
    }
    with patch("src.data_sources.news_sentiment.get_news_signal", return_value=signal) as m:
        yield m


@pytest.fixture
def patch_social_signal():
    """Patch get_social_signal to return synthetic data."""
    signal = {
        "signal": "bullish",
        "strength": 0.65,
        "avg_sentiment": 0.3,
        "post_count": 12,
        "figure_mentions": [],
        "reasons": ["[r/wallstreetbets] AAPL mooning (↑42)"],
    }
    with patch("src.data_sources.social_media.get_social_signal", return_value=signal) as m:
        yield m


@pytest.fixture
def patch_geopolitical_signal():
    """Patch get_geopolitical_signal to return synthetic data."""
    signal = {
        "signal": "neutral",
        "strength": 0.5,
        "avg_tone": 0.1,
        "event_count": 10,
        "reasons": ["No major geopolitical events"],
        "source": "stored",
    }
    with patch("src.data_sources.geopolitical.get_geopolitical_signal", return_value=signal) as m:
        yield m


@pytest.fixture
def patch_order_book():
    """Patch get_order_book to return synthetic L1 data."""
    book = {
        "source": "yfinance (Level 1)",
        "level": 1,
        "symbol": "AAPL",
        "bids": [{"price": 150.0, "size": 1000}],
        "asks": [{"price": 150.5, "size": 800}],
        "best_bid": 150.0,
        "best_ask": 150.5,
        "spread": 0.5,
        "spread_pct": 0.333,
        "total_bid_vol": 1000,
        "total_ask_vol": 800,
        "pressure": 55.6,
    }
    with patch("src.data_sources.order_book.get_order_book", return_value=book) as m:
        yield m


@pytest.fixture
def client():
    """Create a Flask test client."""
    from web.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
