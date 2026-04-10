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
    conn.execute("PRAGMA busy_timeout=10000")
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

        CREATE TABLE IF NOT EXISTS price_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            price       REAL NOT NULL,
            prev_close  REAL,
            change_abs  REAL,
            change_pct  REAL,
            volume      INTEGER,
            bid         REAL,
            ask         REAL,
            day_high    REAL,
            day_low     REAL,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS news_tracker_state (
            source      TEXT PRIMARY KEY,
            last_fetched TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL UNIQUE,
            name        TEXT DEFAULT '',
            note        TEXT DEFAULT '',
            alert_above REAL,
            alert_below REAL,
            added_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS training_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            date        TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            sma_20 REAL, sma_50 REAL, ema_9 REAL, ema_12 REAL, ema_21 REAL, ema_26 REAL,
            macd REAL, signal_line REAL, macd_hist REAL,
            rsi REAL, stoch_k REAL, stoch_d REAL, williams_r REAL,
            bb_upper REAL, bb_lower REAL,
            adx REAL, plus_di REAL, minus_di REAL,
            atr REAL, obv REAL, vwap REAL, cci REAL, psar REAL,
            ichi_tenkan REAL, ichi_kijun REAL, ichi_span_a REAL, ichi_span_b REAL,
            volatility REAL, daily_return REAL,
            market_index_close REAL,
            vix_close REAL,
            price_change_1d REAL,
            price_change_5d REAL,
            UNIQUE(symbol, date)
        );

        CREATE TABLE IF NOT EXISTS gdelt_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            industry    TEXT NOT NULL,
            avg_tone    REAL,
            article_count INTEGER,
            keywords    TEXT,
            UNIQUE(date, industry)
        );

        CREATE TABLE IF NOT EXISTS daily_features (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            date        TEXT NOT NULL,
            news_sentiment REAL,
            news_count     INTEGER,
            news_top_headline TEXT,
            reddit_sentiment REAL,
            reddit_count     INTEGER,
            figure_sentiment REAL,
            figure_count     INTEGER,
            figure_top       TEXT,
            gdelt_tone       REAL,
            fear_greed       REAL,
            collected_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(symbol, date)
        );

        CREATE TABLE IF NOT EXISTS earnings_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            date            TEXT NOT NULL,
            period          TEXT,
            eps_actual      REAL,
            eps_estimate    REAL,
            surprise_pct    REAL,
            revenue_actual  REAL,
            revenue_estimate REAL,
            revenue_surprise_pct REAL,
            UNIQUE(symbol, date)
        );

        CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_history(symbol);
        CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_history(date);

        CREATE TABLE IF NOT EXISTS classification_cache (
            headline_hash TEXT PRIMARY KEY,
            industry     TEXT NOT NULL,
            method       TEXT DEFAULT 'keyword',
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS insider_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            filing_date     TEXT NOT NULL,
            insider_name    TEXT,
            transaction_type TEXT,
            shares          REAL,
            value           REAL,
            shares_total    REAL,
            UNIQUE(symbol, filing_date, insider_name, transaction_type)
        );

        CREATE TABLE IF NOT EXISTS analyst_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            date            TEXT NOT NULL,
            strong_buy      INTEGER DEFAULT 0,
            buy             INTEGER DEFAULT 0,
            hold            INTEGER DEFAULT 0,
            sell            INTEGER DEFAULT 0,
            strong_sell     INTEGER DEFAULT 0,
            UNIQUE(symbol, date)
        );

        CREATE TABLE IF NOT EXISTS catalyst_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id         TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            event_label     TEXT NOT NULL,
            headline        TEXT NOT NULL,
            sentiment       REAL,
            confidence      REAL,
            affected_json   TEXT,
            picks_json      TEXT,
            scanned_at      TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at      TEXT,
            UNIQUE(scan_id, event_type)
        );

        CREATE INDEX IF NOT EXISTS idx_catalyst_scanned ON catalyst_alerts(scanned_at);

        CREATE TABLE IF NOT EXISTS catalyst_outcomes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id        INTEGER REFERENCES catalyst_alerts(id),
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            predicted_move  REAL,
            actual_move_24h REAL,
            entry_price     REAL,
            exit_price      REAL,
            is_correct      INTEGER,
            measured_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stock_knowledge (
            symbol          TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            market          TEXT DEFAULT 'MY',
            business_desc   TEXT,
            parent_company  TEXT,
            subsidiaries    TEXT,
            related_stocks  TEXT,
            suppliers       TEXT,
            customers       TEXT,
            commodity_exposure TEXT,
            sector          TEXT,
            knowledge_json  TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_insider_symbol ON insider_history(symbol);
        CREATE INDEX IF NOT EXISTS idx_insider_date ON insider_history(filing_date);
        CREATE INDEX IF NOT EXISTS idx_analyst_symbol ON analyst_history(symbol);
        CREATE INDEX IF NOT EXISTS idx_analyst_date ON analyst_history(date);

        CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
        CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);
        CREATE INDEX IF NOT EXISTS idx_news_platform ON news(source_platform);
        CREATE INDEX IF NOT EXISTS idx_news_fetched ON news(fetched_at);
        CREATE INDEX IF NOT EXISTS idx_sector_created ON sector_snapshots(created_at);
        CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_time ON price_snapshots(symbol, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_gdelt_date ON gdelt_history(date);
        CREATE INDEX IF NOT EXISTS idx_training_symbol_date ON training_data(symbol, date);
        CREATE INDEX IF NOT EXISTS idx_daily_features_symbol_date ON daily_features(symbol, date);
    """)

    # Migration: add new training_data columns for macro/cross-asset features
    for col in ["treasury_10y", "treasury_2y", "yield_spread", "dxy_close",
                 "sector_etf_return", "oil_close", "gold_close", "copper_close"]:
        try:
            conn.execute(f"ALTER TABLE training_data ADD COLUMN {col} REAL")
        except Exception:
            pass  # Column already exists

    # Migration: rename old industry names in gdelt_history to canonical names
    try:
        from config.industries import INDUSTRY_NAME_MIGRATION
        for old_name, new_name in INDUSTRY_NAME_MIGRATION.items():
            conn.execute(
                "UPDATE gdelt_history SET industry = ? WHERE industry = ?",
                (new_name, old_name)
            )
        conn.commit()
    except Exception:
        pass

    # Migration: deduplicate news then add UNIQUE index
    try:
        conn.execute("""
            DELETE FROM news WHERE id NOT IN (
                SELECT MIN(id) FROM news GROUP BY headline, source_platform
            )
        """)
        conn.commit()
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_news_dedup
            ON news(headline, source_platform)
        """)
        conn.commit()
    except Exception:
        pass

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
    if not headline:
        return
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO news
           (source_platform, headline, summary, url, source_name,
            sentiment_label, sentiment_score, related_symbol, related_figure)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (platform, headline, summary, url, source_name,
         sentiment_label, sentiment_score, related_symbol, related_figure)
    )
    conn.commit()
    conn.close()


