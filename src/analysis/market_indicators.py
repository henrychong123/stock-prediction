"""
Market-wide indicators: Fear & Greed Index, correlation matrix, earnings calendar.

These provide the "big picture" context that individual stock analysis misses.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.data_sources.stock_prices import get_historical_prices


# ===== FEAR & GREED INDEX =====
# Composite score (0-100) based on 5 market indicators:
#   1. Market momentum (S&P 500 vs 125-day MA)
#   2. Market volatility (VIX level)
#   3. Market breadth (advancing vs declining stocks proxy)
#   4. Safe haven demand (bonds vs stocks ratio)
#   5. RSI of S&P 500

def calculate_fear_greed(market: str = "US") -> dict:
    """Calculate a Fear & Greed index (0=Extreme Fear, 100=Extreme Greed).

    Args:
        market: "US" or "MY"

    Returns:
        Dict with overall score, label, and component breakdowns
    """
    if market == "MY":
        index_sym = "^KLSE"
        vol_sym = None  # No VIX equivalent for Malaysia
        bond_sym = None
    else:
        index_sym = "SPY"
        vol_sym = "VXX"
        bond_sym = "TLT"

    components = {}

    # 1. Market Momentum (index vs 125-day MA)
    try:
        df = get_historical_prices(index_sym, period="1y")
        if not df.empty and len(df) > 125:
            ma_125 = df["Close"].rolling(125).mean().iloc[-1]
            current = df["Close"].iloc[-1]
            momentum = ((current - ma_125) / ma_125) * 100
            # Map to 0-100: -10% = 0, +10% = 100
            momentum_score = max(0, min(100, (momentum + 10) * 5))
            components["momentum"] = {
                "score": round(momentum_score),
                "value": round(momentum, 2),
                "label": "Market Momentum",
                "detail": f"{'Above' if momentum > 0 else 'Below'} 125-day MA by {abs(momentum):.1f}%",
            }
    except Exception:
        pass

    # 2. Volatility (VIX level - lower = more greedy)
    if vol_sym:
        try:
            vdf = get_historical_prices(vol_sym, period="3mo")
            if not vdf.empty:
                vix = vdf["Close"].iloc[-1]
                # VIX < 15 = greed (100), VIX > 35 = fear (0)
                vol_score = max(0, min(100, (35 - vix) / 20 * 100))
                components["volatility"] = {
                    "score": round(vol_score),
                    "value": round(vix, 2),
                    "label": "Volatility (VIX)",
                    "detail": f"VIX at {vix:.1f}",
                }
        except Exception:
            pass

    # 3. RSI of the index
    try:
        df = get_historical_prices(index_sym, period="3mo")
        if not df.empty:
            rsi = df["RSI"].iloc[-1]
            # RSI 30 = fear (0), RSI 70 = greed (100)
            rsi_score = max(0, min(100, (rsi - 30) / 40 * 100))
            components["rsi"] = {
                "score": round(rsi_score),
                "value": round(rsi, 1),
                "label": "Market RSI",
                "detail": f"RSI at {rsi:.1f}",
            }
    except Exception:
        pass

    # 4. Safe Haven Demand (stocks vs bonds)
    if bond_sym:
        try:
            sdf = get_historical_prices(index_sym, period="3mo")
            bdf = get_historical_prices(bond_sym, period="3mo")
            if not sdf.empty and not bdf.empty:
                stock_ret = (sdf["Close"].iloc[-1] - sdf["Close"].iloc[-20]) / sdf["Close"].iloc[-20]
                bond_ret = (bdf["Close"].iloc[-1] - bdf["Close"].iloc[-20]) / bdf["Close"].iloc[-20]
                spread = (stock_ret - bond_ret) * 100
                # Spread > 5% = greed, < -5% = fear
                haven_score = max(0, min(100, (spread + 5) * 10))
                components["safe_haven"] = {
                    "score": round(haven_score),
                    "value": round(spread, 2),
                    "label": "Safe Haven Demand",
                    "detail": f"Stocks vs Bonds: {spread:+.1f}%",
                }
        except Exception:
            pass

    # 5. Market Breadth (20-day price trend)
    try:
        df = get_historical_prices(index_sym, period="3mo")
        if not df.empty and len(df) > 20:
            recent_returns = df["Daily_Return"].iloc[-20:]
            up_days = (recent_returns > 0).sum()
            breadth_ratio = up_days / 20
            breadth_score = breadth_ratio * 100
            components["breadth"] = {
                "score": round(breadth_score),
                "value": round(breadth_ratio, 2),
                "label": "Market Breadth",
                "detail": f"{up_days}/20 up days",
            }
    except Exception:
        pass

    # Calculate overall score
    if components:
        scores = [c["score"] for c in components.values()]
        overall = round(sum(scores) / len(scores))
    else:
        overall = 50

    # Label
    if overall >= 75:
        label = "Extreme Greed"
    elif overall >= 55:
        label = "Greed"
    elif overall >= 45:
        label = "Neutral"
    elif overall >= 25:
        label = "Fear"
    else:
        label = "Extreme Fear"

    return {
        "score": overall,
        "label": label,
        "market": market,
        "components": components,
        "timestamp": datetime.now().isoformat(),
    }


# ===== CORRELATION MATRIX =====

def calculate_correlations(symbols: list[str], period: str = "6mo") -> dict:
    """Calculate price correlation matrix between multiple assets.

    Helps identify diversification opportunities and correlated risks.

    Args:
        symbols: List of stock tickers
        period: Time period for correlation calculation

    Returns:
        Dict with correlation matrix and interpretation
    """
    prices = {}
    for sym in symbols:
        try:
            df = get_historical_prices(sym, period=period)
            if not df.empty:
                prices[sym] = df["Close"]
        except Exception:
            continue

    if len(prices) < 2:
        return {"error": "Need at least 2 symbols with data"}

    # Align dates and create returns DataFrame
    price_df = pd.DataFrame(prices)
    price_df = price_df.dropna()
    returns_df = price_df.pct_change().dropna()

    if returns_df.empty:
        return {"error": "No overlapping data"}

    # Correlation matrix
    corr = returns_df.corr()

    # Convert to serializable format
    matrix = {}
    for sym1 in corr.columns:
        matrix[sym1] = {}
        for sym2 in corr.columns:
            matrix[sym1][sym2] = round(corr.loc[sym1, sym2], 3)

    # Find notable correlations
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            val = corr.iloc[i, j]
            pairs.append({
                "pair": f"{cols[i]} / {cols[j]}",
                "correlation": round(val, 3),
                "strength": "Strong" if abs(val) > 0.7 else "Moderate" if abs(val) > 0.4 else "Weak",
                "direction": "Positive" if val > 0 else "Negative",
            })

    pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    return {
        "matrix": matrix,
        "symbols": list(corr.columns),
        "notable_pairs": pairs[:10],
        "period": period,
        "data_points": len(returns_df),
    }


# ===== EARNINGS CALENDAR =====

def get_earnings_calendar(symbols: list[str]) -> list[dict]:
    """Get upcoming earnings dates for a list of stocks.

    Uses yfinance to fetch earnings dates from company calendars.

    Args:
        symbols: List of stock tickers

    Returns:
        List of earnings events sorted by date
    """
    import yfinance as yf

    events = []
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                # yfinance calendar returns a DataFrame or dict
                if isinstance(cal, pd.DataFrame):
                    for col in cal.columns:
                        if "earnings" in col.lower() or "date" in col.lower():
                            date_val = cal[col].iloc[0] if len(cal) > 0 else None
                            if date_val:
                                events.append({
                                    "symbol": sym,
                                    "event": "Earnings",
                                    "date": str(date_val),
                                })
                elif isinstance(cal, dict):
                    for key, val in cal.items():
                        if "earnings" in str(key).lower():
                            events.append({
                                "symbol": sym,
                                "event": "Earnings",
                                "date": str(val),
                            })
            # Also check earnings_dates
            try:
                edates = ticker.earnings_dates
                if edates is not None and not edates.empty:
                    for date_idx in edates.index[:2]:  # Next 2 dates
                        events.append({
                            "symbol": sym,
                            "event": "Earnings",
                            "date": str(date_idx.date()) if hasattr(date_idx, 'date') else str(date_idx),
                            "estimate": edates.loc[date_idx].get("Earnings Estimate", None),
                        })
            except Exception:
                pass
        except Exception:
            continue

    # Deduplicate and sort by date
    seen = set()
    unique = []
    for e in events:
        key = f"{e['symbol']}_{e['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(e)

    unique.sort(key=lambda x: x.get("date", ""))
    return unique
