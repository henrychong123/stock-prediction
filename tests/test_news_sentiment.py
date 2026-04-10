"""Tests for src/data_sources/news_sentiment.py – sentiment analysis, news fetching, signals."""

from unittest.mock import patch, MagicMock


class TestKeywordSentiment:
    def test_positive(self):
        from src.data_sources.news_sentiment import _keyword_sentiment
        result = _keyword_sentiment("Stock surge rally profit growth bullish")
        assert result["label"] == "positive"
        assert result["score"] > 0

    def test_negative(self):
        from src.data_sources.news_sentiment import _keyword_sentiment
        result = _keyword_sentiment("Market crash plunge recession fear crisis")
        assert result["label"] == "negative"
        assert result["score"] < 0

    def test_neutral(self):
        from src.data_sources.news_sentiment import _keyword_sentiment
        result = _keyword_sentiment("The weather is nice today")
        assert result["label"] == "neutral"
        assert result["score"] == 0.0


class TestAnalyzeSentiment:
    def test_fallback_to_keywords(self):
        """When FinBERT is unavailable, should use keyword fallback."""
        from src.data_sources import news_sentiment
        news_sentiment._sentiment_pipeline = "unavailable"

        result = news_sentiment.analyze_sentiment("Stock surge rally profit")
        assert result["label"] == "positive"
        # Restore
        news_sentiment._sentiment_pipeline = None

    def test_neutral_text(self):
        from src.data_sources import news_sentiment
        news_sentiment._sentiment_pipeline = "unavailable"

        result = news_sentiment.analyze_sentiment("Regular quarterly report filed")
        assert result["label"] == "neutral"
        news_sentiment._sentiment_pipeline = None


class TestFetchMarketNews:
    def test_no_api_key(self):
        with patch("src.data_sources.news_sentiment.FINNHUB_API_KEY", ""):
            from src.data_sources.news_sentiment import fetch_market_news
            result = fetch_market_news()
            assert len(result) == 1
            assert "error" in result[0]

    def test_with_api_key(self):
        mock_client = MagicMock()
        mock_client.general_news.return_value = [
            {
                "headline": "Apple hits record high",
                "summary": "Strong earnings beat expectations",
                "source": "Reuters",
                "url": "https://example.com",
                "datetime": 1700000000,
            }
        ]

        import src.data_sources.news_sentiment as ns
        ns._sentiment_pipeline = "unavailable"

        with patch("src.data_sources.news_sentiment.FINNHUB_API_KEY", "test_key"), \
             patch("finnhub.Client", return_value=mock_client):
            result = ns.fetch_market_news()
            assert len(result) == 1
            assert result[0]["headline"] == "Apple hits record high"
            assert "sentiment" in result[0]

        ns._sentiment_pipeline = None


class TestFetchCompanyNews:
    def test_no_api_key(self):
        with patch("src.data_sources.news_sentiment.FINNHUB_API_KEY", ""):
            from src.data_sources.news_sentiment import fetch_company_news
            result = fetch_company_news("AAPL")
            assert len(result) == 1
            assert "error" in result[0]

    def test_with_api_key(self):
        mock_client = MagicMock()
        mock_client.company_news.return_value = [
            {
                "headline": "AAPL beats Q4",
                "summary": "Revenue up 10%",
                "source": "Bloomberg",
                "datetime": 1700000000,
            }
        ]

        import src.data_sources.news_sentiment as ns
        ns._sentiment_pipeline = "unavailable"

        with patch("src.data_sources.news_sentiment.FINNHUB_API_KEY", "test_key"), \
             patch("finnhub.Client", return_value=mock_client):
            result = ns.fetch_company_news("AAPL")
            assert len(result) == 1
            assert "sentiment" in result[0]

        ns._sentiment_pipeline = None


class TestGetNewsSignal:
    def test_no_news(self):
        with patch("src.data_sources.news_sentiment.fetch_company_news", return_value=[{"error": "no key"}]):
            from src.data_sources.news_sentiment import get_news_signal
            result = get_news_signal("AAPL")
            assert result["signal"] == "neutral"
            assert result["strength"] == 0.5

    def test_bullish_news(self):
        articles = [
            {"headline": "Apple rallies", "sentiment": {"label": "positive", "score": 0.5}},
            {"headline": "Revenue beats", "sentiment": {"label": "positive", "score": 0.3}},
        ]
        with patch("src.data_sources.news_sentiment.fetch_company_news", return_value=articles):
            from src.data_sources.news_sentiment import get_news_signal
            result = get_news_signal("AAPL")
            assert result["signal"] == "bullish"
            assert result["strength"] > 0.5
            assert result["article_count"] == 2

    def test_bearish_news(self):
        articles = [
            {"headline": "Apple falls", "sentiment": {"label": "negative", "score": -0.5}},
            {"headline": "Revenue misses", "sentiment": {"label": "negative", "score": -0.4}},
        ]
        with patch("src.data_sources.news_sentiment.fetch_company_news", return_value=articles):
            from src.data_sources.news_sentiment import get_news_signal
            result = get_news_signal("AAPL")
            assert result["signal"] == "bearish"
            assert result["strength"] < 0.5


class TestGetFigureSignal:
    def test_no_news(self):
        with patch("src.data_sources.news_sentiment.fetch_influential_figure_news", return_value=[]):
            from src.data_sources.news_sentiment import get_figure_signal
            result = get_figure_signal("AAPL")
            assert result["signal"] == "neutral"
            assert result["total_mentions"] == 0