def get_all_news(limit: int = 500, platform: str = None,
                 hours_back: int = None) -> list[dict]:
    conn = get_connection()
    clauses = []
    params: list = []
    if platform:
        clauses.append("source_platform = ?")
        params.append(platform)
    if hours_back:
        clauses.append("fetched_at >= datetime('now', ?)")
        params.append(f"-{hours_back} hours")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM news {where} ORDER BY fetched_at DESC LIMIT ?", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_news_latest_fetched() -> str | None:
    """Return ISO timestamp of the most recently fetched news article."""
    conn = get_connection()
    row = conn.execute(
        "SELECT fetched_at FROM news ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["fetched_at"] if row else None


def update_news_article_text(news_id: int, article_text: str):
    """Update the summary field with full article text."""
    import time
    for attempt in range(3):
        try:
            conn = get_connection()
            conn.execute("UPDATE news SET summary = ? WHERE id = ?", (article_text[:5000], news_id))
            conn.commit()
            conn.close()
            return
        except Exception:
            time.sleep(2)
    # Final attempt without retry
    conn = get_connection()
    conn.execute("UPDATE news SET summary = ? WHERE id = ?", (article_text[:5000], news_id))
    conn.commit()
    conn.close()


def get_news_without_article_text(limit: int = 50) -> list[dict]:
    """Get recent news articles that have a URL but no article text."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, headline, url FROM news
           WHERE url IS NOT NULL AND url != ''
           AND (summary IS NULL OR summary = '' OR LENGTH(summary) < 100)
           ORDER BY fetched_at DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── News tracker state (tracks last API poll time per source) ─────────────────

def get_tracker_last_fetched(source: str) -> datetime | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT last_fetched FROM news_tracker_state WHERE source = ?", (source,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return datetime.fromisoformat(row["last_fetched"])
        except ValueError:
            return None
    return None


def set_tracker_last_fetched(source: str):
    conn = get_connection()
    conn.execute(
        """INSERT INTO news_tracker_state (source, last_fetched)
           VALUES (?, datetime('now'))
           ON CONFLICT(source) DO UPDATE SET last_fetched = datetime('now')""",
        (source,)
    )
    conn.commit()
    conn.close()


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


# ===== PRICE SNAPSHOTS =====

def save_price_snapshot(symbol: str, price: float, prev_close: float = None,
                        change_abs: float = None, change_pct: float = None,
                        volume: int = None, bid: float = None, ask: float = None,
                        day_high: float = None, day_low: float = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO price_snapshots
           (symbol, price, prev_close, change_abs, change_pct, volume, bid, ask, day_high, day_low)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, price, prev_close, change_abs, change_pct,
         volume, bid, ask, day_high, day_low)
    )
    conn.commit()
    conn.close()


def get_price_history(symbol: str, hours: int = 24) -> list[dict]:
    """Return all snapshots for a symbol within the last N hours."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM price_snapshots
           WHERE symbol = ? AND recorded_at >= datetime('now', 'localtime', ?)
           ORDER BY recorded_at ASC""",
        (symbol, f"-{hours} hours")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_snapshot(symbol: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM price_snapshots WHERE symbol = ? ORDER BY recorded_at DESC LIMIT 1",
        (symbol,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_tracked_symbols() -> list[str]:
    """All symbols that have at least one price snapshot."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM price_snapshots ORDER BY symbol"
    ).fetchall()
    conn.close()
    return [r["symbol"] for r in rows]


