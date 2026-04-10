"""
Earnings data and signal — tracks EPS/revenue surprises and upcoming earnings dates.

Data source:
- Finnhub: company_earnings() for historical EPS, earnings_calendar() for upcoming dates
- US stocks only (Finnhub doesn't cover Bursa Malaysia)

Signal logic:
- Recent earnings beat with high surprise % → bullish
- Recent earnings miss → bearish
- Upcoming earnings within 5 days → flag high volatility
- No data / MY stocks → neutral
"""

import finnhub
from datetime import datetime, timedelta

from config.settings import FINNHUB_API_KEY


def _get_client():
    if not FINNHUB_API_KEY:
        return None
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def fetch_company_earnings(symbol: str, limit: int = 8) -> list[dict]:
    """Fetch historical quarterly EPS data for a stock.

    Returns list of dicts with: period, actual, estimate, surprise, surprisePct, date
    Sorted by date descending (most recent first).
    """
    client = _get_client()
    if not client:
        return [{"error": "FINNHUB_API_KEY not set"}]

    try:
        raw = client.company_earnings(symbol, limit=limit)
        if not raw:
            return []

        results = []
        for item in raw:
            actual = item.get("actual")
            estimate = item.get("estimate")
            surprise_pct = None
            if actual is not None and estimate is not None and estimate != 0:
                surprise_pct = round((actual - estimate) / abs(estimate) * 100, 2)

            results.append({
                "symbol": symbol,
                "period": item.get("period", ""),
                "date": item.get("period", ""),
                "eps_actual": actual,
                "eps_estimate": estimate,
                "surprise": item.get("surprise"),
                "surprise_pct": surprise_pct,
            })

        return results
    except Exception:
        return []


def fetch_earnings_calendar(symbol: str = None, days_ahead: int = 30) -> list[dict]:
    """Fetch upcoming earnings dates.

    Args:
        symbol: Specific stock, or None for market-wide calendar
        days_ahead: How many days ahead to look

    Returns list of dicts with: symbol, date, epsEstimate, revenueEstimate, etc.
    """
    client = _get_client()
    if not client:
        return [{"error": "FINNHUB_API_KEY not set"}]

    try:
        start = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        raw = client.earnings_calendar(
            _from=start, to=end,
            symbol=symbol if symbol else None,
            international=False,
        )

        events = raw.get("earningsCalendar", [])
        results = []
        for item in events:
            results.append({
                "symbol": item.get("symbol", ""),
                "date": item.get("date", ""),
                "eps_estimate": item.get("epsEstimate"),
                "eps_actual": item.get("epsActual"),
                "revenue_estimate": item.get("revenueEstimate"),
                "revenue_actual": item.get("revenueActual"),
                "hour": item.get("hour", ""),  # "bmo" (before market open), "amc" (after market close)
                "quarter": item.get("quarter"),
                "year": item.get("year"),
            })

        return results
    except Exception:
        return []


def get_earnings_signal(symbol: str) -> dict:
    """Generate a trading signal based on earnings data.

    Combines:
    1. Most recent earnings surprise (beat/miss)
    2. Historical beat rate (last 4 quarters)
    3. Proximity to next earnings date

    Returns standard signal dict.
    """
    # Malaysian stocks — no Finnhub coverage
    if symbol.upper().endswith(".KL") or symbol.upper().startswith("^KL"):
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["Earnings data not available for Bursa Malaysia stocks"],
            "has_data": False,
        }

    if not FINNHUB_API_KEY:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["FINNHUB_API_KEY not set"],
            "has_data": False,
        }

    # Fetch historical earnings
    history = fetch_company_earnings(symbol, limit=4)
    if not history or (history and "error" in history[0]):
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["No earnings data available"],
            "has_data": False,
        }

    # Analyze recent earnings
    valid = [e for e in history if e.get("eps_actual") is not None and e.get("eps_estimate") is not None]
    if not valid:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["No EPS actual/estimate data"],
            "has_data": False,
        }

    # Most recent quarter
    latest = valid[0]
    latest_surprise = latest.get("surprise_pct", 0) or 0

    # Beat rate (last 4 quarters)
    beats = sum(1 for e in valid if (e.get("surprise_pct") or 0) > 0)
    beat_rate = beats / len(valid)

    # Build reasons
    reasons = []
    if latest_surprise > 0:
        reasons.append(f"Beat EPS by {latest_surprise:+.1f}% ({latest['period']})")
    elif latest_surprise < 0:
        reasons.append(f"Missed EPS by {latest_surprise:+.1f}% ({latest['period']})")
    else:
        reasons.append(f"Met EPS estimates ({latest['period']})")

    reasons.append(f"Beat rate: {beats}/{len(valid)} quarters ({beat_rate:.0%})")

    # Check upcoming earnings
    upcoming = fetch_earnings_calendar(symbol, days_ahead=14)
    days_to_next = None
    if upcoming and "error" not in upcoming[0]:
        for event in upcoming:
            if event.get("symbol", "").upper() == symbol.upper():
                try:
                    event_date = datetime.strptime(event["date"], "%Y-%m-%d")
                    days_to_next = (event_date - datetime.now()).days
                    if days_to_next >= 0:
                        reasons.append(f"Earnings in {days_to_next} days ({event.get('hour', '')})")
                        break
                except (ValueError, KeyError):
                    pass

    # Compute signal strength
    # Base: surprise % normalized (clip to ±50%)
    surprise_score = max(min(latest_surprise / 50, 1), -1)  # -1 to +1

    # Beat rate bonus: consistent beaters get a boost
    beat_bonus = (beat_rate - 0.5) * 0.4  # -0.2 to +0.2

    # Combine
    raw_score = surprise_score * 0.7 + beat_bonus * 0.3
    strength = (raw_score + 1) / 2  # normalize to 0-1

    # Volatility warning if earnings imminent
    if days_to_next is not None and days_to_next <= 3:
        reasons.append("HIGH VOLATILITY — earnings imminent")

    # Determine signal direction
    if raw_score > 0.15:
        signal = "bullish"
    elif raw_score < -0.15:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "latest_surprise_pct": latest_surprise,
        "beat_rate": round(beat_rate, 2),
        "quarters_analyzed": len(valid),
        "days_to_next_earnings": days_to_next,
        "reasons": reasons,
        "has_data": True,
    }
