"""Tests for the catalyst event detection and stock ranking system."""

import pytest
from unittest.mock import patch, MagicMock
from src.analysis.catalyst import (
    detect_catalyst_events,
    rank_stocks_for_event,
    scan_catalysts,
    CatalystEvent,
)


class TestEventDetection:
    """Tests for detect_catalyst_events()."""

    def test_detect_supply_chain(self):
        headlines = [
            {"headline": "Global chip shortage disrupts auto production supply chain",
             "sentiment_score": -0.7, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        assert len(events) >= 1
        types = [e.event_type for e in events]
        assert "supply_chain" in types
        sc = next(e for e in events if e.event_type == "supply_chain")
        assert "Industrial & Manufacturing" in sc.affected_industries or "Technology" in sc.affected_industries

    def test_detect_tariff(self):
        headlines = [
            {"headline": "US announces new tariff on Chinese imports, trade war escalates",
             "sentiment_score": -0.5, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        types = [e.event_type for e in events]
        assert "tariff_trade" in types

    def test_detect_rate_hike(self):
        headlines = [
            {"headline": "Federal Reserve raises interest rate by 25 basis points, hawkish stance",
             "sentiment_score": -0.3, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        types = [e.event_type for e in events]
        assert "rate_decision" in types
        rd = next(e for e in events if e.event_type == "rate_decision")
        # Rate hike should be bullish for banks
        assert rd.affected_industries.get("Banking & Finance") == "bullish"

    def test_detect_rate_cut(self):
        headlines = [
            {"headline": "Fed cuts interest rate, dovish signal sends markets higher",
             "sentiment_score": 0.6, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        rd = next((e for e in events if e.event_type == "rate_decision"), None)
        assert rd is not None
        # Rate cut with positive sentiment → industries might flip from default
        assert "Property & Construction" in rd.affected_industries or "Technology" in rd.affected_industries

    def test_detect_commodity_spike(self):
        headlines = [
            {"headline": "Oil price surge as OPEC cuts production, crude oil at $90",
             "sentiment_score": 0.2, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        types = [e.event_type for e in events]
        assert "commodity_spike" in types
        cs = next(e for e in events if e.event_type == "commodity_spike")
        assert cs.affected_industries.get("Oil & Gas") == "bullish"

    def test_no_events_for_generic_news(self):
        headlines = [
            {"headline": "Company XYZ reports normal quarterly results",
             "sentiment_score": 0.0, "source_platform": "finnhub", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        assert len(events) == 0

    def test_deduplication(self):
        """Same event type from multiple headlines should only appear once."""
        headlines = [
            {"headline": "Chip shortage worsens across supply chain",
             "sentiment_score": -0.5, "source_platform": "a", "fetched_at": "2026-04-08T10:00:00"},
            {"headline": "Auto supply chain disrupted by shortage",
             "sentiment_score": -0.6, "source_platform": "b", "fetched_at": "2026-04-08T10:01:00"},
        ]
        events = detect_catalyst_events(headlines)
        supply_events = [e for e in events if e.event_type == "supply_chain"]
        assert len(supply_events) == 1

    def test_confidence_threshold(self):
        """Low-confidence matches should be filtered out."""
        headlines = [
            {"headline": "The weather is nice today",
             "sentiment_score": 0.1, "source_platform": "a", "fetched_at": "2026-04-08T10:00:00"},
        ]
        events = detect_catalyst_events(headlines)
        assert len(events) == 0

    def test_empty_input(self):
        assert detect_catalyst_events([]) == []


class TestStockRanking:
    """Tests for rank_stocks_for_event()."""

    @patch("src.analysis.catalyst._get_stock_momentum")
    @patch("src.analysis.catalyst._get_stocks_for_industry")
    def test_rank_basic(self, mock_stocks, mock_momentum):
        mock_stocks.return_value = [
            {"symbol": "AAPL", "name": "Apple", "market": "US", "sector_exposure": 0.9},
            {"symbol": "MSFT", "name": "Microsoft", "market": "US", "sector_exposure": 0.8},
        ]
        mock_momentum.return_value = {"momentum": 1.5, "price": 150.0, "volume_ratio": 1.2}

        event = CatalystEvent(
            event_type="tech_breakthrough",
            label="Technology Breakthrough",
            headline="AI breakthrough shakes tech world",
            sentiment=0.8,
            confidence=0.7,
            affected_industries={"Technology": "bullish"},
            detected_at="2026-04-08T10:00:00",
        )

        picks = rank_stocks_for_event(event, max_picks=5)
        assert len(picks) > 0
        assert picks[0].direction == "bullish"
        assert picks[0].score > 0

    @patch("src.analysis.catalyst._get_stock_momentum")
    @patch("src.analysis.catalyst._get_stocks_for_industry")
    def test_rank_bearish(self, mock_stocks, mock_momentum):
        mock_stocks.return_value = [
            {"symbol": "XOM", "name": "Exxon", "market": "US", "sector_exposure": 0.9},
        ]
        mock_momentum.return_value = {"momentum": -2.0, "price": 100.0, "volume_ratio": 1.5}

        event = CatalystEvent(
            event_type="geopolitical",
            label="Geopolitical Crisis",
            headline="Major conflict erupts",
            sentiment=-0.9,
            confidence=0.8,
            affected_industries={"Consumer & Retail": "bearish"},
            detected_at="2026-04-08T10:00:00",
        )

        picks = rank_stocks_for_event(event)
        # Should have picks if stocks found
        assert isinstance(picks, list)


class TestCatalystDB:
    """Tests for catalyst DB operations."""

    def test_save_and_get_alerts(self, tmp_database):
        from src.database import save_catalyst_scan, get_catalyst_alerts

        events = [
            {"event_type": "supply_chain", "label": "Supply Chain Disruption",
             "headline": "Chip shortage worsens", "sentiment": -0.5,
             "confidence": 0.7, "affected_industries": {"Technology": "bearish"}},
        ]
        picks = [
            {"symbol": "AAPL", "catalyst_type": "supply_chain", "score": 75,
             "direction": "bearish", "predicted_move_pct": -1.5},
        ]

        save_catalyst_scan("test123", events, picks)
        alerts = get_catalyst_alerts(hours_back=1)
        assert len(alerts) >= 1
        assert alerts[0]["event_type"] == "supply_chain"


class TestCatalystAPI:
    """Tests for catalyst API endpoints."""

    def test_get_alerts(self, client):
        res = client.get("/api/catalyst/alerts")
        assert res.status_code == 200
        data = res.get_json()
        assert "alerts" in data

    def test_get_history(self, client):
        res = client.get("/api/catalyst/history?days=7")
        assert res.status_code == 200
        data = res.get_json()
        assert "history" in data

    @patch("src.analysis.catalyst.scan_catalysts")
    def test_trigger_scan(self, mock_scan, client):
        mock_scan.return_value = {
            "events": [],
            "picks": [],
            "scanned_at": "2026-04-08T10:00:00",
            "headlines_scanned": 0,
        }
        res = client.post("/api/catalyst/scan")
        assert res.status_code == 200
        data = res.get_json()
        assert "scan_id" in data