def get_prediction_accuracy(limit: int = 100) -> dict:
    """
    Join predictions against price_snapshots to measure accuracy.

    For each prediction, finds:
    - entry_price: snapshot closest to prediction's created_at
    - current_price: most recent snapshot for that symbol
    - actual_return_pct: (current - entry) / entry * 100
    - outcome: CORRECT if prediction direction matches actual direction
    """
    conn = get_connection()

    rows = conn.execute(
        """SELECT p.id, p.symbol, p.action, p.confidence, p.price AS pred_price,
                  p.score, p.created_at,
                  snap_entry.price AS entry_snap_price,
                  snap_entry.recorded_at AS entry_snap_at,
                  snap_latest.price AS latest_price,
                  snap_latest.recorded_at AS latest_snap_at
           FROM predictions p
           LEFT JOIN price_snapshots snap_entry ON snap_entry.symbol = p.symbol
               AND snap_entry.recorded_at = (
                   SELECT recorded_at FROM price_snapshots
                   WHERE symbol = p.symbol
                   AND recorded_at >= p.created_at
                   ORDER BY recorded_at ASC LIMIT 1
               )
           LEFT JOIN price_snapshots snap_latest ON snap_latest.symbol = p.symbol
               AND snap_latest.recorded_at = (
                   SELECT MAX(recorded_at) FROM price_snapshots WHERE symbol = p.symbol
               )
           ORDER BY p.created_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()

    results = []
    correct = 0
    total_with_data = 0

    for row in rows:
        r = dict(row)
        entry_price = r.get("entry_snap_price") or r.get("pred_price")
        latest_price = r.get("latest_price")

        actual_return = None
        outcome = "pending"

        if entry_price and latest_price and entry_price > 0:
            actual_return = round((latest_price - entry_price) / entry_price * 100, 2)
            action = (r.get("action") or "").upper()
            is_bullish_pred = any(w in action for w in ("BUY", "BULL"))
            is_bearish_pred = any(w in action for w in ("SELL", "BEAR"))

            if is_bullish_pred:
                outcome = "correct" if actual_return > 0 else "wrong"
            elif is_bearish_pred:
                outcome = "correct" if actual_return < 0 else "wrong"
            else:
                outcome = "correct" if abs(actual_return) < 2 else "wrong"

            total_with_data += 1
            if outcome == "correct":
                correct += 1

        r["entry_price"] = entry_price
        r["latest_price"] = latest_price
        r["actual_return_pct"] = actual_return
        r["outcome"] = outcome
        results.append(r)

    accuracy_pct = round(correct / total_with_data * 100, 1) if total_with_data > 0 else None
    return {
        "predictions": results,
        "summary": {
            "total": len(results),
            "with_data": total_with_data,
            "correct": correct,
            "accuracy_pct": accuracy_pct,
        }
    }


# ===== WATCHLIST =====

def get_watchlist() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM watchlist ORDER BY added_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_watchlist(symbol: str, name: str = '', note: str = '',
                     alert_above: float = None, alert_below: float = None) -> bool:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO watchlist (symbol, name, note, alert_above, alert_below)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol, name, note, alert_above, alert_below)
        )
        conn.commit()
        inserted = conn.total_changes > 0
    except Exception:
        inserted = False
    conn.close()
    return inserted


def remove_from_watchlist(symbol: str) -> bool:
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    conn.commit()
    deleted = conn.total_changes > 0
    conn.close()
    return deleted


def update_watchlist_item(symbol: str, note: str = None,
                          alert_above: float = None, alert_below: float = None) -> bool:
    conn = get_connection()
    fields, vals = [], []
    if note is not None:
        fields.append("note = ?"); vals.append(note)
    if alert_above is not None:
        fields.append("alert_above = ?"); vals.append(alert_above if alert_above > 0 else None)
    if alert_below is not None:
        fields.append("alert_below = ?"); vals.append(alert_below if alert_below > 0 else None)
    if not fields:
        conn.close()
        return False
    vals.append(symbol)
    conn.execute(f"UPDATE watchlist SET {', '.join(fields)} WHERE symbol = ?", vals)
    conn.commit()
    updated = conn.total_changes > 0
    conn.close()
    return updated


def is_in_watchlist(symbol: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM watchlist WHERE symbol = ?", (symbol,)).fetchone()
    conn.close()
    return row is not None


# ===== GDELT HISTORY =====

def save_gdelt_history_batch(rows: list[dict]):
    """Bulk insert GDELT historical tone data."""
    if not rows:
        return
    conn = get_connection()
    conn.executemany(
        "INSERT OR REPLACE INTO gdelt_history (date, industry, avg_tone, article_count, keywords) VALUES (?, ?, ?, ?, ?)",
        [(r["date"], r["industry"], r.get("avg_tone"), r.get("article_count"), r.get("keywords", "")) for r in rows],
    )
    conn.commit()
    conn.close()


def get_gdelt_tone_for_date(date: str, industry: str = None) -> dict:
    """Get GDELT tone data for a date, optionally filtered by industry."""
    conn = get_connection()
    if industry:
        rows = conn.execute(
            "SELECT * FROM gdelt_history WHERE date = ? AND industry = ?", (date, industry)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM gdelt_history WHERE date = ?", (date,)).fetchall()
    conn.close()
    return {r["industry"]: {"avg_tone": r["avg_tone"], "article_count": r["article_count"]} for r in rows}


# ===== LATEST PREDICTIONS =====

def get_latest_predictions(symbols: list[str] = None) -> dict:
    """Get the most recent prediction for each symbol.
    Returns dict keyed by symbol: {action, confidence, score, price, created_at}
    """
    conn = get_connection()
    query = """
        SELECT p.symbol, p.action, p.confidence, p.score, p.price, p.created_at
        FROM predictions p
        INNER JOIN (
            SELECT symbol, MAX(created_at) as max_date
            FROM predictions
            GROUP BY symbol
        ) latest ON p.symbol = latest.symbol AND p.created_at = latest.max_date
    """
    if symbols:
        placeholders = ",".join(["?"] * len(symbols))
        query += f" WHERE p.symbol IN ({placeholders})"
        rows = conn.execute(query, symbols).fetchall()
    else:
        rows = conn.execute(query).fetchall()
    conn.close()

    result = {}
    for r in rows:
        result[r["symbol"]] = {
            "action": r["action"],
            "confidence": r["confidence"],
            "score": r["score"],
            "price": r["price"],
            "created_at": r["created_at"],
        }
    return result


# ===== TRAINING DATA =====

def save_training_row(row: dict):
    """Insert or replace one row of training data."""
    conn = get_connection()
    cols = [
        "symbol", "date", "open", "high", "low", "close", "volume",
        "sma_20", "sma_50", "ema_9", "ema_12", "ema_21", "ema_26",
        "macd", "signal_line", "macd_hist",
        "rsi", "stoch_k", "stoch_d", "williams_r",
        "bb_upper", "bb_lower",
        "adx", "plus_di", "minus_di",
        "atr", "obv", "vwap", "cci", "psar",
        "ichi_tenkan", "ichi_kijun", "ichi_span_a", "ichi_span_b",
        "volatility", "daily_return",
        "market_index_close", "vix_close",
        "price_change_1d", "price_change_5d",
        "treasury_10y", "treasury_2y", "yield_spread",
        "dxy_close", "sector_etf_return",
        "oil_close", "gold_close", "copper_close",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    vals = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT OR REPLACE INTO training_data ({col_names}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    conn.close()


def save_training_batch(rows: list[dict]):
    """Bulk insert training data rows."""
    if not rows:
        return
    conn = get_connection()
    cols = [
        "symbol", "date", "open", "high", "low", "close", "volume",
        "sma_20", "sma_50", "ema_9", "ema_12", "ema_21", "ema_26",
        "macd", "signal_line", "macd_hist",
        "rsi", "stoch_k", "stoch_d", "williams_r",
        "bb_upper", "bb_lower",
        "adx", "plus_di", "minus_di",
        "atr", "obv", "vwap", "cci", "psar",
        "ichi_tenkan", "ichi_kijun", "ichi_span_a", "ichi_span_b",
        "volatility", "daily_return",
        "market_index_close", "vix_close",
        "price_change_1d", "price_change_5d",
        "treasury_10y", "treasury_2y", "yield_spread",
        "dxy_close", "sector_etf_return",
        "oil_close", "gold_close", "copper_close",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    data = [[row.get(c) for c in cols] for row in rows]
    conn.executemany(
        f"INSERT OR REPLACE INTO training_data ({col_names}) VALUES ({placeholders})",
        data,
    )
    conn.commit()
    conn.close()


def get_training_data(symbol: str = None) -> list[dict]:
    conn = get_connection()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM training_data WHERE symbol = ? ORDER BY date", (symbol,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM training_data ORDER BY symbol, date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_training_symbols() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT symbol FROM training_data ORDER BY symbol").fetchall()
    conn.close()
    return [r["symbol"] for r in rows]


# ===== DAILY FEATURES =====

def save_daily_features(row: dict):
    conn = get_connection()
    cols = [
        "symbol", "date", "news_sentiment", "news_count", "news_top_headline",
        "reddit_sentiment", "reddit_count",
        "figure_sentiment", "figure_count", "figure_top",
        "gdelt_tone", "fear_greed",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    vals = [row.get(c) for c in cols]
    conn.execute(
        f"INSERT OR REPLACE INTO daily_features ({col_names}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    conn.close()


def get_daily_features(symbol: str = None) -> list[dict]:
    conn = get_connection()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM daily_features WHERE symbol = ? ORDER BY date", (symbol,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM daily_features ORDER BY symbol, date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== EARNINGS HISTORY =====

def save_earnings_batch(rows: list[dict]):
    """Bulk insert earnings history records."""
    if not rows:
        return
    conn = get_connection()
    conn.executemany(
        """INSERT OR REPLACE INTO earnings_history
           (symbol, date, period, eps_actual, eps_estimate, surprise_pct,
            revenue_actual, revenue_estimate, revenue_surprise_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(r.get("symbol"), r.get("date"), r.get("period"),
          r.get("eps_actual"), r.get("eps_estimate"), r.get("surprise_pct"),
          r.get("revenue_actual"), r.get("revenue_estimate"), r.get("revenue_surprise_pct"))
         for r in rows],
    )
    conn.commit()
    conn.close()


