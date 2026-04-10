"""Tests for src/database.py – CRUD operations on predictions, news, sectors,
watchlist, price snapshots, training data, GDELT history, daily features."""

from src.database import (
    save_prediction, get_prediction_history, get_all_prediction_history,
    get_prediction_trend, save_news, get_all_news, get_news_stats,
    save_sector_snapshot, get_sector_history,
    get_news_latest_fetched, get_tracker_last_fetched, set_tracker_last_fetched,
    save_price_snapshot, get_price_history, get_latest_snapshot, get_tracked_symbols,
    get_prediction_accuracy,
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    update_watchlist_item, is_in_watchlist,
    save_gdelt_history_batch, get_gdelt_tone_for_date,
    get_latest_predictions,
    save_training_row, save_training_batch, get_training_data, get_training_symbols,
    save_daily_features, get_daily_features,
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


class TestNewsTrackerState:
    def test_set_and_get(self):
        set_tracker_last_fetched("finnhub")
        result = get_tracker_last_fetched("finnhub")
        assert result is not None

    def test_get_nonexistent(self):
        assert get_tracker_last_fetched("nonexistent") is None

    def test_update_existing(self):
        set_tracker_last_fetched("rss")
        first = get_tracker_last_fetched("rss")
        set_tracker_last_fetched("rss")
        second = get_tracker_last_fetched("rss")
        assert second >= first

    def test_news_latest_fetched_empty(self):
        assert get_news_latest_fetched() is None

    def test_news_latest_fetched(self):
        save_news("finnhub", "Test headline")
        result = get_news_latest_fetched()
        assert result is not None


class TestPriceSnapshots:
    def test_save_and_get_latest(self):
        save_price_snapshot("AAPL", 150.0, prev_close=148.0,
                            change_abs=2.0, change_pct=1.35)
        snap = get_latest_snapshot("AAPL")
        assert snap is not None
        assert snap["price"] == 150.0
        assert snap["prev_close"] == 148.0

    def test_get_latest_nonexistent(self):
        assert get_latest_snapshot("ZZZZ") is None

    def test_price_history(self):
        save_price_snapshot("TSLA", 200.0)
        save_price_snapshot("TSLA", 201.0)
        history = get_price_history("TSLA", hours=24)
        assert len(history) >= 2

    def test_tracked_symbols(self):
        save_price_snapshot("AAPL", 150.0)
        save_price_snapshot("TSLA", 200.0)
        symbols = get_tracked_symbols()
        assert "AAPL" in symbols
        assert "TSLA" in symbols

    def test_tracked_symbols_empty(self):
        assert get_tracked_symbols() == []


class TestPredictionAccuracy:
    def test_empty(self):
        result = get_prediction_accuracy()
        assert result["summary"]["total"] == 0
        assert result["summary"]["accuracy_pct"] is None

    def test_with_data(self):
        save_prediction("AAPL", "BUY", 0.8, 150.0, 0.4, {}, [])
        save_price_snapshot("AAPL", 150.0)
        save_price_snapshot("AAPL", 160.0)
        result = get_prediction_accuracy()
        assert result["summary"]["total"] >= 1


class TestWatchlist:
    def test_add_and_get(self):
        added = add_to_watchlist("AAPL", name="Apple Inc")
        assert added is True
        items = get_watchlist()
        assert len(items) == 1
        assert items[0]["symbol"] == "AAPL"
        assert items[0]["name"] == "Apple Inc"

    def test_is_in_watchlist(self):
        add_to_watchlist("TSLA")
        assert is_in_watchlist("TSLA") is True
        assert is_in_watchlist("ZZZZ") is False

    def test_duplicate_add(self):
        add_to_watchlist("AAPL")
        added = add_to_watchlist("AAPL")
        assert added is False
        assert len(get_watchlist()) == 1

    def test_remove(self):
        add_to_watchlist("AAPL")
        removed = remove_from_watchlist("AAPL")
        assert removed is True
        assert is_in_watchlist("AAPL") is False

    def test_remove_nonexistent(self):
        removed = remove_from_watchlist("ZZZZ")
        assert removed is False

    def test_update_note(self):
        add_to_watchlist("AAPL")
        updated = update_watchlist_item("AAPL", note="Great stock")
        assert updated is True
        items = get_watchlist()
        assert items[0]["note"] == "Great stock"

    def test_update_alerts(self):
        add_to_watchlist("AAPL")
        update_watchlist_item("AAPL", alert_above=200.0, alert_below=100.0)
        items = get_watchlist()
        assert items[0]["alert_above"] == 200.0
        assert items[0]["alert_below"] == 100.0

    def test_update_empty(self):
        add_to_watchlist("AAPL")
        updated = update_watchlist_item("AAPL")
        assert updated is False


class TestGDELTHistory:
    def test_save_and_retrieve(self):
        rows = [
            {"date": "2024-01-15", "industry": "Technology", "avg_tone": 1.5, "article_count": 10, "keywords": "AI"},
            {"date": "2024-01-15", "industry": "Banking & Finance", "avg_tone": -0.5, "article_count": 8},
        ]
        save_gdelt_history_batch(rows)
        result = get_gdelt_tone_for_date("2024-01-15")
        assert "Technology" in result
        assert result["Technology"]["avg_tone"] == 1.5
        assert result["Banking & Finance"]["avg_tone"] == -0.5

    def test_filter_by_industry(self):
        save_gdelt_history_batch([
            {"date": "2024-01-15", "industry": "Technology", "avg_tone": 1.5, "article_count": 10},
            {"date": "2024-01-15", "industry": "Energy", "avg_tone": -2.0, "article_count": 5},
        ])
        result = get_gdelt_tone_for_date("2024-01-15", industry="Technology")
        assert "Technology" in result
        assert "Energy" not in result

    def test_empty_batch(self):
        save_gdelt_history_batch([])
        result = get_gdelt_tone_for_date("2024-01-15")
        assert result == {}


class TestLatestPredictions:
    def test_latest_per_symbol(self):
        save_prediction("AAPL", "BUY", 0.7, 150.0, 0.3, {}, [])
        save_prediction("AAPL", "HOLD", 0.5, 151.0, 0.0, {}, [])
        save_prediction("TSLA", "SELL", 0.6, 200.0, -0.2, {}, [])

        latest = get_latest_predictions()
        assert "AAPL" in latest
        assert latest["AAPL"]["action"] == "HOLD"
        assert "TSLA" in latest

    def test_filter_by_symbols(self):
        save_prediction("AAPL", "BUY", 0.7, 150.0, 0.3, {}, [])
        save_prediction("TSLA", "SELL", 0.6, 200.0, -0.2, {}, [])

        latest = get_latest_predictions(symbols=["AAPL"])
        assert "AAPL" in latest
        assert "TSLA" not in latest

    def test_empty(self):
        assert get_latest_predictions() == {}


class TestTrainingData:
    def test_save_single_row(self):
        row = {"symbol": "AAPL", "date": "2024-01-15", "close": 150.0, "rsi": 55.0}
        save_training_row(row)
        data = get_training_data("AAPL")
        assert len(data) == 1
        assert data[0]["close"] == 150.0

    def test_save_batch(self):
        rows = [
            {"symbol": "AAPL", "date": "2024-01-15", "close": 150.0},
            {"symbol": "AAPL", "date": "2024-01-16", "close": 152.0},
            {"symbol": "TSLA", "date": "2024-01-15", "close": 200.0},
        ]
        save_training_batch(rows)
        data = get_training_data()
        assert len(data) == 3

    def test_upsert(self):
        save_training_row({"symbol": "AAPL", "date": "2024-01-15", "close": 150.0})
        save_training_row({"symbol": "AAPL", "date": "2024-01-15", "close": 155.0})
        data = get_training_data("AAPL")
        assert len(data) == 1
        assert data[0]["close"] == 155.0

    def test_training_symbols(self):
        save_training_batch([
            {"symbol": "AAPL", "date": "2024-01-15"},
            {"symbol": "TSLA", "date": "2024-01-15"},
        ])
        symbols = get_training_symbols()
        assert "AAPL" in symbols
        assert "TSLA" in symbols

    def test_empty(self):
        assert get_training_data() == []
        assert get_training_symbols() == []


class TestDailyFeatures:
    def test_save_and_retrieve(self):
        row = {
            "symbol": "AAPL", "date": "2024-01-15",
            "news_sentiment": 0.5, "news_count": 10,
            "reddit_sentiment": 0.3, "reddit_count": 5,
            "gdelt_tone": 1.2, "fear_greed": 55.0,
        }
        save_daily_features(row)
        data = get_daily_features("AAPL")
        assert len(data) == 1
        assert data[0]["news_sentiment"] == 0.5
        assert data[0]["fear_greed"] == 55.0

    def test_all_features(self):
        save_daily_features({"symbol": "AAPL", "date": "2024-01-15"})
        save_daily_features({"symbol": "TSLA", "date": "2024-01-15"})
        data = get_daily_features()
        assert len(data) == 2

    def test_empty(self):
        assert get_daily_features() == []
