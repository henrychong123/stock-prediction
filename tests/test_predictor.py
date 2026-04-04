"""Tests for src/analysis/predictor.py – signal combination and PredictionResult."""

import pytest
from src.analysis.predictor import combine_signals, PredictionResult


class TestCombineSignals:
    """Test the weighted signal combination logic."""

    def test_all_bullish(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 0.9},
            "news_sentiment": {"signal": "bullish", "strength": 0.8},
            "social_sentiment": {"signal": "bullish", "strength": 0.85},
            "geopolitical": {"signal": "bullish", "strength": 0.7},
            "market_momentum": {"signal": "bullish", "strength": 0.75},
        }
        action, confidence = combine_signals(signals)
        assert action in ("BUY", "STRONG BUY")
        assert confidence > 0.3

    def test_all_bearish(self):
        signals = {
            "technical": {"signal": "bearish", "strength": 0.1},
            "news_sentiment": {"signal": "bearish", "strength": 0.15},
            "social_sentiment": {"signal": "bearish", "strength": 0.1},
            "geopolitical": {"signal": "bearish", "strength": 0.2},
            "market_momentum": {"signal": "bearish", "strength": 0.15},
        }
        action, confidence = combine_signals(signals)
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
        action, confidence = combine_signals(signals)
        assert action == "HOLD"
        assert confidence == 0.0

    def test_custom_weights(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 0.9},
            "news_sentiment": {"signal": "bearish", "strength": 0.1},
        }
        # Heavy technical weight should yield bullish
        weights = {"technical": 0.9, "news_sentiment": 0.1}
        action, _ = combine_signals(signals, weights)
        assert action in ("BUY", "STRONG BUY")

    def test_empty_signals(self):
        action, confidence = combine_signals({})
        assert action == "HOLD"
        assert confidence == 0.0

    def test_unknown_signal_name_ignored(self):
        signals = {
            "unknown_signal": {"signal": "bullish", "strength": 0.9},
        }
        action, confidence = combine_signals(signals)
        assert action == "HOLD"  # weight=0, so ignored

    def test_confidence_capped_at_one(self):
        signals = {
            "technical": {"signal": "bullish", "strength": 1.0},
            "news_sentiment": {"signal": "bullish", "strength": 1.0},
            "social_sentiment": {"signal": "bullish", "strength": 1.0},
            "geopolitical": {"signal": "bullish", "strength": 1.0},
            "market_momentum": {"signal": "bullish", "strength": 1.0},
        }
        _, confidence = combine_signals(signals)
        assert confidence <= 1.0


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