def get_earnings_history(symbol: str, limit: int = 16) -> list[dict]:
    """Get historical earnings for a stock, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM earnings_history WHERE symbol = ?
           ORDER BY date DESC LIMIT ?""",
        (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_earnings(symbol: str) -> dict | None:
    """Get the most recent earnings record for a stock."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM earnings_history WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        (symbol,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_earnings_for_training(symbols: list[str] = None) -> list[dict]:
    """Get all earnings data for ML training, optionally filtered by symbols."""
    conn = get_connection()
    if symbols:
        placeholders = ",".join(["?"] * len(symbols))
        rows = conn.execute(
            f"SELECT * FROM earnings_history WHERE symbol IN ({placeholders}) ORDER BY symbol, date",
            symbols
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM earnings_history ORDER BY symbol, date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== STOCK KNOWLEDGE =====

def save_stock_knowledge(data: dict):
    """Save or update stock knowledge entry."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO stock_knowledge
           (symbol, name, market, business_desc, parent_company, subsidiaries,
            related_stocks, suppliers, customers, commodity_exposure, sector, knowledge_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.get("symbol"), data.get("name"), data.get("market", "MY"),
         data.get("business_desc", ""), data.get("parent_company", ""),
         json.dumps(data.get("subsidiaries", [])),
         json.dumps(data.get("related_stocks", [])),
         json.dumps(data.get("suppliers", [])),
         json.dumps(data.get("customers", [])),
         json.dumps(data.get("commodity_exposure", [])),
         data.get("sector", ""),
         json.dumps(data.get("raw_knowledge", {})))
    )
    conn.commit()
    conn.close()


