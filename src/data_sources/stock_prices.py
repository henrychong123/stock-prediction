"""
Stock price data fetcher using yfinance (historical) and Finnhub (real-time).

Data sources:
- yfinance: Free, no API key needed. Best for historical data & bulk downloads.
- Finnhub: Free tier (60 req/min). Best for real-time quotes & supplementary data.
"""

import pandas as pd
import numpy as np
import yfinance as yf
import finnhub
from datetime import datetime, timedelta

from config.settings import FINNHUB_API_KEY


def get_historical_prices(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Fetch historical price data from Yahoo Finance with full indicator suite.

    Args:
        symbol: Stock ticker (e.g., "AAPL", "TSLA")
        period: Time period - 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max

    Returns:
        DataFrame with OHLCV + 25+ calculated indicator columns
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)

    if df.empty:
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # ── Moving Averages ───────────────────────────────────────────────────
    df["SMA_20"] = close.rolling(window=20).mean()
    df["SMA_50"] = close.rolling(window=50).mean()
    df["EMA_9"] = close.ewm(span=9, adjust=False).mean()
    df["EMA_12"] = close.ewm(span=12, adjust=False).mean()
    df["EMA_21"] = close.ewm(span=21, adjust=False).mean()
    df["EMA_26"] = close.ewm(span=26, adjust=False).mean()

    # ── MACD ──────────────────────────────────────────────────────────────
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["Signal_Line"]

    # ── RSI (14-period) ───────────────────────────────────────────────────
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # ── Bollinger Bands ───────────────────────────────────────────────────
    df["BB_Middle"] = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    df["BB_Upper"] = df["BB_Middle"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Middle"] - (bb_std * 2)

    # ── Volatility ────────────────────────────────────────────────────────
    df["Daily_Return"] = close.pct_change()
    df["Volatility"] = df["Daily_Return"].rolling(window=20).std()

    # ── Stochastic Oscillator (14-period) ─────────────────────────────────
    low_14 = low.rolling(window=14).min()
    high_14 = high.rolling(window=14).max()
    df["Stoch_K"] = ((close - low_14) / (high_14 - low_14)) * 100
    df["Stoch_D"] = df["Stoch_K"].rolling(window=3).mean()

    # ── Williams %R (14-period) ───────────────────────────────────────────
    df["Williams_R"] = ((high_14 - close) / (high_14 - low_14)) * -100

    # ── ATR (Average True Range, 14-period) ───────────────────────────────
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = true_range.rolling(window=14).mean()

    # ── ADX (Average Directional Index, 14-period) ────────────────────────
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    atr_14 = true_range.ewm(span=14, adjust=False).mean()
    df["Plus_DI"] = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / atr_14)
    df["Minus_DI"] = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr_14)

    di_sum = df["Plus_DI"] + df["Minus_DI"]
    di_sum = di_sum.replace(0, np.nan)
    dx = 100 * ((df["Plus_DI"] - df["Minus_DI"]).abs() / di_sum)
    df["ADX"] = dx.ewm(span=14, adjust=False).mean()

    # ── OBV (On-Balance Volume) ───────────────────────────────────────────
    obv = [0]
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.append(obv[-1] + volume.iloc[i])
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.append(obv[-1] - volume.iloc[i])
        else:
            obv.append(obv[-1])
    df["OBV"] = obv

    # ── VWAP (Volume Weighted Average Price) ──────────────────────────────
    typical_price = (high + low + close) / 3
    cum_tp_vol = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum()
    df["VWAP"] = cum_tp_vol / cum_vol

    # ── CCI (Commodity Channel Index, 20-period) ─────────────────────────
    tp = (high + low + close) / 3
    tp_sma = tp.rolling(window=20).mean()
    tp_mad = tp.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df["CCI"] = (tp - tp_sma) / (0.015 * tp_mad)

    # ── Parabolic SAR ─────────────────────────────────────────────────────
    df["PSAR"] = _calculate_psar(high, low, close)

    # ── Ichimoku Cloud ────────────────────────────────────────────────────
    df["Ichi_Tenkan"] = (high.rolling(window=9).max() + low.rolling(window=9).min()) / 2
    df["Ichi_Kijun"] = (high.rolling(window=26).max() + low.rolling(window=26).min()) / 2
    df["Ichi_SpanA"] = ((df["Ichi_Tenkan"] + df["Ichi_Kijun"]) / 2).shift(26)
    df["Ichi_SpanB"] = ((high.rolling(window=52).max() + low.rolling(window=52).min()) / 2).shift(26)

    return df


