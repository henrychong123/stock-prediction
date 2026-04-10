"""Tests for src/data_sources/social_media.py – Reddit mentions and social signal."""

from unittest.mock import patch, MagicMock


class TestFetchRedditMentions:
    def test_no_credentials(self):
        with patch("src.data_sources.social_media.REDDIT_CLIENT_ID", ""), \
             patch("src.data_sources.social_media.REDDIT_CLIENT_SECRET", ""):
            from src.data_sources.social_media import fetch_reddit_mentions
            result = fetch_reddit_mentions("AAPL")
            assert len(result) == 1
            assert "error" in result[0]

    def test_with_credentials(self):
        mock_post = MagicMock()
        mock_post.title = "AAPL is going up!"
        mock_post.selftext = "Great earnings"
        mock_post.score = 42
        mock_post.upvote_ratio = 0.95
        mock_post.num_comments = 15
        mock_post.created_utc = 1700000000
        mock_post.permalink = "/r/stocks/comments/abc/aapl"

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [mock_post]

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        import src.data_sources.news_sentiment as ns
        ns._sentiment_pipeline = "unavailable"

        with patch("src.data_sources.social_media._get_reddit_client", return_value=mock_reddit):
            from src.data_sources.social_media import fetch_reddit_mentions
            result = fetch_reddit_mentions("AAPL", subreddits=["stocks"])
            assert len(result) == 1
            assert result[0]["title"] == "AAPL is going up!"
            assert result[0]["score"] == 42
            assert "sentiment" in result[0]

        ns._sentiment_pipeline = None


class TestFetchTrendingTickers:
    def test_no_credentials(self):
        with patch("src.data_sources.social_media.REDDIT_CLIENT_ID", ""), \
             patch("src.data_sources.social_media.REDDIT_CLIENT_SECRET", ""):
            from src.data_sources.social_media import fetch_trending_tickers
            result = fetch_trending_tickers()
            assert "error" in result


class TestGetSocialSignal:
    def test_no_data(self):
        with patch("src.data_sources.social_media.fetch_reddit_mentions",
                    return_value=[{"error": "no creds"}]):
            from src.data_sources.social_media import get_social_signal
            result = get_social_signal("AAPL")
            assert result["signal"] == "neutral"
            assert result["strength"] == 0.5
            assert result["post_count"] == 0

    def test_bullish_posts(self):
        posts = [
            {
                "subreddit": "stocks",
                "title": "AAPL to the moon",
                "score": 100,
                "sentiment": {"label": "positive", "score": 0.5},
            },
            {
                "subreddit": "wallstreetbets",
                "title": "AAPL calls printing",
                "score": 50,
                "sentiment": {"label": "positive", "score": 0.3},
            },
        ]
        with patch("src.data_sources.social_media.fetch_reddit_mentions", return_value=posts):
            from src.data_sources.social_media import get_social_signal
            result = get_social_signal("AAPL")
            assert result["signal"] == "bullish"
            assert result["strength"] > 0.5
            assert result["post_count"] == 2

    def test_bearish_posts(self):
        posts = [
            {
                "subreddit": "stocks",
                "title": "AAPL is crashing",
                "score": 80,
                "sentiment": {"label": "negative", "score": -0.6},
            },
        ]
        with patch("src.data_sources.social_media.fetch_reddit_mentions", return_value=posts):
            from src.data_sources.social_media import get_social_signal
            result = get_social_signal("AAPL")
            assert result["signal"] == "bearish"
            assert result["strength"] < 0.5
