"""
Insider trading data — tracks insider buy/sell transactions from SEC filings.

Data source:
- Finnhub: stock_insider_transactions() for historical insider trades
- US stocks only (SEC filings)

Signal logic:
- High insider buying → bullish (insiders know more than the market)
- High insider selling → mildly bearish (could be routine)
- Cluster of insider buys → strong bullish
"""

import finnhub
from datetime import datetime, timedelta

from config.settings import FINNHUB_API_KEY


def _get_client():
    if not FINNHUB_API_KEY:
        return None
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def fetch_insider_transactions(symbol: str, months_back: int = 12) -> list[dict]:
    """Fetch insider transactions for a stock.

    Returns list of dicts with: symbol, filing_date, insider_name,
    transaction_type, shares, value, shares_total.
    """
    client = _get_client()
    if not client:
        return []

    try:
        start = (datetime.now() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        raw = client.stock_insider_transactions(symbol, _from=start, to=end)
        data = raw.get("data", [])
        if not data:
            return []

        results = []
        for item in data:
            tx_code = item.get("transactionCode", "")
            if not tx_code:
                continue

            results.append({
                "symbol": symbol,
                "filing_date": item.get("filingDate", "") or item.get("transactionDate", ""),
                "insider_name": item.get("name", ""),
                "transaction_type": tx_code,  # "P" = Purchase, "S" = Sale
                "shares": item.get("share", 0),
                "value": item.get("change", 0),
                "shares_total": 0,
            })

        return results
    except Exception:
        return []


def _is_buy_transaction(tx_type: str) -> bool:
    """Check if a transaction type indicates a buy/purchase."""
    t = tx_type.upper().strip()
    # Finnhub uses codes like "P-Purchase", "P - Purchase"
    return t.startswith("P") or "BUY" in t or "PURCHASE" in t or "ACQUISITION" in t


def _is_sell_transaction(tx_type: str) -> bool:
    """Check if a transaction type indicates a sell/disposal."""
    t = tx_type.upper().strip()
    # Finnhub uses codes like "S-Sale", "S - Sale"
    return t.startswith("S") or "SELL" in t or "SALE" in t or "DISPOSAL" in t


def get_insider_signal(symbol: str) -> dict:
    """Generate a trading signal based on insider activity.

    Looks at last 90 days of insider transactions.
    """
    if symbol.upper().endswith(".KL"):
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["Insider data not available for Bursa Malaysia stocks"],
            "has_data": False,
        }

    if not FINNHUB_API_KEY:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["FINNHUB_API_KEY not set"],
            "has_data": False,
        }

    transactions = fetch_insider_transactions(symbol, months_back=3)
    if not transactions:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": ["No recent insider transactions"],
            "has_data": False,
        }

    buys = [t for t in transactions if _is_buy_transaction(t.get("transaction_type", ""))]
    sells = [t for t in transactions if _is_sell_transaction(t.get("transaction_type", ""))]

    total = len(buys) + len(sells)
    if total == 0:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "reasons": [f"{len(transactions)} transactions (no clear buy/sell)"],
            "has_data": True,
        }

    buy_ratio = len(buys) / total
    reasons = [f"Insider activity: {len(buys)} buys, {len(sells)} sells (90 days)"]

    if buy_ratio > 0.6:
        signal = "bullish"
        strength = 0.5 + (buy_ratio - 0.5) * 0.8
        reasons.append(f"Buy ratio {buy_ratio:.0%} — insiders accumulating")
    elif buy_ratio < 0.3:
        signal = "bearish"
        strength = 0.5 - (0.5 - buy_ratio) * 0.6
        reasons.append(f"Buy ratio {buy_ratio:.0%} — insiders selling")
    else:
        signal = "neutral"
        strength = 0.5

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "buy_ratio": round(buy_ratio, 3),
        "total_transactions": total,
        "reasons": reasons,
        "has_data": True,
    }
