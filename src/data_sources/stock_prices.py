"""
Stock price data fetcher using yfinance (historical) and Finnhub (real-time).

Data sources:
- yfinance: Free, no API key needed. Best for historical data & bulk downloads.
- Finnhub: Free tier (60 req/min). Best for real-time quotes & supplementary data.
"""

import pandas as pd
import yfinance as yf
import finnhub
from datetime import datetime, timedelta

from config.settings import FINNHUB_API_KEY


def get_historical_prices(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Fetch historical price data from Yahoo Finance.

    Args:
        symbol: Stock ticker (e.g., "AAPL", "TSLA")
        period: Time period - 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume, plus calculated indicators
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)

    if df.empty:
        return df

    # Add technical indicators
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    df["EMA_12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA_26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # RSI (Relative Strength Index)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df["BB_Middle"] = df["Close"].rolling(window=20).mean()
    bb_std = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = df["BB_Middle"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Middle"] - (bb_std * 2)

    # Volatility (20-day rolling standard deviation of returns)
    df["Daily_Return"] = df["Close"].pct_change()
    df["Volatility"] = df["Daily_Return"].rolling(window=20).std()

    return df


def get_realtime_quote(symbol: str) -> dict:
    """Fetch real-time quote from Finnhub.

    Args:
        symbol: Stock ticker

    Returns:
        Dict with current price, change, percent change, high, low, open, previous close
    """
    if not FINNHUB_API_KEY:
        return _fallback_quote(symbol)

    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    quote = client.quote(symbol)

    return {
        "symbol": symbol,
        "current_price": quote.get("c", 0),
        "change": quote.get("d", 0),
        "percent_change": quote.get("dp", 0),
        "high": quote.get("h", 0),
        "low": quote.get("l", 0),
        "open": quote.get("o", 0),
        "previous_close": quote.get("pc", 0),
        "timestamp": datetime.now().isoformat(),
    }


def _fallback_quote(symbol: str) -> dict:
    """Fallback to yfinance if Finnhub key not available."""
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    history = ticker.history(period="2d")

    if history.empty:
        return {"symbol": symbol, "error": "No data available"}

    current = history["Close"].iloc[-1]
    previous = history["Close"].iloc[-2] if len(history) > 1 else current

    return {
        "symbol": symbol,
        "current_price": round(current, 2),
        "change": round(current - previous, 2),
        "percent_change": round(((current - previous) / previous) * 100, 2),
        "high": round(history["High"].iloc[-1], 2),
        "low": round(history["Low"].iloc[-1], 2),
        "open": round(history["Open"].iloc[-1], 2),
        "previous_close": round(previous, 2),
        "timestamp": datetime.now().isoformat(),
    }


def get_technical_signal(symbol: str) -> dict:
    """Analyze technical indicators and return a buy/sell/hold signal.

    Returns:
        Dict with signal (bullish/bearish/neutral), strength (0-1), and reasoning
    """
    df = get_historical_prices(symbol, period="3mo")
    if df.empty or len(df) < 50:
        return {"signal": "neutral", "strength": 0.5, "reasons": ["Insufficient data"]}

    latest = df.iloc[-1]
    reasons = []
    score = 0  # -1 to +1 scale

    # MACD signal
    if latest["MACD"] > latest["Signal_Line"]:
        score += 0.2
        reasons.append("MACD bullish crossover")
    else:
        score -= 0.2
        reasons.append("MACD bearish crossover")

    # RSI signal
    if latest["RSI"] < 30:
        score += 0.25
        reasons.append(f"RSI oversold ({latest['RSI']:.1f})")
    elif latest["RSI"] > 70:
        score -= 0.25
        reasons.append(f"RSI overbought ({latest['RSI']:.1f})")
    else:
        reasons.append(f"RSI neutral ({latest['RSI']:.1f})")

    # Moving average trend
    if latest["SMA_20"] > latest["SMA_50"]:
        score += 0.2
        reasons.append("Short-term MA above long-term (uptrend)")
    else:
        score -= 0.2
        reasons.append("Short-term MA below long-term (downtrend)")

    # Bollinger Band position
    if latest["Close"] < latest["BB_Lower"]:
        score += 0.2
        reasons.append("Price below lower Bollinger Band (potential bounce)")
    elif latest["Close"] > latest["BB_Upper"]:
        score -= 0.2
        reasons.append("Price above upper Bollinger Band (potential pullback)")

    # Price momentum (5-day)
    if len(df) >= 5:
        momentum = (latest["Close"] - df["Close"].iloc[-5]) / df["Close"].iloc[-5]
        if momentum > 0.03:
            score += 0.15
            reasons.append(f"Strong 5-day momentum (+{momentum*100:.1f}%)")
        elif momentum < -0.03:
            score -= 0.15
            reasons.append(f"Weak 5-day momentum ({momentum*100:.1f}%)")

    # Convert score to signal
    strength = (score + 1) / 2  # Normalize to 0-1
    if score > 0.15:
        signal = "bullish"
    elif score < -0.15:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "score": round(score, 3),
        "reasons": reasons,
    }
