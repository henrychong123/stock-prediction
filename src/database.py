"""
SQLite database for storing prediction history, news, and signal trends.

Uses built-in sqlite3 (no extra dependencies). Stores:
- Predictions: every prediction result with all signal scores
- News: aggregated news from all platforms with sentiment
- Sector snapshots: periodic sector analysis results
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "predictions.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence REAL NOT NULL,
            price REAL,
            score REAL,
            signals_json TEXT,
            reasons_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_platform TEXT NOT NULL,
            headline TEXT NOT NULL,
            summary TEXT,
            url TEXT,
            source_name TEXT,
            sentiment_label TEXT,
            sentiment_score REAL,
            related_symbol TEXT,
            related_figure TEXT,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sector_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_name TEXT NOT NULL,
            etf TEXT,
            action TEXT NOT NULL,
            confidence REAL,
            score REAL,
            signal_breakdown_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
        CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);
        CREATE INDEX IF NOT EXISTS idx_news_platform ON news(source_platform);
        CREATE INDEX IF NOT EXISTS idx_news_fetched ON news(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_sector_created ON sector_snapshots(created_at);
    """)
    conn.close()


# ===== PREDICTIONS =====

def save_prediction(symbol: str, action: str, confidence: float, price: float,
                    score: float, signals: dict, reasons: list):
    conn = get_connection()
    conn.execute(
        """INSERT INTO predictions (symbol, action, confidence, price, score, signals_json, reasons_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, action, confidence, price, score,
         json.dumps(signals), json.dumps(reasons))
    )
    conn.commit()
    conn.close()


def get_prediction_history(symbol: str, limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM predictions WHERE symbol = ?
           ORDER BY created_at DESC LIMIT ?""",
        (symbol, limit)
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r["signals"] = json.loads(r.pop("signals_json", "{}"))
        r["reasons"] = json.loads(r.pop("reasons_json", "[]"))
        results.append(r)
    return results


def get_all_prediction_history(limit: int = 500) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prediction_trend(symbol: str, days: int = 30) -> list[dict]:
    """Get prediction score trend over time for a symbol."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT created_at, action, confidence, price, score
           FROM predictions WHERE symbol = ?
           AND created_at >= datetime('now', ?)
           ORDER BY created_at ASC""",
        (symbol, f"-{days} days")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== NEWS =====

def save_news(platform: str, headline: str, summary: str = "", url: str = "",
              source_name: str = "", sentiment_label: str = "",
              sentiment_score: float = 0, related_symbol: str = "",
              related_figure: str = ""):
    conn = get_connection()
    # Avoid duplicates by checking headline
    existing = conn.execute(
        "SELECT id FROM news WHERE headline = ? AND source_platform = ?",
        (headline, platform)
    ).fetchone()
    if existing:
        conn.close()
        return

    conn.execute(
        """INSERT INTO news (source_platform, headline, summary, url, source_name,
           sentiment_label, sentiment_score, related_symbol, related_figure)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (platform, headline, summary, url, source_name,
         sentiment_label, sentiment_score, related_symbol, related_figure)
    )
    conn.commit()
    conn.close()


def get_all_news(limit: int = 200, platform: str = None) -> list[dict]:
    conn = get_connection()
    if platform:
        rows = conn.execute(
            """SELECT * FROM news WHERE source_platform = ?
               ORDER BY fetched_at DESC LIMIT ?""",
            (platform, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM news ORDER BY fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_news_stats() -> dict:
    """Get counts by platform and sentiment breakdown."""
    conn = get_connection()
    platform_counts = conn.execute(
        "SELECT source_platform, COUNT(*) as cnt FROM news GROUP BY source_platform"
    ).fetchall()
    sentiment_counts = conn.execute(
        "SELECT sentiment_label, COUNT(*) as cnt FROM news GROUP BY sentiment_label"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) as cnt FROM news").fetchone()["cnt"]
    conn.close()

    return {
        "total": total,
        "by_platform": {r["source_platform"]: r["cnt"] for r in platform_counts},
        "by_sentiment": {r["sentiment_label"]: r["cnt"] for r in sentiment_counts},
    }


# ===== SECTORS =====

def save_sector_snapshot(sector_name: str, etf: str, action: str,
                         confidence: float, score: float, signal_breakdown: dict):
    conn = get_connection()
    conn.execute(
        """INSERT INTO sector_snapshots (sector_name, etf, action, confidence, score, signal_breakdown_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sector_name, etf, action, confidence, score, json.dumps(signal_breakdown))
    )
    conn.commit()
    conn.close()


def get_sector_history(sector_name: str = None, limit: int = 100) -> list[dict]:
    conn = get_connection()
    if sector_name:
        rows = conn.execute(
            """SELECT * FROM sector_snapshots WHERE sector_name = ?
               ORDER BY created_at DESC LIMIT ?""",
            (sector_name, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sector_snapshots ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r["signal_breakdown"] = json.loads(r.pop("signal_breakdown_json", "{}"))
        results.append(r)
    return results


# Initialize on import
init_db()
