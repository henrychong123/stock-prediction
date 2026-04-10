"""Tests for social crawlers: Yahoo Finance News, RSS feeds, YouTube, LLM analyzer."""

import pytest
from unittest.mock import patch, MagicMock


class TestYahooFinanceNews:

    @patch("src.data_sources.yahoo_news._get_session")
    def test_fetch_yahoo_news(self, mock_session):
        from src.data_sources.yahoo_news import fetch_yahoo_news

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "news": [
                {"title": "Apple beats earnings", "publisher": "Reuters",
                 "link": "https://example.com/1", "providerPublishTime": 1775782146},
                {"title": "iPhone sales surge", "publisher": "Bloomberg",
                 "link": "https://example.com/2", "providerPublishTime": 1775776799},
            ]
        }
        mock_session.return_value.get.return_value = mock_resp

        articles = fetch_yahoo_news("AAPL")
        assert len(articles) == 2
        assert articles[0]["headline"] == "Apple beats earnings"
        assert articles[0]["source_platform"] == "yahoo-finance"
        assert articles[0]["related_symbol"] == "AAPL"

    @patch("src.data_sources.yahoo_news._get_session")
    def test_fetch_yahoo_news_empty(self, mock_session):
        from src.data_sources.yahoo_news import fetch_yahoo_news

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"news": []}
        mock_session.return_value.get.return_value = mock_resp

        assert fetch_yahoo_news("AAPL") == []

    @patch("src.data_sources.yahoo_news._get_session")
    def test_fetch_yahoo_news_error(self, mock_session):
        from src.data_sources.yahoo_news import fetch_yahoo_news

        mock_session.return_value.get.side_effect = Exception("timeout")
        assert fetch_yahoo_news("AAPL") == []


class TestMarketNewsRSS:

    @patch("src.data_sources.market_news_rss.feedparser.parse")
    def test_fetch_all_rss(self, mock_parse):
        from src.data_sources.market_news_rss import fetch_all_rss_news

        class FakeEntry:
            def __init__(self, title):
                self.title = title
                self.summary = "Test summary"
                self.link = "https://example.com"
                self.published_parsed = (2026, 4, 10, 12, 0, 0, 0, 0, 0)
            def get(self, key, default=""):
                return getattr(self, key, default)

        mock_feed = MagicMock()
        mock_feed.entries = [FakeEntry("Market rallies on earnings")]
        mock_parse.return_value = mock_feed

        articles = fetch_all_rss_news()
        assert len(articles) >= 1

    @patch("src.data_sources.market_news_rss.feedparser.parse")
    def test_rss_deduplication(self, mock_parse):
        from src.data_sources.market_news_rss import fetch_all_rss_news

        class FakeEntry:
            def __init__(self, title):
                self.title = title
                self.summary = ""
                self.link = ""
                self.published_parsed = None
            def get(self, key, default=""):
                return getattr(self, key, default)

        mock_feed = MagicMock()
        mock_feed.entries = [FakeEntry("Same headline across feeds"), FakeEntry("Same headline across feeds")]
        mock_parse.return_value = mock_feed

        articles = fetch_all_rss_news()
        titles = [a["headline"] for a in articles]
        assert titles.count("Same headline across feeds") <= 1


class TestYouTubeSentiment:

    def test_no_api_key(self):
        from src.data_sources.youtube_sentiment import fetch_youtube_sentiment
        # Should return empty list when no API key
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": ""}):
            assert fetch_youtube_sentiment("AAPL") == []

    def test_engagement_score(self):
        from src.data_sources.youtube_sentiment import _calc_engagement
        assert _calc_engagement(0, 0, 0) == 0
        assert _calc_engagement(1000, 50, 10) > 0
        assert _calc_engagement(1000, 50, 10) <= 1.0


class TestLLMAnalyzer:

    def test_ollama_unavailable(self):
        from src.analysis.llm_analyzer import analyze_headline
        with patch("src.analysis.llm_analyzer.is_ollama_available", return_value=False):
            assert analyze_headline("Test headline") is None

    def test_parse_llm_response(self):
        from src.analysis.llm_analyzer import _parse_llm_response

        # Valid JSON
        result = _parse_llm_response('{"event_type": "earnings", "sentiment": "bullish"}')
        assert result["event_type"] == "earnings"

        # JSON embedded in text
        result = _parse_llm_response('Here is the analysis: {"event_type": "tariff"} done.')
        assert result["event_type"] == "tariff"

        # Invalid
        assert _parse_llm_response("no json here") is None
        assert _parse_llm_response("") is None

    @patch("src.analysis.llm_analyzer._call_ollama")
    @patch("src.analysis.llm_analyzer.is_ollama_available", return_value=True)
    def test_analyze_headline(self, mock_avail, mock_call):
        from src.analysis.llm_analyzer import analyze_headline

        mock_call.return_value = '{"event_type": "earnings", "affected_stocks": ["AAPL"], "sentiment": "bullish", "confidence": 0.9, "reasoning": "Beat estimates"}'

        result = analyze_headline("Apple beats earnings by 20%")
        assert result is not None
        assert result["event_type"] == "earnings"
        assert "AAPL" in result["affected_stocks"]

    def test_enrich_fallback(self):
        from src.analysis.llm_analyzer import enrich_catalyst_with_llm

        keyword_result = {"event_type": "earnings", "score": 50}
        with patch("src.analysis.llm_analyzer.analyze_headline", return_value=None):
            result = enrich_catalyst_with_llm("Test", keyword_result)
            assert result == keyword_result  # unchanged fallback


class TestSocialCollector:

    @patch("src.data.social_collector.collect_rss_news", return_value=5)
    @patch("src.data.social_collector.collect_yahoo_news", return_value=10)
    @patch("src.data.social_collector.collect_youtube", return_value=0)
    def test_run(self, mock_yt, mock_yahoo, mock_rss):
        from src.data.social_collector import run
        total = run(skip_youtube=True, skip_sentiment=True)
        assert total == 15
        mock_rss.assert_called_once()
        mock_yahoo.assert_called_once()
