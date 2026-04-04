"""Tests for src/analysis/alerts.py – alert CRUD and trigger checking."""

from src.analysis.alerts import (
    create_alert, get_alerts, check_alerts, delete_alert, reset_alert,
    _ensure_alerts_table,
)
from unittest.mock import patch


class TestAlertCRUD:
    def test_create_and_list(self):
        _ensure_alerts_table()
        alert = create_alert("AAPL", "price", "above", 200.0, "Target hit")

        assert alert["symbol"] == "AAPL"
        assert alert["threshold"] == 200.0

        alerts = get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "price"

    def test_delete_alert(self):
        _ensure_alerts_table()
        alert = create_alert("TSLA", "rsi", "below", 30.0)
        delete_alert(alert["id"])

        alerts = get_alerts()
        assert len(alerts) == 0

    def test_reset_triggered(self):
        _ensure_alerts_table()
        alert = create_alert("MSFT", "price", "above", 500.0)

        from src.analysis.alerts import _mark_triggered
        _mark_triggered(alert["id"])

        alerts = get_alerts(active_only=False)
        triggered = [a for a in alerts if a["is_triggered"]]
        assert len(triggered) == 1

        reset_alert(triggered[0]["id"])
        alerts_after = get_alerts(active_only=False)
        assert alerts_after[0]["is_triggered"] == 0

    def test_multiple_alerts(self):
        _ensure_alerts_table()
        create_alert("AAPL", "price", "above", 200.0)
        create_alert("AAPL", "rsi", "below", 30.0)
        create_alert("TSLA", "price", "below", 100.0)

        alerts = get_alerts()
        assert len(alerts) == 3


class TestAlertChecking:
    def test_price_alert_triggers(self):
        _ensure_alerts_table()
        create_alert("AAPL", "price", "above", 100.0, "Moon!")

        mock_quote = {"current_price": 150.0}
        # check_alerts() imports get_realtime_quote from src.data_sources.stock_prices
        with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=mock_quote):
            triggered = check_alerts()
            assert len(triggered) == 1
            assert triggered[0]["symbol"] == "AAPL"
            assert triggered[0]["current_value"] == 150.0

    def test_price_alert_not_triggered(self):
        _ensure_alerts_table()
        create_alert("AAPL", "price", "above", 200.0)

        mock_quote = {"current_price": 150.0}
        with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=mock_quote):
            triggered = check_alerts()
            assert len(triggered) == 0

    def test_rsi_alert_triggers(self, mock_price_df):
        _ensure_alerts_table()
        create_alert("SPY", "rsi", "below", 99.0)

        with patch("src.data_sources.stock_prices.get_historical_prices", return_value=mock_price_df):
            triggered = check_alerts()
            assert len(triggered) == 1
