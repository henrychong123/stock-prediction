"""Tests for insider trading data source and collector."""

import pytest
from unittest.mock import patch, MagicMock


class TestInsiderModule:
    """Tests for src/data_sources/insider.py"""

    @patch("src.data_sources.insider.FINNHUB_API_KEY", "test_key")
    @patch("src.data_sources.insider.finnhub.Client")
    def test_fetch_insider_transactions(self, mock_client_cls):
        from src.data_sources.insider import fetch_insider_transactions

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.stock_insider_transactions.return_value = {
            "data": [
                {
                    "filingDate": "2026-03-15",
                    "name": "John Doe",
                    "transactionCode": "P",
                    "share": 1000,
                    "change": 50000,
                    "transactionDate": "2026-03-14",
                    "transactionPrice": 150.0,
                },
                {
                    "filingDate": "2026-03-10",
                    "name": "Jane Smith",
                    "transactionCode": "S",
                    "share": 500,
                    "change": -25000,
                    "transactionDate": "2026-03-09",
                    "transactionPrice": 155.0,
                },
            ]
        }

        result = fetch_insider_transactions("AAPL", months_back=3)
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["transaction_type"] == "P"
        assert result[1]["transaction_type"] == "S"

    @patch("src.data_sources.insider.FINNHUB_API_KEY", "")
    def test_fetch_no_api_key(self):
        from src.data_sources.insider import fetch_insider_transactions
        assert fetch_insider_transactions("AAPL") == []

    @patch("src.data_sources.insider.FINNHUB_API_KEY", "test_key")
    @patch("src.data_sources.insider.finnhub.Client")
    def test_insider_signal_bullish(self, mock_client_cls):
        from src.data_sources.insider import get_insider_signal

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.stock_insider_transactions.return_value = {
            "data": [
                {"filingDate": "2026-03-15", "name": "A", "transactionCode": "P", "share": 1000, "change": 0, "transactionDate": "2026-03-15", "transactionPrice": 150},
                {"filingDate": "2026-03-14", "name": "B", "transactionCode": "P", "share": 2000, "change": 0, "transactionDate": "2026-03-14", "transactionPrice": 150},
                {"filingDate": "2026-03-13", "name": "C", "transactionCode": "S", "share": 500, "change": 0, "transactionDate": "2026-03-13", "transactionPrice": 150},
            ]
        }

        result = get_insider_signal("AAPL")
        assert result["has_data"] is True
        assert result["signal"] == "bullish"
        assert result["buy_ratio"] > 0.5

    def test_insider_signal_bursa(self):
        from src.data_sources.insider import get_insider_signal
        result = get_insider_signal("1155.KL")
        assert result["signal"] == "neutral"
        assert result["has_data"] is False


class TestInsiderDB:
    """Tests for insider DB operations."""

    def test_save_and_get_insider(self, tmp_database):
        from src.database import save_insider_batch, get_insider_history

        rows = [
            {"symbol": "AAPL", "filing_date": "2026-03-15", "insider_name": "Tim Cook",
             "transaction_type": "P-Purchase", "shares": 1000, "value": 50000, "shares_total": 10000},
            {"symbol": "AAPL", "filing_date": "2026-03-10", "insider_name": "CFO",
             "transaction_type": "S-Sale", "shares": 500, "value": 25000, "shares_total": 5000},
        ]
        save_insider_batch(rows)

        history = get_insider_history("AAPL")
        assert len(history) == 2
        assert history[0]["insider_name"] == "Tim Cook"
