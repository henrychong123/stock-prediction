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

# ===== MULTI-MARKET SUPPORT =====

MARKETS = {
    "US": {
        "name": "United States",
        "currency": "USD",
        "index": "^GSPC",          # S&P 500
        "index_name": "S&P 500",
        "suffix": "",               # No suffix for US stocks
        "default_symbols": ["AAPL", "TSLA", "GOOGL", "AMZN", "MSFT", "NVDA", "META"],
        "trading_hours": "09:30-16:00 ET",
        "finnhub_supported": True,
    },
    "MY": {
        "name": "Malaysia",
        "currency": "MYR",
        "index": "^KLSE",           # FTSE Bursa Malaysia KLCI
        "index_name": "KLCI",
        "suffix": ".KL",            # yfinance suffix for Bursa Malaysia
        "default_symbols": [
            "1155.KL",   # Maybank
            "1295.KL",   # Public Bank
            "1023.KL",   # CIMB Group
            "5347.KL",   # Tenaga Nasional
            "5183.KL",   # Petronas Chemicals
            "5225.KL",   # IHH Healthcare
            "6888.KL",   # Axiata Group
            "6947.KL",   # CelcomDigi
            "5819.KL",   # Hong Leong Bank
            "8869.KL",   # Press Metal
        ],
        "trading_hours": "09:00-12:30, 14:30-17:00 MYT",
        "finnhub_supported": False,  # Finnhub free tier doesn't cover MY
    },
}

# Friendly names for Malaysian stocks (since tickers are numeric)
MY_STOCK_NAMES = {
    "1155.KL": "Maybank",
    "1295.KL": "Public Bank",
    "1023.KL": "CIMB Group",
    "5347.KL": "Tenaga Nasional",
    "5183.KL": "Petronas Chemicals",
    "5225.KL": "IHH Healthcare",
    "6888.KL": "Axiata Group",
    "6947.KL": "CelcomDigi",
    "5819.KL": "Hong Leong Bank",
    "8869.KL": "Press Metal",
    "5285.KL": "Sime Darby Plant.",
    "1066.KL": "RHB Bank",
    "4863.KL": "TM (Telekom)",
    "6012.KL": "Maxis",
    "3182.KL": "Genting Bhd",
    "4715.KL": "Genting Malaysia",
    "5168.KL": "Hartalega",
    "7113.KL": "Top Glove",
    "7084.KL": "QL Resources",
    "5235.KL": "Petronas Gas",
    "6033.KL": "Petronas Dagangan",
    "1015.KL": "AMMB Holdings",
    "6742.KL": "YTL Power",
    "4707.KL": "Nestle Malaysia",
    "3816.KL": "MISC Bhd",
    "5681.KL": "Petronas LPG",
    "2445.KL": "KL Kepong",
    "1961.KL": "IOI Corp",
    "5218.KL": "Sapura Energy",
}

# Default market
DEFAULT_MARKET = os.getenv("DEFAULT_MARKET", "US")

# Backward compatible default symbols (based on market)
DEFAULT_SYMBOLS = MARKETS[DEFAULT_MARKET]["default_symbols"]

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

# Malaysia-specific influential figures
MY_INFLUENTIAL_FIGURES = [
    "Anwar Ibrahim",        # PM of Malaysia
    "Robert Kuok",          # Richest Malaysian
    "Tengku Zafrul",        # Finance Minister
    "Bank Negara Malaysia",
    "Petronas",
    "Khazanah Nasional",
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

# Malaysia-specific geopolitical keywords
MY_GEOPOLITICAL_KEYWORDS = [
    "Malaysia economy",
    "Bank Negara interest rate",
    "ringgit",
    "palm oil price",
    "Malaysia trade",
    "ASEAN",
    "Malaysia China",
    "Petronas",
    "Malaysia budget",
    "semiconductor Malaysia",
]

# Subreddits for social sentiment
REDDIT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "stockmarket",
    "options",
]

MY_REDDIT_SUBREDDITS = [
    "MalaysianPF",
    "bursabets",
    "malaysia",
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

# Malaysian stocks rely more on technicals since Finnhub news isn't available
MY_SIGNAL_WEIGHTS = {
    "technical": 0.40,
    "news_sentiment": 0.15,
    "social_sentiment": 0.10,
    "geopolitical": 0.20,   # Palm oil, ringgit, ASEAN politics matter more
    "market_momentum": 0.15,
}
