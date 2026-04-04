"""
Virtual portfolio tracker with P&L tracking.

Track paper trades based on predictions, calculate returns,
and compare against buy-and-hold strategy.
"""

import json
from datetime import datetime

from src.database import get_connection, init_db


def _ensure_portfolio_tables():
    """Create portfolio tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            initial_capital REAL NOT NULL DEFAULT 10000,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            total_value REAL NOT NULL,
            signal_action TEXT,
            signal_confidence REAL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0,
            UNIQUE(portfolio_id, symbol),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
        );
    """)
    conn.close()


_ensure_portfolio_tables()


def create_portfolio(name: str, capital: float = 10000) -> dict:
    """Create a new virtual portfolio."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO portfolios (name, initial_capital) VALUES (?, ?)",
            (name, capital)
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"id": pid, "name": name, "capital": capital}
    except Exception as e:
        conn.close()
        return {"error": str(e)}


def get_portfolio(name: str = "default") -> dict:
    """Get or create a portfolio by name."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM portfolios WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        return create_portfolio(name)
    conn.close()
    return dict(row)


def execute_trade(
    portfolio_name: str, symbol: str, action: str,
    quantity: float, price: float,
    signal_action: str = "", signal_confidence: float = 0,
    notes: str = ""
) -> dict:
    """Execute a virtual trade (BUY or SELL)."""
    portfolio = get_portfolio(portfolio_name)
    if "error" in portfolio:
        return portfolio

    pid = portfolio["id"]
    total = quantity * price
    conn = get_connection()

    # Record trade
    conn.execute(
        """INSERT INTO trades (portfolio_id, symbol, action, quantity, price,
           total_value, signal_action, signal_confidence, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, symbol, action, quantity, price, total,
         signal_action, signal_confidence, notes)
    )

    # Update holdings
    holding = conn.execute(
        "SELECT * FROM holdings WHERE portfolio_id = ? AND symbol = ?",
        (pid, symbol)
    ).fetchone()

    if action == "BUY":
        if holding:
            old_qty = holding["quantity"]
            old_cost = holding["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_cost) + (quantity * price)) / new_qty
            conn.execute(
                "UPDATE holdings SET quantity = ?, avg_cost = ? WHERE id = ?",
                (new_qty, new_avg, holding["id"])
            )
        else:
            conn.execute(
                "INSERT INTO holdings (portfolio_id, symbol, quantity, avg_cost) VALUES (?, ?, ?, ?)",
                (pid, symbol, quantity, price)
            )
    elif action == "SELL":
        if holding and holding["quantity"] >= quantity:
            new_qty = holding["quantity"] - quantity
            if new_qty == 0:
                conn.execute("DELETE FROM holdings WHERE id = ?", (holding["id"],))
            else:
                conn.execute(
                    "UPDATE holdings SET quantity = ? WHERE id = ?",
                    (new_qty, holding["id"])
                )
        else:
            conn.close()
            return {"error": f"Insufficient holdings to sell {quantity} of {symbol}"}

    conn.commit()
    conn.close()
    return {"success": True, "action": action, "symbol": symbol, "quantity": quantity, "price": price}


def get_holdings(portfolio_name: str = "default") -> list[dict]:
    """Get current holdings with current market values."""
    from src.data_sources.stock_prices import get_realtime_quote

    portfolio = get_portfolio(portfolio_name)
    if "error" in portfolio:
        return []

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM holdings WHERE portfolio_id = ?", (portfolio["id"],)
    ).fetchall()
    conn.close()

    holdings = []
    for row in rows:
        h = dict(row)
        try:
            quote = get_realtime_quote(h["symbol"])
            current_price = quote.get("current_price", h["avg_cost"])
        except Exception:
            current_price = h["avg_cost"]

        h["current_price"] = current_price
        h["market_value"] = round(h["quantity"] * current_price, 2)
        h["cost_basis"] = round(h["quantity"] * h["avg_cost"], 2)
        h["pnl"] = round(h["market_value"] - h["cost_basis"], 2)
        h["pnl_pct"] = round(
            ((current_price - h["avg_cost"]) / h["avg_cost"]) * 100, 2
        ) if h["avg_cost"] > 0 else 0
        holdings.append(h)

    return holdings


def get_portfolio_summary(portfolio_name: str = "default") -> dict:
    """Get full portfolio summary with P&L."""
    portfolio = get_portfolio(portfolio_name)
    if "error" in portfolio:
        return portfolio

    holdings = get_holdings(portfolio_name)
    total_value = sum(h["market_value"] for h in holdings)
    total_cost = sum(h["cost_basis"] for h in holdings)
    total_pnl = total_value - total_cost
    initial = portfolio.get("initial_capital", 10000)

    conn = get_connection()
    trade_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM trades WHERE portfolio_id = ?",
        (portfolio["id"],)
    ).fetchone()["cnt"]
    conn.close()

    return {
        "portfolio": portfolio["name"],
        "initial_capital": initial,
        "total_invested": round(total_cost, 2),
        "current_value": round(total_value, 2),
        "cash_remaining": round(initial - total_cost, 2),
        "total_value_with_cash": round((initial - total_cost) + total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else 0,
        "overall_return_pct": round(
            (((initial - total_cost) + total_value - initial) / initial) * 100, 2
        ),
        "holdings_count": len(holdings),
        "trade_count": trade_count,
        "holdings": holdings,
    }


def get_trade_history(portfolio_name: str = "default", limit: int = 100) -> list[dict]:
    """Get trade history for a portfolio."""
    portfolio = get_portfolio(portfolio_name)
    if "error" in portfolio:
        return []

    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM trades WHERE portfolio_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (portfolio["id"], limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
