"""
Social media sentiment from Reddit.

Data source:
- Reddit (PRAW): Free API (100 req/min), covers wallstreetbets, stocks, etc.

Note on X/Twitter: The free API tier is effectively read-only dead ($200/mo for basic).
We monitor influential figures via news coverage instead (see news_sentiment.py).
"""

import praw
from datetime import datetime

from config.settings import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS,
)


def _get_reddit_client() -> praw.Reddit | None:
    """Create Reddit client if credentials are available."""
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None

    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def fetch_reddit_mentions(
    symbol: str,
    subreddits: list[str] | None = None,
    limit: int = 25,
) -> list[dict]:
    """Fetch Reddit posts mentioning a stock symbol.

    Args:
        symbol: Stock ticker (e.g., "TSLA")
        subreddits: Which subreddits to search (defaults to config list)
        limit: Max posts per subreddit

    Returns:
        List of post dicts with title, score, comments, subreddit, sentiment
    """
    reddit = _get_reddit_client()
    if reddit is None:
        return [{"error": "Reddit credentials not set. See .env.example"}]

    if subreddits is None:
        subreddits = REDDIT_SUBREDDITS

    # Import sentiment analysis
    from src.data_sources.news_sentiment import analyze_sentiment

    posts = []
    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.search(f"${symbol} OR {symbol}", sort="new", limit=limit):
                text = f"{post.title}. {post.selftext[:300]}" if post.selftext else post.title
                sentiment = analyze_sentiment(text)

                posts.append({
                    "subreddit": sub_name,
                    "title": post.title,
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "created": datetime.fromtimestamp(post.created_utc).isoformat(),
                    "url": f"https://reddit.com{post.permalink}",
                    "sentiment": sentiment,
                })
        except Exception as e:
            posts.append({"subreddit": sub_name, "error": str(e)})

    # Sort by score (popularity)
    posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    return posts


def fetch_trending_tickers(subreddits: list[str] | None = None, limit: int = 50) -> dict:
    """Find the most mentioned stock tickers across Reddit.

    Returns:
        Dict mapping ticker -> mention count, sorted by frequency
    """
    import re

    reddit = _get_reddit_client()
    if reddit is None:
        return {"error": "Reddit credentials not set"}

    if subreddits is None:
        subreddits = REDDIT_SUBREDDITS[:3]  # Limit to top 3 for speed

    # Common words to exclude (not stock tickers)
    exclude = {
        "I", "A", "AM", "PM", "CEO", "IPO", "ETF", "DD", "YOLO", "IMO",
        "TL", "DR", "USA", "GDP", "SEC", "FBI", "CIA", "NASA", "AI", "IT",
        "THE", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER", "WAS",
        "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW",
        "OLD", "SEE", "WAY", "WHO", "DID", "GOT", "HIM", "HIS", "LET", "SAY",
    }

    ticker_pattern = re.compile(r'\$([A-Z]{2,5})\b|\b([A-Z]{2,5})\b')
    ticker_counts: dict[str, int] = {}

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=limit):
                text = f"{post.title} {post.selftext[:500]}"
                matches = ticker_pattern.findall(text)
                for m in matches:
                    ticker = m[0] or m[1]
                    if ticker not in exclude and len(ticker) >= 2:
                        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        except Exception:
            continue

    # Sort by count
    return dict(sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:20])


def get_social_signal(symbol: str) -> dict:
    """Aggregate social media sentiment into a trading signal.

    Returns:
        Dict with signal, strength, post count, and top discussions
    """
    posts = fetch_reddit_mentions(symbol)

    if not posts or "error" in posts[0]:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "post_count": 0,
            "reasons": ["No social media data (set Reddit credentials in .env)"],
        }

    valid_posts = [p for p in posts if "error" not in p]
    if not valid_posts:
        return {"signal": "neutral", "strength": 0.5, "post_count": 0, "reasons": ["No posts found"]}

    # Build set of influential figure names for boost detection
    from config.settings import INFLUENTIAL_FIGURES, MY_INFLUENTIAL_FIGURES
    all_figures = [f.lower() for f in INFLUENTIAL_FIGURES + MY_INFLUENTIAL_FIGURES]

    # Weight sentiment by post popularity (upvotes) + figure boost
    weighted_scores = []
    total_weight = 0
    figure_mentions = []

    for post in valid_posts:
        weight = max(post.get("score", 1), 1)  # Minimum weight of 1
        score = post["sentiment"]["score"]

        # Boost posts that mention influential figures (1.5x weight)
        title_lower = post.get("title", "").lower()
        mentioned_figure = None
        for fig in all_figures:
            if fig in title_lower:
                weight *= 1.5
                mentioned_figure = fig.title()
                figure_mentions.append({
                    "figure": mentioned_figure,
                    "title": post.get("title", ""),
                    "sentiment": post["sentiment"]["label"],
                    "score": post.get("score", 0),
                })
                break

        weighted_scores.append(score * weight)
        total_weight += weight

    avg_sentiment = sum(weighted_scores) / total_weight if total_weight > 0 else 0
    strength = (avg_sentiment + 1) / 2  # Normalize to 0-1

    if avg_sentiment > 0.1:
        signal = "bullish"
    elif avg_sentiment < -0.1:
        signal = "bearish"
    else:
        signal = "neutral"

    # Top discussed posts
    top_posts = [f"[r/{p['subreddit']}] {p['title']} (↑{p['score']})" for p in valid_posts[:5]]

    # Add figure-related posts to reasons
    for fm in figure_mentions[:3]:
        top_posts.append(f"[{fm['figure']}] {fm['title']}")

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "avg_sentiment": round(avg_sentiment, 3),
        "post_count": len(valid_posts),
        "figure_mentions": figure_mentions,
        "reasons": top_posts,
    }
