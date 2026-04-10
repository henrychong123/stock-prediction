"""Tests for src/analysis/predictor.py – signal combination, prediction, weights."""

import pytest
from unittest.mock import patch, MagicMock
from src.analysis.predictor import combine_signals, PredictionResult, get_active_weights, predict


class TestCombineSignals:
    """Test the weighted signal combination logic.

    Note: combine_signals now returns (action, confidence, weight_source).
    """

    def test_all_bullish(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 0.9},
            "news_sentiment": {"signal": "bullish", "strength": 0.8},
            "social_sentiment": {"signal": "bullish", "strength": 0.85},
            "geopolitical": {"signal": "bullish", "strength": 0.7},
            "market_momentum": {"signal": "bullish", "strength": 0.75},
        }
        action, confidence, source = combine_signals(signals)
        assert action in ("BUY", "STRONG BUY")
        assert confidence > 0.3
        assert source in ("default", "ai_optimized", "custom")

    def test_all_bearish(self):
        signals = {
            "technical": {"signal": "bearish", "strength": 0.1},
            "news_sentiment": {"signal": "bearish", "strength": 0.15},
            "social_sentiment": {"signal": "bearish", "strength": 0.1},
            "geopolitical": {"signal": "bearish", "strength": 0.2},
            "market_momentum": {"signal": "bearish", "strength": 0.15},
        }
        action, confidence, source = combine_signals(signals)
        assert action in ("SELL", "STRONG SELL")
        assert confidence > 0.3

    def test_neutral_signals(self):
        signals = {
            "technical": {"signal": "neutral", "strength": 0.5},
            "news_sentiment": {"signal": "neutral", "strength": 0.5},
            "social_sentiment": {"signal": "neutral", "strength": 0.5},
            "geopolitical": {"signal": "neutral", "strength": 0.5},
            "market_momentum": {"signal": "neutral", "strength": 0.5},
        }
        action, confidence, _ = combine_signals(signals)
        assert action == "HOLD"
        assert confidence == 0.0

    def test_custom_weights(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 0.9},
            "news_sentiment": {"signal": "bearish", "strength": 0.1},
        }
        weights = {"technical": 0.9, "news_sentiment": 0.1}
        action, _, source = combine_signals(signals, weights)
        assert action in ("BUY", "STRONG BUY")
        assert source == "custom"

    def test_empty_signals(self):
        action, confidence, _ = combine_signals({})
        assert action == "HOLD"
        assert confidence == 0.0

    def test_unknown_signal_name_ignored(self):
        signals = {
            "unknown_signal": {"signal": "bullish", "strength": 0.9},
        }
        action, confidence, _ = combine_signals(signals)
        assert action == "HOLD"

    def test_confidence_capped_at_one(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 1.0},
            "news_sentiment": {"signal": "bullish", "strength": 1.0},
            "social_sentiment": {"signal": "bullish", "strength": 1.0},
            "geopolitical": {"signal": "bullish", "strength": 1.0},
            "market_momentum": {"signal": "bullish", "strength": 1.0},
        }
        _, confidence, _ = combine_signals(signals)
        assert confidence <= 1.0

    def test_my_market_weights(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 0.8},
        }
        action, confidence, source = combine_signals(signals, market="MY")
        assert source in ("default", "ai_optimized")


class TestGetActiveWeights:
    def test_default_us_weights(self):
        import src.analysis.predictor as pred
        pred._optimized_weights_cache = None
        weights, source = get_active_weights("US")
        assert isinstance(weights, dict)
        assert "technical" in weights
        assert source in ("default", "ai_optimized")

    def test_default_my_weights(self):
        import src.analysis.predictor as pred
        pred._optimized_weights_cache = None
        weights, source = get_active_weights("MY")
        assert isinstance(weights, dict)

    def test_optimized_weights_loaded(self):
        """When optimized weights file exists and is fresh, use them."""
        import src.analysis.predictor as pred
        from datetime import datetime
        pred._optimized_weights_cache = None

        mock_data = {
            "optimized_at": datetime.now().isoformat(),
            "US": {"weights": {"technical": 0.5, "news_sentiment": 0.3}},
            "MY": {"weights": {"technical": 0.6}},
        }
        pred._optimized_weights_cache = mock_data
        weights, source = get_active_weights("US")
        assert source == "ai_optimized"
        assert weights["technical"] == 0.5
        # Cleanup
        pred._optimized_weights_cache = None


class TestPredict:
    def test_fast_mode(self, patch_yfinance, patch_realtime_quote):
        """Fast mode uses only technical + ML."""
        import src.analysis.predictor as pred
        pred._ml_models = False  # no ML models available
        pred._optimized_weights_cache = None

        result = predict("AAPL", fast=True)
        assert isinstance(result, PredictionResult)
        assert result.symbol == "AAPL"
        assert result.action in ("STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL")
        assert 0 <= result.confidence <= 1
        assert "technical" in result.signals

    def test_result_has_weight_source(self, patch_yfinance, patch_realtime_quote):
        import src.analysis.predictor as pred
        pred._ml_models = False
        pred._optimized_weights_cache = None

        result = predict("AAPL", fast=True)
        assert result.weight_source in ("default", "ai_optimized")
        assert isinstance(result.weights_used, dict)

    def test_my_market_detection(self, patch_yfinance, patch_realtime_quote):
        import src.analysis.predictor as pred
        pred._ml_models = False
        pred._optimized_weights_cache = None

        result = predict("1155.KL", fast=True)
        assert result.symbol == "1155.KL"


class TestPredictionResult:
    def test_summary_format(self):
        result = PredictionResult(
            symbol="AAPL",
            action="BUY",
            confidence=0.75,
            price_current=180.0,
            signals={"technical": {"signal": "bullish", "strength": 0.8}},
            reasons=["MACD crossover", "RSI oversold"],
        )
        summary = result.summary()
        assert "AAPL" in summary
        assert "BUY" in summary
        assert "75.0%" in summary
        assert "$180.00" in summary
        assert "MACD crossover" in summary
