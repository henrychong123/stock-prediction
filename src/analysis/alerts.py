"""
Alerts system for price thresholds and signal changes.

Stores alert rules in the database and checks them against live data.
"""

from datetime import datetime
from src.database import get_connection


def _ensure_alerts_table():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL,
            message TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_triggered INTEGER NOT NULL DEFAULT 0,
            triggered_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()


_ensure_alerts_table()


def create_alert(symbol: str, alert_type: str, condition: str,
                 threshold: float, message: str = "") -> dict:
    """Create a new alert.

    Args:
        symbol: Stock ticker
        alert_type: "price", "rsi", "signal_change"
        condition: "above", "below", "crosses_above", "crosses_below"
        threshold: Value to trigger on
        message: Custom alert message

    Returns:
        Created alert dict
    """
    conn = get_connection()
    conn.execute(
        """INSERT INTO alerts (symbol, alert_type, condition, threshold, message)
           VALUES (?, ?, ?, ?, ?)""",
        (symbol, alert_type, condition, threshold, message)
    )
    conn.commit()
    aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": aid, "symbol": symbol, "alert_type": alert_type,
            "condition": condition, "threshold": threshold}


def get_alerts(active_only: bool = True) -> list[dict]:
    """Get all alerts."""
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE is_active = 1 ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_alerts() -> list[dict]:
    """Check all active alerts against current data.

    Returns:
        List of triggered alerts
    """
    from src.data_sources.stock_prices import get_realtime_quote, get_historical_prices

    alerts = get_alerts(active_only=True)
    triggered = []

    for alert in alerts:
        try:
            symbol = alert["symbol"]
            alert_type = alert["alert_type"]
            condition = alert["condition"]
            threshold = alert["threshold"]

            if alert_type == "price":
                quote = get_realtime_quote(symbol)
                current = quote.get("current_price", 0)

                hit = False
                if condition == "above" and current > threshold:
                    hit = True
                elif condition == "below" and current < threshold:
                    hit = True

                if hit:
                    alert["current_value"] = current
                    alert["triggered_at"] = datetime.now().isoformat()
                    triggered.append(alert)
                    _mark_triggered(alert["id"])

            elif alert_type == "rsi":
                df = get_historical_prices(symbol, period="1mo")
                if not df.empty:
                    rsi = df["RSI"].iloc[-1]
                    hit = False
                    if condition == "below" and rsi < threshold:
                        hit = True
                    elif condition == "above" and rsi > threshold:
                        hit = True

                    if hit:
                        alert["current_value"] = round(rsi, 2)
                        alert["triggered_at"] = datetime.now().isoformat()
                        triggered.append(alert)
                        _mark_triggered(alert["id"])

        except Exception:
            continue

    return triggered


def _mark_triggered(alert_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE alerts SET is_triggered = 1, triggered_at = datetime('now') WHERE id = ?",
        (alert_id,)
    )
    conn.commit()
    conn.close()


def delete_alert(alert_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()


def reset_alert(alert_id: int):
    """Reset a triggered alert back to active."""
    conn = get_connection()
    conn.execute(
        "UPDATE alerts SET is_triggered = 0, triggered_at = NULL WHERE id = ?",
        (alert_id,)
    )
    conn.commit()
    conn.close()
