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

# Bursa Malaysia industry categories with 10 stocks each
BURSA_INDUSTRIES = {
    "Banking & Finance": {
        "icon": "🏦",
        "stocks": [
            {"symbol": "1155.KL", "name": "Maybank"},
            {"symbol": "1295.KL", "name": "Public Bank"},
            {"symbol": "1023.KL", "name": "CIMB Group"},
            {"symbol": "5819.KL", "name": "Hong Leong Bank"},
            {"symbol": "1066.KL", "name": "RHB Bank"},
            {"symbol": "1015.KL", "name": "AMMB Holdings"},
            {"symbol": "5258.KL", "name": "Aeon Credit"},
            {"symbol": "6139.KL", "name": "Allianz Malaysia"},
            {"symbol": "1163.KL", "name": "Hong Leong Financial"},
            {"symbol": "5185.KL", "name": "Bursa Malaysia"},
        ]
    },
    "Technology": {
        "icon": "💻",
        "stocks": [
            {"symbol": "0166.KL", "name": "Inari Amertron"},
            {"symbol": "0138.KL", "name": "MY E.G. Services"},
            {"symbol": "7022.KL", "name": "Globetronics"},
            {"symbol": "0072.KL", "name": "Frontken"},
            {"symbol": "5235SS.KL", "name": "Opensys"},
            {"symbol": "0082.KL", "name": "Datasonic"},
            {"symbol": "5136.KL", "name": "Unisem"},
            {"symbol": "7191.KL", "name": " Malaysian Pacific"},
            {"symbol": "5161.KL", "name": "D&O Green Tech"},
            {"symbol": "0078.KL", "name": "Revenue Group"},
        ]
    },
    "Utilities & Energy": {
        "icon": "⚡",
        "stocks": [
            {"symbol": "5347.KL", "name": "Tenaga Nasional"},
            {"symbol": "5183.KL", "name": "Petronas Chemicals"},
            {"symbol": "6033.KL", "name": "Petronas Gas"},
            {"symbol": "7277.KL", "name": "Dialog Group"},
            {"symbol": "6742.KL", "name": "YTL Power"},
            {"symbol": "5218.KL", "name": "Sapura Energy"},
            {"symbol": "3816.KL", "name": "MISC Bhd"},
            {"symbol": "5681.KL", "name": "Petronas Dagangan"},
            {"symbol": "5132.KL", "name": "Deleum"},
            {"symbol": "6556.KL", "name": "Gas Malaysia"},
        ]
    },
    "Telecommunications": {
        "icon": "📡",
        "stocks": [
            {"symbol": "6947.KL", "name": "CelcomDigi"},
            {"symbol": "6888.KL", "name": "Axiata Group"},
            {"symbol": "4863.KL", "name": "TM (Telekom)"},
            {"symbol": "6012.KL", "name": "Maxis"},
            {"symbol": "0008.KL", "name": "OCK Group"},
            {"symbol": "5031.KL", "name": "TIME dotCom"},
            {"symbol": "6076.KL", "name": "U Mobile"},
            {"symbol": "6399.KL", "name": "Astro Malaysia"},
            {"symbol": "5204.KL", "name": "Media Prima"},
            {"symbol": "5878.KL", "name": "Star Media"},
        ]
    },
    "Healthcare": {
        "icon": "🏥",
        "stocks": [
            {"symbol": "5225.KL", "name": "IHH Healthcare"},
            {"symbol": "5168.KL", "name": "Hartalega"},
            {"symbol": "7113.KL", "name": "Top Glove"},
            {"symbol": "7084.KL", "name": "QL Resources"},
            {"symbol": "5148.KL", "name": "KPJ Healthcare"},
            {"symbol": "7153.KL", "name": "Kossan Rubber"},
            {"symbol": "7052.KL", "name": "Supermax"},
            {"symbol": "0391.KL", "name": "Pharmaniaga"},
            {"symbol": "5243.KL", "name": "Duopharma"},
            {"symbol": "0045.KL", "name": "Apex Healthcare"},
        ]
    },
    "Plantation & Agriculture": {
        "icon": "🌿",
        "stocks": [
            {"symbol": "5285.KL", "name": "Sime Darby Plant."},
            {"symbol": "2445.KL", "name": "KL Kepong"},
            {"symbol": "1961.KL", "name": "IOI Corp"},
            {"symbol": "2291.KL", "name": "Genting Plant."},
            {"symbol": "5012.KL", "name": "IJM Plant."},
            {"symbol": "2038.KL", "name": "Boustead Plant."},
            {"symbol": "5069.KL", "name": "FGV Holdings"},
            {"symbol": "2089.KL", "name": "HSL"},
            {"symbol": "1899.KL", "name": "Hap Seng Plant."},
            {"symbol": "9059.KL", "name": "TSH Resources"},
        ]
    },
    "Consumer & Retail": {
        "icon": "🛒",
        "stocks": [
            {"symbol": "4707.KL", "name": "Nestle Malaysia"},
            {"symbol": "5080.KL", "name": "Padini Holdings"},
            {"symbol": "7106.KL", "name": "Aeon Co."},
            {"symbol": "5296.KL", "name": "MR DIY"},
            {"symbol": "5202.KL", "name": "Berjaya Corp"},
            {"symbol": "5196.KL", "name": "Berjaya Food"},
            {"symbol": "3026.KL", "name": "Dutch Lady"},
            {"symbol": "2658.KL", "name": "Fraser & Neave"},
            {"symbol": "5209.KL", "name": "99 Speedmart"},
            {"symbol": "4065.KL", "name": "PPB Group"},
        ]
    },
    "Gaming & Leisure": {
        "icon": "🎰",
        "stocks": [
            {"symbol": "3182.KL", "name": "Genting Bhd"},
            {"symbol": "4715.KL", "name": "Genting Malaysia"},
            {"symbol": "3859.KL", "name": "Magnum"},
            {"symbol": "1562.KL", "name": "Sports Toto"},
            {"symbol": "3948.KL", "name": "Berjaya Sports"},
            {"symbol": "1724.KL", "name": "Paramount Corp"},
            {"symbol": "2836.KL", "name": "Carlsberg"},
            {"symbol": "8664.KL", "name": "SP Setia"},
            {"symbol": "1818.KL", "name": "Bursa Malaysia"},
            {"symbol": "4677.KL", "name": "YTL Corp"},
        ]
    },
}