def get_stock_knowledge(symbol: str) -> dict | None:
    """Get knowledge for a specific stock."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM stock_knowledge WHERE symbol = ?", (symbol,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    for field in ["subsidiaries", "related_stocks", "suppliers", "customers", "commodity_exposure"]:
        try:
            r[field] = json.loads(r[field])
        except (json.JSONDecodeError, TypeError):
            r[field] = []
    try:
        r["knowledge_json"] = json.loads(r["knowledge_json"])
    except (json.JSONDecodeError, TypeError):
        r["knowledge_json"] = {}
    return r


def get_related_stocks(symbol: str) -> list[str]:
    """Get all related stock symbols for a given stock."""
    knowledge = get_stock_knowledge(symbol)
    if not knowledge:
        return []
    related = set()
    for field in ["related_stocks", "subsidiaries", "suppliers", "customers"]:
        for s in knowledge.get(field, []):
            if isinstance(s, str) and s.endswith(".KL"):
                related.add(s)
    related.discard(symbol)
    return list(related)


def get_all_stock_knowledge() -> list[dict]:
    """Get knowledge for all stocks."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM stock_knowledge ORDER BY symbol").fetchall()
    conn.close()
    results = []
    for row in rows:
        r = dict(row)
        for field in ["subsidiaries", "related_stocks", "suppliers", "customers", "commodity_exposure"]:
            try:
                r[field] = json.loads(r[field])
            except (json.JSONDecodeError, TypeError):
                r[field] = []
        results.append(r)
    return results


