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


class TestPredictAPI:
    def test_predict_live(self, client, patch_yfinance, patch_realtime_quote):
        """Live prediction when no cache exists."""
        import src.analysis.predictor as pred
        pred._ml_models = False
        pred._optimized_weights_cache = None

        resp = client.get("/api/predict/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "action" in data
        assert data["symbol"] == "AAPL"
        assert "signals" in data
        assert "confidence" in data

    def test_predict_full_mode(self, client, patch_yfinance, patch_realtime_quote):
        import src.analysis.predictor as pred
        pred._ml_models = False
        pred._optimized_weights_cache = None

        # Mock the slow sources for full mode
        neutral = {"signal": "neutral", "strength": 0.5, "reasons": []}
        with patch("src.data_sources.news_sentiment.get_news_signal", return_value=neutral), \
             patch("src.data_sources.social_media.get_social_signal", return_value=neutral), \
             patch("src.data_sources.geopolitical.get_geopolitical_signal", return_value=neutral), \
             patch("src.data_sources.news_sentiment.fetch_influential_figure_news", return_value=[]):
            resp = client.get("/api/predict/AAPL?mode=full")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["cached"] is False


class TestPredictionsLatestAPI:
    def test_empty(self, client):
        resp = client.get("/api/predictions/latest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["predictions"] == {}

    def test_with_data(self, client):
        from src.database import save_prediction
        save_prediction("AAPL", "BUY", 0.8, 150.0, 0.4, {}, [])
        resp = client.get("/api/predictions/latest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "AAPL" in data["predictions"]


class TestSignalAPIs:
    def test_news_signal(self, client, patch_news_signal):
        resp = client.get("/api/signal/news/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "signal" in data

    def test_social_signal(self, client, patch_social_signal):
        resp = client.get("/api/signal/social/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "signal" in data

    def test_geopolitical_signal(self, client, patch_geopolitical_signal):
        resp = client.get("/api/signal/geopolitical")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "signal" in data

    def test_earnings_signal(self, client):
        with patch("src.data_sources.earnings.FINNHUB_API_KEY", ""):
            resp = client.get("/api/signal/earnings/AAPL")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "signal" in data

    def test_earnings_signal_my_stock(self, client):
        resp = client.get("/api/signal/earnings/1155.KL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["signal"]["signal"] == "neutral"


class TestWeightsAPI:
    def test_returns_weights(self, client):
        import src.analysis.predictor as pred
        pred._optimized_weights_cache = None

        resp = client.get("/api/weights")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "US" in data
        assert "MY" in data
        assert "weights" in data["US"]
        assert "source" in data["US"]


class TestWatchlistAPI:
    def test_empty_watchlist(self, client):
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["watchlist"] == []

    def test_add_to_watchlist(self, client):
        resp = client.post("/api/watchlist",
                           data=json.dumps({"symbol": "AAPL", "name": "Apple"}),
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["symbol"] == "AAPL"

    def test_add_requires_symbol(self, client):
        resp = client.post("/api/watchlist",
                           data=json.dumps({"name": "Apple"}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_remove_from_watchlist(self, client):
        from src.database import add_to_watchlist
        add_to_watchlist("TSLA")
        resp = client.delete("/api/watchlist/TSLA")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["removed"] is True

    def test_update_watchlist(self, client):
        from src.database import add_to_watchlist
        add_to_watchlist("AAPL")
        resp = client.put("/api/watchlist/AAPL",
                          data=json.dumps({"note": "Great stock", "alert_above": 200}),
                          content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["updated"] is True


class TestOrderBookAPI:
    def test_order_book(self, client, patch_order_book):
        resp = client.get("/api/orderbook/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "bids" in data
        assert "asks" in data

    def test_ib_status(self, client):
        import src.data_sources.order_book as ob
        ob._ib = None
        ob._ib_available = False
        resp = client.get("/api/ib/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "connected" in data
        ob._ib_available = None


class TestPredictionTrendAPI:
    def test_empty(self, client):
        resp = client.get("/api/predictions/trend/AAPL")
        assert resp.status_code == 200

    def test_with_data(self, client):
        from src.database import save_prediction
        save_prediction("AAPL", "BUY", 0.8, 150.0, 0.4, {}, [])
        resp = client.get("/api/predictions/trend/AAPL")
        assert resp.status_code == 200


class TestFearGreedAPI:
    def test_returns_result(self, client, patch_historical_prices):
        resp = client.get("/api/fear-greed")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "score" in data or "error" in data


class TestResolveSymbolAPI:
    def test_klse_passthrough(self, client):
        resp = client.get("/api/resolve-symbol?q=1155.KL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["resolved"] == "1155.KL"

    def test_empty_query(self, client):
        resp = client.get("/api/resolve-symbol?q=")
        assert resp.status_code == 400

    def test_us_stock(self, client):
        resp = client.get("/api/resolve-symbol?q=AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["resolved"] == "AAPL"


class TestBursaAccuracyAPI:
    def test_empty(self, client):
        resp = client.get("/api/bursa/accuracy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data

    def test_with_limit(self, client):
        resp = client.get("/api/bursa/accuracy?limit=10")
        assert resp.status_code == 200


class TestBursaHistoryAPI:
    def test_empty(self, client):
        resp = client.get("/api/bursa/history/1155")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["history"] == []
        assert data["symbol"] == "1155.KL"


class TestNewsStatusAPI:
    def test_returns_status(self, client):
        resp = client.get("/api/news/status")
        assert resp.status_code == 200


class TestStockPage:
    def test_stock_page(self, client):
        resp = client.get("/stock/AAPL")
        assert resp.status_code == 200
