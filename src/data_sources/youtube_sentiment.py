"""
YouTube Financial Sentiment Crawler — searches for stock-related videos
and extracts comments + engagement metrics.

Requires: YouTube Data API v3 key (free, 10K quota/day).
Falls back gracefully if key not set.

Usage:
    from src.data_sources.youtube_sentiment import fetch_youtube_sentiment
    articles = fetch_youtube_sentiment("AAPL")
"""

import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def _get_youtube_client():
    """Lazy-load YouTube API client."""
    if not YOUTUBE_API_KEY:
        return None
    try:
        from googleapiclient.discovery import build
        return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    except ImportError:
        log.warning("google-api-python-client not installed. Run: pip install google-api-python-client")
        return None
    except Exception as e:
        log.warning(f"YouTube client error: {e}")
        return None


def fetch_youtube_sentiment(symbol: str, max_videos: int = 5) -> list[dict]:
    """Search YouTube for stock-related videos and extract data.

    Args:
        symbol: Stock ticker (e.g., "AAPL", "TSLA")
        max_videos: Max videos to analyze

    Returns:
        List of {headline, summary, view_count, like_count, comment_count,
                 top_comments, source_platform, related_symbol}
    """
    client = _get_youtube_client()
    if not client:
        return []

    try:
        # Search for stock analysis videos
        query = f"{symbol} stock analysis"
        search_resp = client.search().list(
            q=query,
            type="video",
            part="snippet",
            maxResults=max_videos,
            order="date",  # most recent
            relevanceLanguage="en",
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        if not video_ids:
            return []

        # Get video statistics
        stats_resp = client.videos().list(
            id=",".join(video_ids),
            part="statistics,snippet",
        ).execute()

        articles = []
        for video in stats_resp.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})

            title = snippet.get("title", "")
            if not title:
                continue

            view_count = int(stats.get("viewCount", 0))
            like_count = int(stats.get("likeCount", 0))
            comment_count = int(stats.get("commentCount", 0))

            # Fetch top comments for this video
            top_comments = []
            try:
                comments_resp = client.commentThreads().list(
                    videoId=video["id"],
                    part="snippet",
                    maxResults=10,
                    order="relevance",
                ).execute()

                for thread in comments_resp.get("items", []):
                    comment = thread["snippet"]["topLevelComment"]["snippet"]
                    top_comments.append({
                        "text": comment.get("textDisplay", "")[:200],
                        "likes": comment.get("likeCount", 0),
                    })
            except Exception:
                pass  # comments may be disabled

            published = snippet.get("publishedAt", "")

            articles.append({
                "headline": title,
                "summary": snippet.get("description", "")[:300],
                "url": f"https://youtube.com/watch?v={video['id']}",
                "source_name": snippet.get("channelTitle", "YouTube"),
                "source_platform": "youtube",
                "related_symbol": symbol,
                "fetched_at": datetime.now().isoformat(),
                "published_at": published,
                # Extra YouTube-specific data
                "view_count": view_count,
                "like_count": like_count,
                "comment_count": comment_count,
                "top_comments": top_comments,
                # Engagement score (normalized)
                "engagement_score": _calc_engagement(view_count, like_count, comment_count),
            })

        return articles
    except Exception as e:
        log.warning(f"YouTube search failed for {symbol}: {e}")
        return []


def _calc_engagement(views: int, likes: int, comments: int) -> float:
    """Calculate engagement score 0-1 based on video metrics."""
    if views <= 0:
        return 0
    # Engagement rate = (likes + comments * 5) / views
    # Comments weighted more (indicates stronger opinion)
    rate = (likes + comments * 5) / views
    # Normalize: 1% engagement = 0.5, 5% = 1.0
    return min(rate / 0.05, 1.0)


def fetch_youtube_market_news(max_videos: int = 10) -> list[dict]:
    """Fetch general stock market videos from popular finance channels."""
    all_articles = []
    seen = set()

    for query in ["stock market today", "market news today", "trading stocks"]:
        articles = fetch_youtube_sentiment(query, max_videos=5)
        for a in articles:
            if a["headline"] not in seen:
                seen.add(a["headline"])
                a["related_symbol"] = ""
                all_articles.append(a)

    return all_articles[:max_videos]