# ===== CATALYST ALERTS =====

def save_catalyst_scan(scan_id: str, events: list[dict], picks: list[dict],
                       direct_picks: list[dict] = None):
    """Save a catalyst scan result."""
    conn = get_connection()
    expires = (datetime.now() + __import__('datetime').timedelta(hours=24)).isoformat()

    # Save direct stock mentions as a special event
    if direct_picks:
        conn.execute(
            """INSERT OR REPLACE INTO catalyst_alerts
               (scan_id, event_type, event_label, headline, sentiment, confidence,
                affected_json, picks_json, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, "direct_mention", "Direct Stock Mentions",
             f"{len(direct_picks)} stocks detected in headlines",
             0, 0.95,
             json.dumps({}),
             json.dumps(direct_picks),
             expires)
        )

    # Save industry-level events
    for event in events:
        event_picks = [p for p in picks if p.get("catalyst_type") == event.get("event_type")]
        conn.execute(
            """INSERT OR REPLACE INTO catalyst_alerts
               (scan_id, event_type, event_label, headline, sentiment, confidence,
                affected_json, picks_json, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, event.get("event_type", ""), event.get("label", ""),
             event.get("headline", ""), event.get("sentiment", 0),
             event.get("confidence", 0),
             json.dumps(event.get("affected_industries", {})),
             json.dumps(event_picks),
             expires)
        )

    conn.commit()
    conn.close()


