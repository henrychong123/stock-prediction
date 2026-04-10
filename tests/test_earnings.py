"""Tests for src/data_sources/earnings.py — earnings signal and data fetching."""

from unittest.mock import patch, MagicMock
from src.database import save_earnings_batch, get_earnings_history, get_latest_earnings


class TestFetchCompanyEarnings:
    def test_no_api_key(self):
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", ""):
            from src.data_sources.earnings import fetch_company_earnings
            result = fetch_company_earnings("AAPL")
            assert len(result) == 1
            assert "error" in result[0]

    def test_with_data(self):
        mock_client = MagicMock()
        mock_client.company_earnings.return_value = [
            {"period": "2024-03-31", "actual": 1.53, "estimate": 1.50, "surprise": 0.03},
            {"period": "2023-12-31", "actual": 2.18, "estimate": 2.10, "surprise": 0.08},
        ]

        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("finnhub.Client", return_value=mock_client):
            from src.data_sources.earnings import fetch_company_earnings
            result = fetch_company_earnings("AAPL", limit=4)
            assert len(result) == 2
            assert result[0]["eps_actual"] == 1.53
            assert result[0]["eps_estimate"] == 1.50
            assert result[0]["surprise_pct"] == 2.0  # (1.53-1.50)/1.50*100

    def test_empty_response(self):
        mock_client = MagicMock()
        mock_client.company_earnings.return_value = []

        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("finnhub.Client", return_value=mock_client):
            from src.data_sources.earnings import fetch_company_earnings
            result = fetch_company_earnings("ZZZZ")
            assert result == []


class TestFetchEarningsCalendar:
    def test_no_api_key(self):
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", ""):
            from src.data_sources.earnings import fetch_earnings_calendar
            result = fetch_earnings_calendar("AAPL")
            assert "error" in result[0]

    def test_with_data(self):
        mock_client = MagicMock()
        mock_client.earnings_calendar.return_value = {
            "earningsCalendar": [
                {"symbol": "AAPL", "date": "2024-07-25", "epsEstimate": 1.35,
                 "hour": "amc", "quarter": 3, "year": 2024},
            ]
        }

        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("finnhub.Client", return_value=mock_client):
            from src.data_sources.earnings import fetch_earnings_calendar
            result = fetch_earnings_calendar("AAPL")
            assert len(result) == 1
            assert result[0]["symbol"] == "AAPL"
            assert result[0]["eps_estimate"] == 1.35


class TestGetEarningsSignal:
    def test_my_stock_neutral(self):
        from src.data_sources.earnings import get_earnings_signal
        result = get_earnings_signal("1155.KL")
        assert result["signal"] == "neutral"
        assert result["has_data"] is False

    def test_no_api_key(self):
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", ""):
            from src.data_sources.earnings import get_earnings_signal
            result = get_earnings_signal("AAPL")
            assert result["signal"] == "neutral"

    def test_bullish_signal(self):
        mock_history = [
            {"eps_actual": 2.0, "eps_estimate": 1.5, "surprise_pct": 33.3, "period": "Q1 2024"},
            {"eps_actual": 1.8, "eps_estimate": 1.6, "surprise_pct": 12.5, "period": "Q4 2023"},
            {"eps_actual": 1.7, "eps_estimate": 1.5, "surprise_pct": 13.3, "period": "Q3 2023"},
            {"eps_actual": 1.6, "eps_estimate": 1.4, "surprise_pct": 14.3, "period": "Q2 2023"},
        ]
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("src.data_sources.earnings.fetch_company_earnings", return_value=mock_history), \
             patch("src.data_sources.earnings.fetch_earnings_calendar", return_value=[]):
            from src.data_sources.earnings import get_earnings_signal
            result = get_earnings_signal("AAPL")
            assert result["signal"] == "bullish"
            assert result["strength"] > 0.5
            assert result["beat_rate"] == 1.0
            assert result["has_data"] is True

    def test_bearish_signal(self):
        mock_history = [
            {"eps_actual": 1.0, "eps_estimate": 1.5, "surprise_pct": -33.3, "period": "Q1 2024"},
            {"eps_actual": 1.1, "eps_estimate": 1.6, "surprise_pct": -31.3, "period": "Q4 2023"},
        ]
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("src.data_sources.earnings.fetch_company_earnings", return_value=mock_history), \
             patch("src.data_sources.earnings.fetch_earnings_calendar", return_value=[]):
            from src.data_sources.earnings import get_earnings_signal
            result = get_earnings_signal("AAPL")
            assert result["signal"] == "bearish"
            assert result["strength"] < 0.5

    def test_no_data(self):
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", "test_key"), \
             patch("src.data_sources.earnings.fetch_company_earnings", return_value=[]):
            from src.data_sources.earnings import get_earnings_signal
            result = get_earnings_signal("ZZZZ")
            assert result["signal"] == "neutral"
            assert result["has_data"] is False


class TestEarningsDB:
    def test_save_and_retrieve(self):
        batch = [
            {"symbol": "AAPL", "date": "2024-03-31", "period": "Q1 2024",
             "eps_actual": 1.53, "eps_estimate": 1.50, "surprise_pct": 2.0},
            {"symbol": "AAPL", "date": "2023-12-31", "period": "Q4 2023",
             "eps_actual": 2.18, "eps_estimate": 2.10, "surprise_pct": 3.8},
        ]
        save_earnings_batch(batch)
        history = get_earnings_history("AAPL")
        assert len(history) == 2
        assert history[0]["eps_actual"] == 1.53  # most recent first

    def test_get_latest(self):
        save_earnings_batch([
            {"symbol": "TSLA", "date": "2024-03-31", "eps_actual": 0.45, "eps_estimate": 0.50},
            {"symbol": "TSLA", "date": "2023-12-31", "eps_actual": 0.71, "eps_estimate": 0.65},
        ])
        latest = get_latest_earnings("TSLA")
        assert latest is not None
        assert latest["date"] == "2024-03-31"

    def test_get_latest_nonexistent(self):
        assert get_latest_earnings("ZZZZ") is None

    def test_upsert(self):
        save_earnings_batch([
            {"symbol": "AAPL", "date": "2024-03-31", "eps_actual": 1.50},
        ])
        save_earnings_batch([
            {"symbol": "AAPL", "date": "2024-03-31", "eps_actual": 1.53},
        ])
        history = get_earnings_history("AAPL")
        assert len(history) == 1
        assert history[0]["eps_actual"] == 1.53

    def test_empty(self):
        assert get_earnings_history("NONEXISTENT") == []
