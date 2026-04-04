"""Tests for src/analysis/market_indicators.py – Fear & Greed, correlations."""

from unittest.mock import patch
import pandas as pd
import numpy as np


class TestFearGreed:
    def test_returns_valid_structure(self, patch_historical_prices):
        from src.analysis.market_indicators import calculate_fear_greed

        result = calculate_fear_greed("US")
        assert "score" in result
        assert "label" in result
        assert "components" in result
        assert 0 <= result["score"] <= 100
        assert result["label"] in (
            "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
        )

    def test_label_mapping(self, patch_historical_prices):
        from src.analysis.market_indicators import calculate_fear_greed

        result = calculate_fear_greed("US")
        score = result["score"]
        label = result["label"]

        if score >= 75:
            assert label == "Extreme Greed"
        elif score >= 55:
            assert label == "Greed"
        elif score >= 45:
            assert label == "Neutral"
        elif score >= 25:
            assert label == "Fear"
        else:
            assert label == "Extreme Fear"

    def test_my_market(self, patch_historical_prices):
        from src.analysis.market_indicators import calculate_fear_greed

        result = calculate_fear_greed("MY")
        assert result["market"] == "MY"
        # MY has no VIX or bond proxy, so fewer components
        assert "volatility" not in result["components"]
        assert "safe_haven" not in result["components"]


class TestCorrelations:
    def test_basic_correlation(self):
        """Two correlated series should have high correlation."""
        np.random.seed(0)
        dates = pd.bdate_range(end="2024-06-01", periods=100)
        base_prices = 100 * np.cumprod(1 + np.random.normal(0, 0.01, len(dates)))

        def mock_prices(symbol, period="6mo"):
            np.random.seed(hash(symbol) % 2**31)
            noise = np.random.normal(0, 0.001, len(dates))
            df = pd.DataFrame({"Close": base_prices * (1 + noise)}, index=dates)
            df["RSI"] = 50.0
            df["Daily_Return"] = df["Close"].pct_change()
            return df

        with patch("src.analysis.market_indicators.get_historical_prices", side_effect=mock_prices):
            from src.analysis.market_indicators import calculate_correlations

            result = calculate_correlations(["A", "B"], period="6mo")
            assert "matrix" in result
            assert "notable_pairs" in result
            assert result["matrix"]["A"]["B"] > 0.9

    def test_insufficient_symbols(self):
        with patch("src.analysis.market_indicators.get_historical_prices", return_value=pd.DataFrame()):
            from src.analysis.market_indicators import calculate_correlations

            result = calculate_correlations(["A"], period="6mo")
            assert "error" in result
