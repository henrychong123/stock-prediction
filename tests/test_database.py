"""Tests for src/database.py – CRUD operations on predictions, news, sectors."""

from src.database import (
    save_prediction, get_prediction_history, get_all_prediction_history,
    get_prediction_trend, save_news, get_all_news, get_news_stats,
    save_sector_snapshot, get_sector_history,
)


class TestPredictions:
    def test_save_and_retrieve(self):
        save_prediction("AAPL", "BUY", 0.75, 180.0, 0.35,
                        {"technical": {"signal": "bullish"}},
                        ["MACD crossover"])

        history = get_prediction_history("AAPL")
        assert len(history) == 1
        assert history[0]["symbol"] == "AAPL"
        assert history[0]["action"] == "BUY"
        assert history[0]["confidence"] == 0.75
        assert history[0]["signals"]["technical"]["signal"] == "bullish"
        assert history[0]["reasons"] == ["MACD crossover"]

    def test_multiple_symbols(self):
        save_prediction("AAPL", "BUY", 0.8, 180.0, 0.4, {}, [])
        save_prediction("TSLA", "SELL", 0.6, 250.0, -0.3, {}, [])
        save_prediction("AAPL", "HOLD", 0.5, 181.0, 0.0, {}, [])

        aapl = get_prediction_history("AAPL")
        assert len(aapl) == 2

        all_preds = get_all_prediction_history()
        assert len(all_preds) == 3

    def test_prediction_trend(self):
        save_prediction("MSFT", "BUY", 0.7, 400.0, 0.3, {}, [])
        trend = get_prediction_trend("MSFT", days=30)
        assert len(trend) == 1
        assert trend[0]["action"] == "BUY"

    def test_empty_history(self):
        assert get_prediction_history("NONEXISTENT") == []


class TestNews:
    def test_save_and_retrieve(self):
        save_news("finnhub", "Apple beats earnings",
                  summary="Q4 results exceed expectations",
                  sentiment_label="positive", sentiment_score=0.9)

        news = get_all_news()
        assert len(news) == 1
        assert news[0]["headline"] == "Apple beats earnings"
        assert news[0]["sentiment_label"] == "positive"

    def test_deduplication(self):
        save_news("finnhub", "Same headline", sentiment_label="positive")
        save_news("finnhub", "Same headline", sentiment_label="negative")

        news = get_all_news()
        assert len(news) == 1  # second insert is skipped

    def test_different_platforms_same_headline(self):
        save_news("finnhub", "Breaking news")
        save_news("gdelt", "Breaking news")

        news = get_all_news()
        assert len(news) == 2  # different platforms = not duplicate

    def test_filter_by_platform(self):
        save_news("finnhub", "US news")
        save_news("google-news-my", "MY news")

        us = get_all_news(platform="finnhub")
        assert len(us) == 1
        assert us[0]["source_platform"] == "finnhub"

    def test_news_stats(self):
        save_news("finnhub", "A", sentiment_label="positive")
        save_news("finnhub", "B", sentiment_label="negative")
        save_news("gdelt", "C", sentiment_label="positive")

        stats = get_news_stats()
        assert stats["total"] == 3
        assert stats["by_platform"]["finnhub"] == 2
        assert stats["by_sentiment"]["positive"] == 2


class TestSectors:
    def test_save_and_retrieve(self):
        save_sector_snapshot("Technology", "XLK", "BUY", 0.7, 0.35,
                             {"technical": {"signal": "bullish"}})

        history = get_sector_history("Technology")
        assert len(history) == 1
        assert history[0]["action"] == "BUY"
        assert history[0]["signal_breakdown"]["technical"]["signal"] == "bullish"

    def test_all_sectors_history(self):
        save_sector_snapshot("Technology", "XLK", "BUY", 0.7, 0.35, {})
        save_sector_snapshot("Energy", "XLE", "SELL", 0.6, -0.2, {})

        all_h = get_sector_history()
        assert len(all_h) == 2
