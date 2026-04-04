"""Tests for src/data_sources/stock_prices.py – technical indicators & signals."""

from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


class TestGetHistoricalPrices:
    def test_returns_dataframe_with_indicators(self, patch_yfinance):
        from src.data_sources.stock_prices import get_historical_prices

        df = get_historical_prices("AAPL", period="6mo")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col in df.columns

        for col in ["SMA_20", "SMA_50", "MACD", "Signal_Line", "RSI",
                     "BB_Upper", "BB_Lower", "Daily_Return", "Volatility"]:
            assert col in df.columns

    def test_empty_ticker_returns_empty(self, patch_yfinance):
        """Override the default mock to return empty."""
        import yfinance
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        yfinance.Ticker.return_value = mock_ticker

        from src.data_sources.stock_prices import get_historical_prices
        df = get_historical_prices("INVALID")
        assert df.empty

    def test_rsi_bounded(self, mock_price_df):
        """RSI should always be between 0 and 100."""
        rsi = mock_price_df["RSI"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()


class TestGetTechnicalSignal:
    def test_returns_valid_signal(self, patch_yfinance):
        from src.data_sources.stock_prices import get_technical_signal

        result = get_technical_signal("AAPL")
        assert result["signal"] in ("bullish", "bearish", "neutral")
        assert 0 <= result["strength"] <= 1
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) > 0

    def test_insufficient_data(self, patch_yfinance):
        """Short history should return neutral."""
        import yfinance
        short_df = pd.DataFrame({
            "Close": [100, 101, 102],
            "Open": [99, 100, 101],
            "High": [101, 102, 103],
            "Low": [98, 99, 100],
            "Volume": [1e6, 1e6, 1e6],
        })
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = short_df
        yfinance.Ticker.return_value = mock_ticker

        from src.data_sources.stock_prices import get_technical_signal
        result = get_technical_signal("AAPL")
        assert result["signal"] == "neutral"
        assert "Insufficient data" in result["reasons"]


class TestFallbackQuote:
    def test_fallback_returns_quote(self, patch_yfinance):
        """When FINNHUB_API_KEY is empty, fallback to yfinance."""
        import yfinance
        dates = pd.bdate_range(end="2024-01-15", periods=2)
        history = pd.DataFrame({
            "Open": [148.0, 150.0],
            "High": [152.0, 153.0],
            "Low": [147.0, 149.0],
            "Close": [150.0, 152.0],
            "Volume": [1e7, 1.2e7],
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = history
        mock_ticker.fast_info = MagicMock()
        yfinance.Ticker.return_value = mock_ticker

        with patch("src.data_sources.stock_prices.FINNHUB_API_KEY", ""):
            from src.data_sources.stock_prices import get_realtime_quote
            q = get_realtime_quote("AAPL")
            assert q["symbol"] == "AAPL"
            assert q["current_price"] == 152.0
            assert q["previous_close"] == 150.0
            assert q["change"] == 2.0
