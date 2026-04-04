"""Tests for web/app.py – Flask API endpoint smoke tests.

All external calls are mocked so tests run offline and fast.
"""

import json
from unittest.mock import patch, MagicMock
from tests.conftest import _make_price_df


class TestBasicRoutes:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Stock Prediction" in resp.data

    def test_pro_dashboard(self, client):
        resp = client.get("/pro")
        assert resp.status_code == 200
        assert b"PRO" in resp.data


class TestQuoteAPI:
    def test_single_quote(self, client, patch_realtime_quote):
        resp = client.get("/api/quote/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current_price"] == 150.25

    def test_batch_quotes(self, client, patch_realtime_quote):
        resp = client.get("/api/quotes?symbols=AAPL,TSLA")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "quotes" in data
        assert len(data["quotes"]) == 2

    def test_batch_quotes_empty(self, client, patch_realtime_quote):
        resp = client.get("/api/quotes?symbols=")
        assert resp.status_code == 400


class TestHistoryAPI:
    def test_history_success(self, client, patch_yfinance):
        resp = client.get("/api/history/AAPL?period=6mo")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dates" in data
        assert "close" in data
        assert "rsi" in data
        assert len(data["dates"]) > 0

    def test_history_empty(self, client, patch_yfinance):
        import yfinance
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = __import__("pandas").DataFrame()
        yfinance.Ticker.return_value = mock_ticker

        resp = client.get("/api/history/INVALID")
        assert resp.status_code == 404


class TestMarketsAPI:
    def test_markets_endpoint(self, client):
        resp = client.get("/api/markets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "US" in data["markets"]
        assert "MY" in data["markets"]
        assert "my_stock_names" in data


class TestPredictionHistoryAPI:
    def test_prediction_history_empty(self, client):
        resp = client.get("/api/predictions/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["predictions"] == []

    def test_prediction_symbols_empty(self, client):
        resp = client.get("/api/predictions/symbols")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbols"] == []


class TestAlertsAPI:
    def test_list_alerts_empty(self, client):
        from src.analysis.alerts import _ensure_alerts_table
        _ensure_alerts_table()

        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["alerts"] == []

    def test_create_alert(self, client):
        from src.analysis.alerts import _ensure_alerts_table
        _ensure_alerts_table()

        resp = client.post("/api/alerts/create",
                           data=json.dumps({
                               "symbol": "AAPL",
                               "alert_type": "price",
                               "condition": "above",
                               "threshold": 200,
                           }),
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbol"] == "AAPL"

    def test_delete_alert(self, client):
        from src.analysis.alerts import _ensure_alerts_table, create_alert
        _ensure_alerts_table()
        alert = create_alert("TSLA", "price", "below", 100)

        resp = client.delete(f"/api/alerts/{alert['id']}")
        assert resp.status_code == 200


class TestPortfolioAPI:
    def test_portfolio_summary(self, client, patch_realtime_quote):
        from src.analysis.portfolio import _ensure_portfolio_tables
        _ensure_portfolio_tables()

        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200

    def test_execute_trade(self, client):
        from src.analysis.portfolio import _ensure_portfolio_tables
        _ensure_portfolio_tables()

        resp = client.post("/api/portfolio/trade",
                           data=json.dumps({
                               "symbol": "AAPL",
                               "action": "BUY",
                               "quantity": 10,
                               "price": 150,
                           }),
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_trade_no_body(self, client):
        resp = client.post("/api/portfolio/trade",
                           content_type="application/json")
        assert resp.status_code == 400


class TestSectorHistoryAPI:
    def test_sector_history_empty(self, client):
        resp = client.get("/api/sectors/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["history"] == []
