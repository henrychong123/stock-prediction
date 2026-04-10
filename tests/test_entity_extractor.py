"""Tests for stock entity extraction from headlines."""

import pytest
from src.analysis.entity_extractor import extract_stocks


class TestEntityExtraction:
    """Tests for extract_stocks()."""

    def test_alias_match_apple(self):
        matches = extract_stocks("Apple beats Q4 earnings expectations with record iPhone sales")
        symbols = [m["symbol"] for m in matches]
        assert "AAPL" in symbols
        assert any(m["match_type"] == "alias" for m in matches if m["symbol"] == "AAPL")

    def test_alias_match_tesla(self):
        matches = extract_stocks("Tesla recalls 500,000 vehicles over safety concerns")
        symbols = [m["symbol"] for m in matches]
        assert "TSLA" in symbols

    def test_alias_match_elon_musk(self):
        matches = extract_stocks("Elon Musk sells $5 billion worth of shares")
        symbols = [m["symbol"] for m in matches]
        assert "TSLA" in symbols

    def test_alias_match_maybank(self):
        matches = extract_stocks("Maybank reports 15% increase in net profit for Q3")
        symbols = [m["symbol"] for m in matches]
        assert "1155.KL" in symbols

    def test_alias_match_petronas(self):
        matches = extract_stocks("Petronas Chemicals declares special dividend")
        symbols = [m["symbol"] for m in matches]
        assert "5183.KL" in symbols

    def test_ticker_match(self):
        matches = extract_stocks("NVDA stock surges 10% on AI demand outlook")
        symbols = [m["symbol"] for m in matches]
        assert "NVDA" in symbols

    def test_name_match_from_csv(self):
        matches = extract_stocks("Abbott Laboratories wins FDA approval for new device")
        symbols = [m["symbol"] for m in matches]
        assert "ABT" in symbols

    def test_no_false_positive_common_words(self):
        """Common words like 'AI', 'IT', 'US' should not match tickers."""
        matches = extract_stocks("US GDP growth beats expectations as AI spending rises")
        symbols = [m["symbol"] for m in matches]
        assert "A" not in symbols  # Agilent Technologies
        assert "IT" not in symbols

    def test_empty_headline(self):
        assert extract_stocks("") == []
        assert extract_stocks(None) == []

    def test_no_match(self):
        matches = extract_stocks("The weather is sunny today in Kuala Lumpur")
        assert len(matches) == 0

    def test_multiple_stocks(self):
        matches = extract_stocks("Apple and Microsoft compete for AI dominance")
        symbols = [m["symbol"] for m in matches]
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_confidence_ordering(self):
        """Alias matches should have higher confidence than ticker matches."""
        matches = extract_stocks("Tesla TSLA stock surges on Cybertruck deliveries")
        # Should only return TSLA once (deduped), alias match preferred
        tsla_matches = [m for m in matches if m["symbol"] == "TSLA"]
        assert len(tsla_matches) == 1
        assert tsla_matches[0]["confidence"] >= 0.9  # alias confidence

    def test_bursa_numeric_ticker_not_matched(self):
        """Numeric Bursa tickers like 1155 shouldn't match random numbers in text."""
        matches = extract_stocks("Stock market gains 1155 points in historic rally")
        # 1155.KL should NOT match because the headline says "1155 points"
        symbols = [m["symbol"] for m in matches]
        assert "1155.KL" not in symbols


class TestDirectMentionIntegration:
    """Tests for detect_direct_stock_mentions in catalyst.py."""

    def test_direct_mention_detects_stock(self):
        from src.analysis.catalyst import detect_direct_stock_mentions

        headlines = [
            {"headline": "Apple beats earnings by 20%, stock surges after hours",
             "sentiment_score": 0.8, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        picks = detect_direct_stock_mentions(headlines)
        assert len(picks) >= 1
        aapl = next((p for p in picks if p.symbol == "AAPL"), None)
        assert aapl is not None
        assert aapl.score > 30  # should have a meaningful score
        assert aapl.direction in ("bullish", "bearish")  # ML model may override

    def test_direct_mention_negative_sentiment(self):
        from src.analysis.catalyst import detect_direct_stock_mentions

        headlines = [
            {"headline": "Tesla faces massive recall, Elon Musk under investigation",
             "sentiment_score": -0.7, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        picks = detect_direct_stock_mentions(headlines)
        assert len(picks) >= 1
        tsla = next((p for p in picks if p.symbol == "TSLA"), None)
        assert tsla is not None
        assert tsla.score > 30

    def test_neutral_headlines_skipped(self):
        from src.analysis.catalyst import detect_direct_stock_mentions

        headlines = [
            {"headline": "Apple schedules event for next week",
             "sentiment_score": 0.05, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        picks = detect_direct_stock_mentions(headlines)
        # Neutral sentiment (< 0.1) should be skipped
        assert len(picks) == 0
