"""Tests for analyst consensus data source and collector."""

import pytest
from unittest.mock import patch, MagicMock


class TestAnalystModule:
    """Tests for src/data_sources/analyst.py"""

    @patch("src.data_sources.analyst.FINNHUB_API_KEY", "test_key")
    @patch("src.data_sources.analyst.finnhub.Client")
    def test_fetch_recommendation_trends(self, mock_client_cls):
        from src.data_sources.analyst import fetch_recommendation_trends

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recommendation_trends.return_value = [
            {"period": "2026-03-01", "strongBuy": 10, "buy": 15, "hold": 5, "sell": 2, "strongSell": 0},
            {"period": "2026-02-01", "strongBuy": 8, "buy": 14, "hold": 6, "sell": 3, "strongSell": 1},
        ]

        result = fetch_recommendation_trends("AAPL")
        assert len(result) == 2
        assert result[0]["strong_buy"] == 10
        assert result[0]["buy"] == 15

    @patch("src.data_sources.analyst.FINNHUB_API_KEY", "")
    def test_fetch_no_api_key(self):
        from src.data_sources.analyst import fetch_recommendation_trends
        assert fetch_recommendation_trends("AAPL") == []

    @patch("src.data_sources.analyst.FINNHUB_API_KEY", "test_key")
    @patch("src.data_sources.analyst.finnhub.Client")
    def test_analyst_signal_bullish(self, mock_client_cls):
        from src.data_sources.analyst import get_analyst_signal

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recommendation_trends.return_value = [
            {"period": "2026-03-01", "strongBuy": 15, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
        ]

        result = get_analyst_signal("AAPL")
        assert result["has_data"] is True
        assert result["signal"] == "bullish"
        assert result["analyst_score"] > 0

    @patch("src.data_sources.analyst.FINNHUB_API_KEY", "test_key")
    @patch("src.data_sources.analyst.finnhub.Client")
    def test_analyst_signal_bearish(self, mock_client_cls):
        from src.data_sources.analyst import get_analyst_signal

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.recommendation_trends.return_value = [
            {"period": "2026-03-01", "strongBuy": 0, "buy": 1, "hold": 3, "sell": 10, "strongSell": 8},
        ]

        result = get_analyst_signal("AAPL")
        assert result["has_data"] is True
        assert result["signal"] == "bearish"
        assert result["analyst_score"] < 0

    def test_analyst_signal_bursa(self):
        from src.data_sources.analyst import get_analyst_signal
        result = get_analyst_signal("1155.KL")
        assert result["signal"] == "neutral"
        assert result["has_data"] is False


class TestAnalystDB:
    """Tests for analyst DB operations."""

    def test_save_and_get_analyst(self, tmp_database):
        from src.database import save_analyst_batch, get_analyst_history

        rows = [
            {"symbol": "AAPL", "date": "2026-03-01", "strong_buy": 10, "buy": 15,
             "hold": 5, "sell": 2, "strong_sell": 0},
            {"symbol": "AAPL", "date": "2026-02-01", "strong_buy": 8, "buy": 14,
             "hold": 6, "sell": 3, "strong_sell": 1},
        ]
        save_analyst_batch(rows)

        history = get_analyst_history("AAPL")
        assert len(history) == 2
        assert history[0]["strong_buy"] == 10
