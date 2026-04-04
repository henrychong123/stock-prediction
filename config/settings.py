"""
Configuration settings for the stock prediction system.
API keys are loaded from environment variables or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Finnhub API (free: 60 requests/min)
# Get your key at: https://finnhub.io/register
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# Reddit API (free: 100 requests/min with OAuth)
# Create app at: https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "StockPredictor/1.0")

# Default stock symbols to track
DEFAULT_SYMBOLS = ["AAPL", "TSLA", "GOOGL", "AMZN", "MSFT", "NVDA", "META"]

# Influential figures to monitor (via news coverage)
INFLUENTIAL_FIGURES = [
    "Elon Musk",
    "Donald Trump",
    "Warren Buffett",
    "Jerome Powell",
    "Janet Yellen",
    "Tim Cook",
    "Satya Nadella",
]

# Geopolitical keywords to track
GEOPOLITICAL_KEYWORDS = [
    "Iran war",
    "trade war",
    "sanctions",
    "tariffs",
    "federal reserve",
    "interest rate",
    "oil price",
    "OPEC",
    "NATO",
    "China Taiwan",
]

# Subreddits for social sentiment
REDDIT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "stockmarket",
    "options",
]

# Sentiment analysis model
SENTIMENT_MODEL = "ProsusAI/finbert"

# Prediction weights (how much each signal contributes)
SIGNAL_WEIGHTS = {
    "technical": 0.30,   # Price trends, moving averages
    "news_sentiment": 0.25,  # Financial news sentiment
    "social_sentiment": 0.20,  # Reddit + influential figures
    "geopolitical": 0.15,  # War, sanctions, policy
    "market_momentum": 0.10,  # Volume, volatility
}