# Friendly names for Malaysian stocks (since tickers are numeric)
MY_STOCK_NAMES = {s["symbol"]: s["name"]
                  for industry in BURSA_INDUSTRIES.values()
                  for s in industry["stocks"]}

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

# Figure → stock mapping (which stocks a figure commonly moves)
FIGURE_STOCK_MAP = {
    "Elon Musk":      ["TSLA", "DOGE-USD", "BTC-USD", "XCOM"],
    "Donald Trump":   ["DJT", "SPY", "QQQ", "GLD"],
    "Warren Buffett": ["BRK-B", "AAPL", "KO", "BAC", "OXY"],
    "Jerome Powell":  ["SPY", "QQQ", "TLT", "GLD", "DXY"],
    "Janet Yellen":   ["SPY", "TLT"],
    "Tim Cook":       ["AAPL"],
    "Satya Nadella":  ["MSFT"],
    "Jensen Huang":   ["NVDA"],
    "Mark Zuckerberg":["META"],
    "Andy Jassy":     ["AMZN"],
}

MY_FIGURE_STOCK_MAP = {
    "Anwar Ibrahim":       ["^KLSE"],
    "Robert Kuok":         ["2445.KL", "5285.KL"],
    "Tengku Zafrul":       ["^KLSE", "1155.KL"],
    "Bank Negara Malaysia": ["^KLSE", "1155.KL", "1295.KL"],
    "Petronas":            ["5183.KL", "6033.KL", "5347.KL"],
    "Khazanah Nasional":   ["5225.KL", "6947.KL", "4863.KL"],
}

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
# ml_model is included when trained models are available in models/
SIGNAL_WEIGHTS = {
    "technical": 0.22,
    "news_sentiment": 0.18,
    "social_sentiment": 0.12,
    "geopolitical": 0.08,
    "market_momentum": 0.10,
    "earnings": 0.12,        # EPS surprise + beat rate
    "ml_model": 0.18,        # XGBoost + LightGBM ensemble
}

# Malaysian stocks rely more on technicals since Finnhub news isn't available
MY_SIGNAL_WEIGHTS = {
    "technical": 0.28,
    "news_sentiment": 0.10,
    "social_sentiment": 0.10,
    "geopolitical": 0.12,
    "market_momentum": 0.15,
    "earnings": 0.05,        # Limited data for Bursa stocks
    "ml_model": 0.20,
}
