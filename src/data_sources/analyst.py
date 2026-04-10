"""
Analyst consensus data — tracks buy/hold/sell recommendations over time.

Data source:
- Finnhub: recommendation_trends() for monthly analyst consensus
- US stocks only

Signal logic:
- Strong consensus buy → bullish
- Strong consensus sell → bearish
- Upgrades/downgrades from prior month → momentum signal
"""

import finnhub
from config.settings import FINNHUB_API_KEY


def _get_client():
    if not FINNHUB_API_KEY:
        return None
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def fetch_recommendation_trends(symbol: str) -> list[dict]:
    """Fetch analyst recommendation trends (monthly snapshots).

    Returns list of dicts with: symbol, date, strong_buy, buy, hold, sell, strong_sell.
    Sorted by date descending (most recent first).
    """
    client = _get_client()
    if not client:
        return []

    try:
        raw = client.recommendation_trends(symbol)
        if not raw:
            return []

        results = []
        for item in raw:
            results.append({
                "symbol": symbol,
                "date": item.get("period", ""),
                "strong_buy": item.get("strongBuy", 0),
                "buy": item.get("buy", 0),
                "hold": item.get("hold", 0),
                "sell": item.get("sell", 0),
                "strong_sell": item.get("strongSell", 0),
            })

        return results
    except Exception:
        return []


def get_analyst_signal(symbol: str) -> dict:
    """Generate a trading signal based on analyst consensus.

    Combines current consensus score with momentum (change from prior month).
    """
    if symbol.upper().endswith(".KL"):
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["Analyst data not available for Bursa Malaysia stocks"],
            "has_data": False,
        }

    if not FINNHUB_API_KEY:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["FINNHUB_API_KEY not set"],
            "has_data": False,
        }

    trends = fetch_recommendation_trends(symbol)
    if not trends:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["No analyst data available"],
            "has_data": False,
        }

    latest = trends[0]
    sb = latest.get("strong_buy", 0) or 0
    b = latest.get("buy", 0) or 0
    h = latest.get("hold", 0) or 0
    s = latest.get("sell", 0) or 0
    ss = latest.get("strong_sell", 0) or 0
    total = sb + b + h + s + ss

    if total == 0:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["No analyst ratings"],
            "has_data": False,
        }

    # Score: -1 (all strong sell) to +1 (all strong buy)
    score = (sb * 2 + b * 1 + h * 0 - s * 1 - ss * 2) / (total * 2)

    reasons = [f"Analysts: {sb} strong buy, {b} buy, {h} hold, {s} sell, {ss} strong sell"]

    # Check for momentum (upgrade/downgrade vs prior month)
    if len(trends) >= 2:
        prev = trends[1]
        prev_total = sum(prev.get(k, 0) or 0 for k in ["strong_buy", "buy", "hold", "sell", "strong_sell"])
        if prev_total > 0:
            prev_score = (
                (prev.get("strong_buy", 0) or 0) * 2 +
                (prev.get("buy", 0) or 0) * 1 -
                (prev.get("sell", 0) or 0) * 1 -
                (prev.get("strong_sell", 0) or 0) * 2
            ) / (prev_total * 2)
            delta = score - prev_score
            if delta > 0.05:
                reasons.append(f"Upgrade trend: score improved by {delta:+.2f}")
            elif delta < -0.05:
                reasons.append(f"Downgrade trend: score declined by {delta:+.2f}")

    # Map score to signal
    if score > 0.2:
        signal = "bullish"
        strength = 0.5 + score * 0.5
    elif score < -0.2:
        signal = "bearish"
        strength = 0.5 + score * 0.5  # score is negative, so strength < 0.5
    else:
        signal = "neutral"
        strength = 0.5

    return {
        "signal": signal,
        "strength": round(max(0, min(1, strength)), 3),
        "analyst_score": round(score, 3),
        "total_analysts": total,
        "reasons": reasons,
        "has_data": True,
    }
