"""Tests for src/data_sources/order_book.py – order book and IB status."""

from unittest.mock import patch, MagicMock


class TestIBStatus:
    def test_ib_not_available(self):
        import src.data_sources.order_book as ob
        ob._ib = None
        ob._ib_available = False

        result = ob.ib_status()
        assert result["connected"] is False
        assert "yfinance" in result["source"]

        # Cleanup
        ob._ib_available = None


class TestGetOrderBook:
    def test_yfinance_fallback(self):
        """When IB is not available, falls back to yfinance Level 1."""
        import src.data_sources.order_book as ob
        ob._ib = None
        ob._ib_available = False

        mock_info = {
            "bid": 150.0,
            "ask": 150.5,
            "bidSize": 10,
            "askSize": 8,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = ob.get_order_book("AAPL")
            assert result["level"] == 1
            assert result["best_bid"] == 150.0
            assert result["best_ask"] == 150.5
            assert result["spread"] == 0.5
            assert result["pressure"] is not None
            assert "yfinance" in result["source"]

        ob._ib_available = None

    def test_yfinance_no_data(self):
        """When yfinance has no bid/ask data."""
        import src.data_sources.order_book as ob
        ob._ib = None
        ob._ib_available = False

        mock_ticker = MagicMock()
        mock_ticker.info = {"bid": None, "ask": None}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = ob.get_order_book("ZZZZ")
            assert "error" in result

        ob._ib_available = None

    def test_spread_calculation(self):
        import src.data_sources.order_book as ob
        ob._ib = None
        ob._ib_available = False

        mock_ticker = MagicMock()
        mock_ticker.info = {"bid": 100.0, "ask": 100.5, "bidSize": 5, "askSize": 5}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = ob.get_order_book("TEST")
            assert result["spread"] == 0.5
            assert result["spread_pct"] == 0.5  # 0.5/100.0 * 100
            assert result["pressure"] == 50.0  # equal bid/ask vol

        ob._ib_available = None
