"""Tests for src/analysis/portfolio.py – virtual portfolio tracking."""

from src.analysis.portfolio import (
    create_portfolio, get_portfolio, execute_trade,
    get_holdings, get_portfolio_summary, get_trade_history,
    _ensure_portfolio_tables,
)
from unittest.mock import patch


class TestPortfolioCRUD:
    def test_create_portfolio(self):
        _ensure_portfolio_tables()
        p = create_portfolio("test_port", 50000)
        assert p["name"] == "test_port"
        assert p["capital"] == 50000

    def test_get_or_create(self):
        _ensure_portfolio_tables()
        p1 = get_portfolio("auto_created")
        assert p1["name"] == "auto_created"

        p2 = get_portfolio("auto_created")
        assert p1["id"] == p2["id"]


class TestTrading:
    def test_buy_trade(self):
        _ensure_portfolio_tables()
        result = execute_trade("default", "AAPL", "BUY", 10, 150.0)
        assert result["success"] is True
        assert result["action"] == "BUY"

    def test_sell_trade(self):
        _ensure_portfolio_tables()
        execute_trade("default", "AAPL", "BUY", 10, 150.0)
        result = execute_trade("default", "AAPL", "SELL", 5, 160.0)
        assert result["success"] is True

    def test_sell_insufficient_holdings(self):
        _ensure_portfolio_tables()
        result = execute_trade("default", "TSLA", "SELL", 100, 200.0)
        assert "error" in result

    def test_avg_cost_calculation(self):
        _ensure_portfolio_tables()
        execute_trade("default", "AAPL", "BUY", 10, 100.0)
        execute_trade("default", "AAPL", "BUY", 10, 200.0)

        mock_quote = {"current_price": 150.0}
        with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=mock_quote):
            holdings = get_holdings("default")
            aapl = [h for h in holdings if h["symbol"] == "AAPL"][0]
            assert aapl["quantity"] == 20
            assert aapl["avg_cost"] == 150.0  # (10*100 + 10*200) / 20

    def test_sell_removes_holding_at_zero(self):
        _ensure_portfolio_tables()
        execute_trade("default", "MSFT", "BUY", 5, 400.0)
        execute_trade("default", "MSFT", "SELL", 5, 420.0)

        mock_quote = {"current_price": 420.0}
        with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=mock_quote):
            holdings = get_holdings("default")
            msft = [h for h in holdings if h["symbol"] == "MSFT"]
            assert len(msft) == 0


class TestPortfolioSummary:
    def test_summary_structure(self):
        _ensure_portfolio_tables()
        execute_trade("default", "AAPL", "BUY", 10, 150.0)

        mock_quote = {"current_price": 160.0}
        with patch("src.data_sources.stock_prices.get_realtime_quote", return_value=mock_quote):
            summary = get_portfolio_summary("default")
            assert "total_invested" in summary
            assert "current_value" in summary
            assert "total_pnl" in summary
            assert "holdings" in summary
            assert summary["holdings_count"] == 1
            assert summary["trade_count"] == 1

    def test_trade_history(self):
        _ensure_portfolio_tables()
        execute_trade("default", "AAPL", "BUY", 10, 150.0)
        execute_trade("default", "AAPL", "SELL", 5, 160.0)

        trades = get_trade_history("default")
        assert len(trades) == 2
