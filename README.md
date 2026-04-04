# Stock Prediction System

Multi-signal stock prediction engine that combines technical analysis, news sentiment, social media, and geopolitical events.

## Data Sources

| Source | Platform | What it provides | Cost |
|--------|----------|-----------------|------|
| Stock Prices | **Yahoo Finance** (yfinance) | Historical prices, technicals (RSI, MACD, Bollinger) | Free |
| Real-time Quotes | **Finnhub** | Live prices, company news | Free (60 req/min) |
| News Sentiment | **Finnhub + FinBERT** | AI-powered financial sentiment analysis | Free |
| Geopolitical | **GDELT Project** | War, sanctions, policy events from 100+ languages | Free |
| Social Media | **Reddit** (PRAW) | r/wallstreetbets, r/stocks sentiment | Free |
| Influential Figures | **News coverage** | Musk, Trump, Buffett, Powell mentions in news | Free |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up API keys (Finnhub is free, Reddit is optional)
cp .env.example .env
# Edit .env with your keys

# 3. Run predictions
python main.py TSLA AAPL NVDA
```

## Usage

```bash
# Predict specific stocks
python main.py TSLA AAPL NVDA

# Predict all default stocks (AAPL, TSLA, GOOGL, AMZN, MSFT, NVDA, META)
python main.py

# View latest market news with sentiment
python main.py --news

# View geopolitical events (wars, sanctions, tariffs)
python main.py --geopolitical

# See trending tickers on Reddit
python main.py --trending
```

## How It Works

The system gathers 5 types of signals and combines them with configurable weights:

| Signal | Weight | Source |
|--------|--------|--------|
| Technical Analysis | 30% | Price trends, RSI, MACD, Bollinger Bands |
| News Sentiment | 25% | Company + market news via FinBERT NLP |
| Social Sentiment | 20% | Reddit discussions + influential figure news |
| Geopolitical | 15% | GDELT events (wars, sanctions, policy) |
| Market Momentum | 10% | Volume and volatility patterns |

Output: **STRONG BUY / BUY / HOLD / SELL / STRONG SELL** with confidence score.

## API Keys

- **Finnhub** (recommended): Free at [finnhub.io/register](https://finnhub.io/register) — enables news + real-time quotes
- **Reddit** (optional): Create app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — enables social sentiment
- **yfinance**: No key needed — works immediately for price data
- **GDELT**: No key needed — works immediately for geopolitical data

## Project Structure

```
stock-prediction/
├── main.py                          # CLI entry point
├── config/
│   └── settings.py                  # API keys, weights, defaults
├── src/
│   ├── data_sources/
│   │   ├── stock_prices.py          # yfinance + Finnhub
│   │   ├── news_sentiment.py        # Finnhub news + FinBERT
│   │   ├── geopolitical.py          # GDELT events
│   │   └── social_media.py          # Reddit PRAW
│   └── analysis/
│       └── predictor.py             # Signal combiner + prediction
├── requirements.txt
├── .env.example
└── README.md
```

## Disclaimer

This tool is for **educational purposes only**. Do not make investment decisions based solely on this tool. Stock markets are inherently unpredictable, and past performance does not guarantee future results.