def _calculate_psar(high: pd.Series, low: pd.Series, close: pd.Series,
                    af_start=0.02, af_step=0.02, af_max=0.2) -> pd.Series:
    """Calculate Parabolic SAR using the standard Wilder method."""
    n = len(close)
    psar = close.copy()
    bull = True
    af = af_start
    ep = low.iloc[0]
    hp = high.iloc[0]
    lp = low.iloc[0]

    for i in range(2, n):
        if bull:
            psar.iloc[i] = psar.iloc[i - 1] + af * (hp - psar.iloc[i - 1])
            psar.iloc[i] = min(psar.iloc[i], low.iloc[i - 1], low.iloc[i - 2])

            if low.iloc[i] < psar.iloc[i]:
                bull = False
                psar.iloc[i] = hp
                lp = low.iloc[i]
                af = af_start
            else:
                if high.iloc[i] > hp:
                    hp = high.iloc[i]
                    af = min(af + af_step, af_max)
        else:
            psar.iloc[i] = psar.iloc[i - 1] + af * (lp - psar.iloc[i - 1])
            psar.iloc[i] = max(psar.iloc[i], high.iloc[i - 1], high.iloc[i - 2])

            if high.iloc[i] > psar.iloc[i]:
                bull = True
                psar.iloc[i] = lp
                hp = high.iloc[i]
                af = af_start
            else:
                if low.iloc[i] < lp:
                    lp = low.iloc[i]
                    af = min(af + af_step, af_max)

    return psar


def get_fibonacci_levels(df: pd.DataFrame) -> dict:
    """Calculate Fibonacci retracement levels from period high/low."""
    if df.empty:
        return {}
    period_high = float(df["High"].max())
    period_low = float(df["Low"].min())
    diff = period_high - period_low
    return {
        "high": round(period_high, 4),
        "low": round(period_low, 4),
        "level_236": round(period_high - 0.236 * diff, 4),
        "level_382": round(period_high - 0.382 * diff, 4),
        "level_500": round(period_high - 0.500 * diff, 4),
        "level_618": round(period_high - 0.618 * diff, 4),
        "level_786": round(period_high - 0.786 * diff, 4),
    }


