"""
Order book / market depth data.

Tier 1 (personal use): ib_insync → IB Gateway running locally on port 7497
  - Full Level 2 order book (multiple bid/ask price levels)
  - Real-time, requires Interactive Brokers account + IB Gateway desktop app

Tier 2 (fallback): yfinance
  - Level 1 only: best bid/ask + sizes from ticker.info
  - ~15 min delayed, no depth

The source actually used is returned in the `source` field of every response
so the UI can clearly label what the user is looking at.
"""

import yfinance as yf

# ── IB connection (lazy, module-level singleton) ───────────────────────────────

_ib = None
_ib_available = None   # None = not yet tested, True/False after first attempt


def _get_ib():
    """Return a connected IB instance, or None if IB Gateway is not reachable."""
    global _ib, _ib_available

    # Already confirmed unavailable this session
    if _ib_available is False:
        return None

    # Already connected and still alive
    if _ib is not None and _ib.isConnected():
        return _ib

    try:
        from ib_insync import IB
        ib = IB()
        ib.connect('127.0.0.1', 7497, clientId=10, timeout=3, readonly=True)
        _ib = ib
        _ib_available = True
        return ib
    except Exception:
        _ib_available = False
        _ib = None
        return None


def ib_status() -> dict:
    """Return whether IB Gateway is connected. Safe to call any time."""
    ib = _get_ib()
    if ib and ib.isConnected():
        return {"connected": True, "source": "IB Gateway (Level 2)"}
    return {"connected": False, "source": "yfinance (Level 1 fallback)"}


# ── Symbol conversion ─────────────────────────────────────────────────────────

def _to_ib_contract(symbol: str):
    """Convert a yfinance-style ticker to an IB Contract object."""
    from ib_insync import Stock, Index

    if symbol == "^KLSE":
        return Index("KLCI", "KLSE", "MYR")

    if symbol.endswith(".KL"):
        code = symbol[:-3]
        return Stock(code, "KLSE", "MYR")

    # US stock
    return Stock(symbol, "SMART", "USD")


# ── Level 2 via IB ────────────────────────────────────────────────────────────

def _fetch_ib_order_book(symbol: str, depth: int = 10) -> dict:
    """Fetch full order book from IB Gateway. Returns None if not available."""
    ib = _get_ib()
    if not ib:
        return None

    try:
        contract = _to_ib_contract(symbol)
        ib.qualifyContracts(contract)

        ticker = ib.reqMktDepth(contract, numRows=depth)
        ib.sleep(1.5)   # wait for data to arrive

        bids = []
        asks = []
        for row in ticker.domBids:
            if row.price and row.size:
                bids.append({"price": round(row.price, 4), "size": int(row.size)})
        for row in ticker.domAsks:
            if row.price and row.size:
                asks.append({"price": round(row.price, 4), "size": int(row.size)})

        ib.cancelMktDepth(contract)

        if not bids and not asks:
            return None

        # Sort correctly: bids descending (highest first), asks ascending (lowest first)
        bids.sort(key=lambda x: x["price"], reverse=True)
        asks.sort(key=lambda x: x["price"])

        best_bid = bids[0]["price"] if bids else None
        best_ask = asks[0]["price"] if asks else None
        spread    = round(best_ask - best_bid, 4) if (best_bid and best_ask) else None
        spread_pct = round(spread / best_bid * 100, 3) if (spread and best_bid) else None

        total_bid_vol = sum(b["size"] for b in bids)
        total_ask_vol = sum(a["size"] for a in asks)
        pressure = round(total_bid_vol / (total_bid_vol + total_ask_vol) * 100, 1) \
            if (total_bid_vol + total_ask_vol) else 50.0

        return {
            "source":       "IB Gateway (Level 2)",
            "level":        2,
            "symbol":       symbol,
            "bids":         bids[:depth],
            "asks":         asks[:depth],
            "best_bid":     best_bid,
            "best_ask":     best_ask,
            "spread":       spread,
            "spread_pct":   spread_pct,
            "total_bid_vol": total_bid_vol,
            "total_ask_vol": total_ask_vol,
            "pressure":     pressure,   # >50 = more buying pressure, <50 = selling pressure
        }
    except Exception:
        return None


# ── Level 1 via yfinance (fallback) ──────────────────────────────────────────

def _fetch_yf_order_book(symbol: str) -> dict:
    """Fetch best bid/ask from yfinance. Always available, Level 1 only."""
    try:
        info = yf.Ticker(symbol).info
        bid      = info.get("bid")
        ask      = info.get("ask")
        bid_size = info.get("bidSize")
        ask_size = info.get("askSize")

        if not bid or not ask:
            return {"source": "yfinance (Level 1)", "level": 1, "symbol": symbol,
                    "error": "No bid/ask data available for this symbol"}

        spread     = round(ask - bid, 4)
        spread_pct = round(spread / bid * 100, 3) if bid else None

        total_bid_vol = (bid_size or 0) * 100   # yfinance returns lots
        total_ask_vol = (ask_size or 0) * 100
        pressure = round(total_bid_vol / (total_bid_vol + total_ask_vol) * 100, 1) \
            if (total_bid_vol + total_ask_vol) else 50.0

        return {
            "source":       "yfinance (Level 1 — best bid/ask only)",
            "level":        1,
            "symbol":       symbol,
            "bids":         [{"price": bid, "size": total_bid_vol}] if bid else [],
            "asks":         [{"price": ask, "size": total_ask_vol}] if ask else [],
            "best_bid":     bid,
            "best_ask":     ask,
            "spread":       spread,
            "spread_pct":   spread_pct,
            "total_bid_vol": total_bid_vol,
            "total_ask_vol": total_ask_vol,
            "pressure":     pressure,
        }
    except Exception as e:
        return {"source": "yfinance (Level 1)", "level": 1, "symbol": symbol,
                "error": str(e)}


# ── Public entry point ────────────────────────────────────────────────────────

def get_order_book(symbol: str, depth: int = 10) -> dict:
    """
    Get order book data. Tries IB Gateway first, falls back to yfinance.
    Always returns a dict — never raises.
    """
    # Try IB first
    result = _fetch_ib_order_book(symbol, depth)
    if result:
        return result

    # Fall back to yfinance Level 1
    return _fetch_yf_order_book(symbol)
