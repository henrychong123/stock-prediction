"""Tests for config/stock_universe.py – stock universe management."""

from unittest.mock import patch, MagicMock
from config.stock_universe import (
    get_bursa_stocks, get_all_stocks, get_core_stocks, INDICES, CORE_US,
)


class TestGetBursaStocks:
    def test_returns_list(self):
        stocks = get_bursa_stocks()
        assert isinstance(stocks, list)
        assert len(stocks) > 0

    def test_structure(self):
        stocks = get_bursa_stocks()
        for s in stocks:
            assert "symbol" in s
            assert "name" in s
            assert "sector" in s
            assert "market" in s
            assert s["market"] == "MY"

    def test_symbols_end_with_kl(self):
        stocks = get_bursa_stocks()
        for s in stocks:
            assert s["symbol"].endswith(".KL"), f"{s['symbol']} doesn't end with .KL"


class TestGetAllStocks:
    def test_includes_bursa(self):
        with patch("config.stock_universe.get_sp500", return_value=[]):
            stocks = get_all_stocks()
            bursa = [s for s in stocks if s["market"] == "MY"]
            assert len(bursa) > 0

    def test_includes_indices(self):
        with patch("config.stock_universe.get_sp500", return_value=[]):
            stocks = get_all_stocks()
            symbols = {s["symbol"] for s in stocks}
            for idx in INDICES:
                assert idx in symbols, f"Missing index: {idx}"

    def test_no_duplicates(self):
        with patch("config.stock_universe.get_sp500", return_value=[]):
            stocks = get_all_stocks()
            symbols = [s["symbol"] for s in stocks]
            assert len(symbols) == len(set(symbols))


class TestGetCoreStocks:
    def test_includes_bursa(self):
        stocks = get_core_stocks()
        bursa = [s for s in stocks if s["market"] == "MY"]
        assert len(bursa) > 0

    def test_includes_core_us(self):
        stocks = get_core_stocks()
        symbols = {s["symbol"] for s in stocks}
        for us in CORE_US:
            assert us in symbols, f"Missing core US stock: {us}"

    def test_no_duplicates(self):
        stocks = get_core_stocks()
        symbols = [s["symbol"] for s in stocks]
        assert len(symbols) == len(set(symbols))


class TestConstants:
    def test_indices(self):
        assert "SPY" in INDICES
        assert "^KLSE" in INDICES

    def test_core_us(self):
        assert "AAPL" in CORE_US
        assert "TSLA" in CORE_US