def get_realtime_quote(symbol: str) -> dict:
    """Fetch real-time quote from Finnhub.

    Args:
        symbol: Stock ticker

    Returns:
        Dict with current price, change, percent change, high, low, open, previous close
    """
    if not FINNHUB_API_KEY:
        return _fallback_quote(symbol)

    try:
        client = finnhub.Client(api_key=FINNHUB_API_KEY)
        quote = client.quote(symbol)
        if not quote.get("c"):
            return _fallback_quote(symbol)
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
    except Exception:
        return _fallback_quote(symbol)


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
    """Analyze all technical indicators and return a buy/sell/hold signal.

    Uses 11 indicators across momentum, trend, volume, and volatility.
    Returns:
        Dict with signal (bullish/bearish/neutral), strength (0-1), and reasoning
    """
    df = get_historical_prices(symbol, period="3mo")
    if df.empty or len(df) < 50:
        return {"signal": "neutral", "strength": 0.5, "reasons": ["Insufficient data"]}

    latest = df.iloc[-1]
    reasons = []
    score = 0  # -1 to +1 scale

    # ── MACD ──────────────────────────────────────────────────────────────
    if latest["MACD"] > latest["Signal_Line"]:
        score += 0.2
        reasons.append("MACD bullish crossover")
    else:
        score -= 0.2
        reasons.append("MACD bearish crossover")

    # ── RSI ───────────────────────────────────────────────────────────────
    rsi = latest["RSI"]
    if rsi < 30:
        score += 0.25
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > 70:
        score -= 0.25
        reasons.append(f"RSI overbought ({rsi:.1f})")
    else:
        reasons.append(f"RSI neutral ({rsi:.1f})")

    # ── SMA Cross ─────────────────────────────────────────────────────────
    if latest["SMA_20"] > latest["SMA_50"]:
        score += 0.2
        reasons.append("Short-term MA above long-term (uptrend)")
    else:
        score -= 0.2
        reasons.append("Short-term MA below long-term (downtrend)")

    # ── Bollinger Bands ───────────────────────────────────────────────────
    if latest["Close"] < latest["BB_Lower"]:
        score += 0.2
        reasons.append("Price below lower Bollinger Band (potential bounce)")
    elif latest["Close"] > latest["BB_Upper"]:
        score -= 0.2
        reasons.append("Price above upper Bollinger Band (potential pullback)")

    # ── 5-day Momentum ────────────────────────────────────────────────────
    if len(df) >= 5:
        momentum = (latest["Close"] - df["Close"].iloc[-5]) / df["Close"].iloc[-5]
        if momentum > 0.03:
            score += 0.15
            reasons.append(f"Strong 5-day momentum (+{momentum*100:.1f}%)")
        elif momentum < -0.03:
            score -= 0.15
            reasons.append(f"Weak 5-day momentum ({momentum*100:.1f}%)")

    # ── Stochastic Oscillator ─────────────────────────────────────────────
    stoch_k = latest.get("Stoch_K")
    if stoch_k is not None and not pd.isna(stoch_k):
        if stoch_k < 20:
            score += 0.15
            reasons.append(f"Stochastic oversold (%K={stoch_k:.1f})")
        elif stoch_k > 80:
            score -= 0.15
            reasons.append(f"Stochastic overbought (%K={stoch_k:.1f})")

    # ── Williams %R ───────────────────────────────────────────────────────
    wr = latest.get("Williams_R")
    if wr is not None and not pd.isna(wr):
        if wr < -80:
            score += 0.1
            reasons.append(f"Williams %R oversold ({wr:.1f})")
        elif wr > -20:
            score -= 0.1
            reasons.append(f"Williams %R overbought ({wr:.1f})")

    # ── CCI ───────────────────────────────────────────────────────────────
    cci = latest.get("CCI")
    if cci is not None and not pd.isna(cci):
        if cci < -100:
            score += 0.1
            reasons.append(f"CCI oversold ({cci:.0f})")
        elif cci > 100:
            score -= 0.1
            reasons.append(f"CCI overbought ({cci:.0f})")

    # ── OBV Divergence ────────────────────────────────────────────────────
    if len(df) >= 10:
        price_dir = latest["Close"] - df["Close"].iloc[-10]
        obv_dir = latest["OBV"] - df["OBV"].iloc[-10]
        if price_dir < 0 and obv_dir > 0:
            score += 0.1
            reasons.append("OBV bullish divergence (volume accumulating)")
        elif price_dir > 0 and obv_dir < 0:
            score -= 0.1
            reasons.append("OBV bearish divergence (volume declining)")

    # ── Ichimoku Cloud ────────────────────────────────────────────────────
    span_a = latest.get("Ichi_SpanA")
    span_b = latest.get("Ichi_SpanB")
    if span_a is not None and span_b is not None and not pd.isna(span_a) and not pd.isna(span_b):
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        if latest["Close"] > cloud_top:
            score += 0.2
            reasons.append("Price above Ichimoku cloud (bullish)")
        elif latest["Close"] < cloud_bot:
            score -= 0.2
            reasons.append("Price below Ichimoku cloud (bearish)")
        else:
            reasons.append("Price inside Ichimoku cloud (indecisive)")

    # ── ADX Trend Strength ────────────────────────────────────────────────
    adx = latest.get("ADX")
    if adx is not None and not pd.isna(adx) and adx > 25:
        score *= 1.3  # amplify signal when trend is strong
        reasons.append(f"ADX {adx:.0f} — strong trend confirms direction")
    elif adx is not None and not pd.isna(adx):
        reasons.append(f"ADX {adx:.0f} — weak trend")

    # Clamp score to [-1, 1]
    score = max(-1.0, min(1.0, score))

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