def get_catalyst_alerts(hours_back: int = 24, limit: int = 20) -> list[dict]:
    """Get recent catalyst alerts."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM catalyst_alerts
           WHERE scanned_at >= datetime('now', ?)
           ORDER BY confidence DESC, scanned_at DESC LIMIT ?""",
        (f"-{hours_back} hours", limit)
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r["affected_industries"] = json.loads(r.pop("affected_json", "{}"))
        r["picks"] = json.loads(r.pop("picks_json", "[]"))
        results.append(r)
    return results


def get_catalyst_history(days: int = 7, limit: int = 100) -> list[dict]:
    """Get catalyst alert history for accuracy tracking."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, o.actual_move_24h, o.is_correct
           FROM catalyst_alerts a
           LEFT JOIN catalyst_outcomes o ON a.id = o.alert_id
           WHERE a.scanned_at >= datetime('now', ?)
           ORDER BY a.scanned_at DESC LIMIT ?""",
        (f"-{days} days", limit)
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        r = dict(row)
        r["affected_industries"] = json.loads(r.pop("affected_json", "{}"))
        r["picks"] = json.loads(r.pop("picks_json", "[]"))
        results.append(r)
    return results


# ===== INSIDER HISTORY =====

def save_insider_batch(rows: list[dict]):
    """Bulk insert insider trading records."""
    if not rows:
        return
    conn = get_connection()
    conn.executemany(
        """INSERT OR IGNORE INTO insider_history
           (symbol, filing_date, insider_name, transaction_type, shares, value, shares_total)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(r.get("symbol"), r.get("filing_date"), r.get("insider_name"),
          r.get("transaction_type"), r.get("shares"), r.get("value"),
          r.get("shares_total"))
         for r in rows],
    )
    conn.commit()
    conn.close()


def get_insider_history(symbol: str, limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM insider_history WHERE symbol = ? ORDER BY filing_date DESC LIMIT ?",
        (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== ANALYST HISTORY =====

def save_analyst_batch(rows: list[dict]):
    """Bulk insert analyst recommendation records."""
    if not rows:
        return
    conn = get_connection()
    conn.executemany(
        """INSERT OR REPLACE INTO analyst_history
           (symbol, date, strong_buy, buy, hold, sell, strong_sell)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(r.get("symbol"), r.get("date"), r.get("strong_buy", 0),
          r.get("buy", 0), r.get("hold", 0), r.get("sell", 0),
          r.get("strong_sell", 0))
         for r in rows],
    )
    conn.commit()
    conn.close()


def get_analyst_history(symbol: str, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analyst_history WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== CLASSIFICATION CACHE =====

def get_cached_classification(headline_hash: str) -> str | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT industry FROM classification_cache WHERE headline_hash = ?",
        (headline_hash,)
    ).fetchone()
    conn.close()
    return row["industry"] if row else None


def save_classification_cache(headline_hash: str, industry: str, method: str = "keyword"):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO classification_cache (headline_hash, industry, method) VALUES (?, ?, ?)",
        (headline_hash, industry, method)
    )
    conn.commit()
    conn.close()


def get_cached_classifications_batch(hashes: list[str]) -> dict[str, str]:
    """Bulk lookup: returns {hash: industry} for all found entries."""
    if not hashes:
        return {}
    conn = get_connection()
    placeholders = ",".join(["?"] * len(hashes))
    rows = conn.execute(
        f"SELECT headline_hash, industry FROM classification_cache WHERE headline_hash IN ({placeholders})",
        hashes
    ).fetchall()
    conn.close()
    return {r["headline_hash"]: r["industry"] for r in rows}


# Initialize on import
init_db()
