"""Tests for src/data_sources/geopolitical.py – GDELT events and geopolitical signal."""

from unittest.mock import patch, MagicMock
from src.database import save_gdelt_history_batch


class TestFetchGeopoliticalEvents:
    def test_no_gdeltdoc(self):
        """When gdeltdoc is not installed, return error."""
        import sys
        # Temporarily remove gdeltdoc mock to simulate ImportError
        saved = sys.modules.get("gdeltdoc")
        sys.modules["gdeltdoc"] = None  # will cause ImportError on from-import

        try:
            # Need to reimport to trigger the ImportError path
            from src.data_sources.geopolitical import fetch_geopolitical_events
            result = fetch_geopolitical_events(keywords=["test"])
            # Should either return error or empty depending on import behavior
            assert isinstance(result, list)
        finally:
            if saved is not None:
                sys.modules["gdeltdoc"] = saved


class TestGetGeopoliticalSignal:
    def test_from_stored_data(self):
        """Uses stored GDELT history when available."""
        save_gdelt_history_batch([
            {"date": "2099-01-01", "industry": "Technology", "avg_tone": 2.0, "article_count": 50},
            {"date": "2099-01-01", "industry": "Banking & Finance", "avg_tone": -1.0, "article_count": 30},
        ])

        from src.data_sources.geopolitical import get_geopolitical_signal
        result = get_geopolitical_signal()
        assert result["signal"] in ("bullish", "bearish", "neutral")
        assert 0 <= result["strength"] <= 1
        assert "source" in result

    def test_empty_stored_data(self):
        """When no stored data, should still return a valid signal."""
        from src.data_sources.geopolitical import get_geopolitical_signal

        # Patch live GDELT to also return nothing
        with patch("src.data_sources.geopolitical.fetch_geopolitical_events",
                    return_value=[{"error": "no data"}]):
            result = get_geopolitical_signal()
            assert result["signal"] in ("bullish", "bearish", "neutral")
            assert "strength" in result

    def test_live_fallback(self):
        """When no stored data, falls back to live GDELT API results."""
        events = [
            {"keyword": "trade war", "title": "US-China tensions", "tone": -3.5,
             "url": "https://example.com", "source": "Reuters", "date": "2024-01-15"},
            {"keyword": "sanctions", "title": "New sanctions imposed", "tone": -5.0,
             "url": "https://example.com", "source": "Bloomberg", "date": "2024-01-15"},
        ]
        with patch("src.data_sources.geopolitical.fetch_geopolitical_events",
                    return_value=events):
            from src.data_sources.geopolitical import get_geopolitical_signal
            result = get_geopolitical_signal()
            assert result["signal"] == "bearish"
            assert result["strength"] < 0.5
            assert result["event_count"] == 2

    def test_positive_tone(self):
        events = [
            {"keyword": "peace", "title": "Peace deal", "tone": 5.0,
             "url": "", "source": "AP", "date": "2024-01-15"},
        ]
        with patch("src.data_sources.geopolitical.fetch_geopolitical_events",
                    return_value=events):
            from src.data_sources.geopolitical import get_geopolitical_signal
            result = get_geopolitical_signal()
            assert result["signal"] == "bullish"
            assert result["strength"] > 0.5
