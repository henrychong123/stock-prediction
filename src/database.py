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

        CREATE TABLE IF NOT EXISTS analyst_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id       TEXT NOT NULL UNIQUE,
            run_type        TEXT NOT NULL,
            market          TEXT NOT NULL,
            picks_json      TEXT NOT NULL,
            summary         TEXT,
            headlines_used  INTEGER,
            articles_used   INTEGER,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS analyst_outcomes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id       TEXT NOT NULL REFERENCES analyst_reports(report_id),
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            confidence      REAL,
            predicted_move  REAL,
            actual_move_24h REAL,
            entry_price     REAL,
            exit_price      REAL,
            is_correct      INTEGER,
            reasoning       TEXT,
            measured_at     TEXT,
            UNIQUE(report_id, symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_analyst_reports_created ON analyst_reports(created_at);
        CREATE INDEX IF NOT EXISTS idx_analyst_outcomes_report ON analyst_outcomes(report_id);

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

        -- ── Paper trading ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS virtual_strategies (
            strategy_id        TEXT PRIMARY KEY,
            name               TEXT NOT NULL,
            description        TEXT,
            starting_capital   REAL NOT NULL,
            rules_json         TEXT,
            created_at         TEXT DEFAULT (datetime('now')),
            active             INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS virtual_portfolios (
            strategy_id        TEXT PRIMARY KEY REFERENCES virtual_strategies(strategy_id),
            cash_balance       REAL NOT NULL,
            equity             REAL NOT NULL,
            last_mtm_at        TEXT,
            updated_at         TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS virtual_positions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id        TEXT NOT NULL,
            symbol             TEXT NOT NULL,
            direction          TEXT NOT NULL,
            entry_price        REAL NOT NULL,
            quantity           INTEGER NOT NULL,
            entry_cost         REAL NOT NULL,
            stop_loss_price    REAL,
            take_profit_price  REAL,
            from_pick_id       TEXT,
            from_report_id     TEXT,
            current_price      REAL,
            unrealized_pnl     REAL,
            opened_at          TEXT DEFAULT (datetime('now')),
            UNIQUE(strategy_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS virtual_trades (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id        TEXT NOT NULL,
            symbol             TEXT NOT NULL,
            side               TEXT NOT NULL,
            quantity           INTEGER NOT NULL,
            price              REAL NOT NULL,
            commission         REAL DEFAULT 0,
            other_fees         REAL DEFAULT 0,
            total_cost         REAL NOT NULL,
            realized_pnl       REAL,
            reason             TEXT,
            from_pick_id       TEXT,
            from_report_id     TEXT,
            executed_at        TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS virtual_equity_snapshots (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id        TEXT NOT NULL,
            snapshot_at        TEXT DEFAULT (datetime('now')),
            cash_balance       REAL NOT NULL,
            positions_value    REAL NOT NULL,
            total_equity       REAL NOT NULL,
            open_positions     INTEGER DEFAULT 0,
            UNIQUE(strategy_id, snapshot_at)
        );

        CREATE INDEX IF NOT EXISTS idx_virtual_trades_strategy ON virtual_trades(strategy_id, executed_at);
        CREATE INDEX IF NOT EXISTS idx_virtual_positions_strategy ON virtual_positions(strategy_id);
        CREATE INDEX IF NOT EXISTS idx_virtual_equity_strategy_time ON virtual_equity_snapshots(strategy_id, snapshot_at);

        -- ── Orderbook snapshots (for analyst confidence model) ────────────
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            snapshot_at     TEXT DEFAULT (datetime('now')),
            source          TEXT,                 -- "IB Gateway (Level 2)" or "yfinance (Level 1 ...)"
            level           INTEGER,              -- 1 or 2
            best_bid        REAL,
            best_ask        REAL,
            spread          REAL,
            spread_pct      REAL,
            total_bid_vol   REAL,
            total_ask_vol   REAL,
            pressure        REAL,                 -- bid/ask imbalance 0-100
            raw_json        TEXT                  -- full response incl. depth for L2
        );

        CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_time ON orderbook_snapshots(symbol, snapshot_at);
        CREATE INDEX IF NOT EXISTS idx_orderbook_time ON orderbook_snapshots(snapshot_at);

        -- ── Quarterly fundamentals ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS fundamentals_quarterly (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol                  TEXT NOT NULL,
            period_end              TEXT NOT NULL,          -- ISO date of fiscal quarter end
            fiscal_year             INTEGER,
            fiscal_quarter          INTEGER,                -- 1-4
            -- Income statement (in reporting currency)
            revenue                 REAL,
            cost_of_revenue         REAL,
            gross_profit            REAL,
            operating_expenses      REAL,
            operating_income        REAL,
            ebitda                  REAL,
            net_income              REAL,
            eps                     REAL,
            -- Balance sheet
            total_assets            REAL,
            total_liabilities       REAL,
            total_equity            REAL,
            cash_and_equivalents    REAL,
            short_term_debt         REAL,
            long_term_debt          REAL,
            total_debt              REAL,
            -- Cash flow
            operating_cash_flow     REAL,
            capex                   REAL,
            free_cash_flow          REAL,
            -- Ratios (pre-computed at save time)
            gross_margin            REAL,
            operating_margin        REAL,
            net_margin              REAL,
            fcf_margin              REAL,
            roe                     REAL,
            roa                     REAL,
            roic                    REAL,
            debt_to_equity          REAL,
            net_debt_to_ebitda      REAL,
            current_ratio           REAL,
            -- Growth (YoY)
            revenue_growth_yoy      REAL,
            earnings_growth_yoy     REAL,
            -- Meta
            currency                TEXT,
            updated_at              TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, period_end)
        );

        CREATE INDEX IF NOT EXISTS idx_fund_symbol_period ON fundamentals_quarterly(symbol, period_end);

        -- ── Options chains (strike-level snapshots) ─────────────────────────
        CREATE TABLE IF NOT EXISTS options_chains (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            snapshot_at     TEXT DEFAULT (datetime('now')),
            expiration      TEXT NOT NULL,      -- ISO date
            strike          REAL NOT NULL,
            option_type     TEXT NOT NULL,      -- 'call' or 'put'
            last_price      REAL,
            bid             REAL,
            ask             REAL,
            volume          INTEGER,
            open_interest   INTEGER,
            implied_vol     REAL,                -- decimal, 0.25 = 25%
            in_the_money    INTEGER,             -- 0/1
            spot_price      REAL                 -- underlying price at snapshot
        );

        CREATE INDEX IF NOT EXISTS idx_options_symbol_time ON options_chains(symbol, snapshot_at);
        CREATE INDEX IF NOT EXISTS idx_options_symbol_exp ON options_chains(symbol, expiration);

        -- Per-symbol aggregate features computed from chains at snapshot time
        CREATE TABLE IF NOT EXISTS options_snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol                  TEXT NOT NULL,
            snapshot_at             TEXT DEFAULT (datetime('now')),
            spot_price              REAL,
            atm_call_iv             REAL,        -- at-the-money call implied vol
            atm_put_iv              REAL,
            atm_iv_avg              REAL,        -- avg of ATM call + put
            iv_rank_30d             REAL,        -- percentile of current IV over last 30 snapshots
            iv_rank_90d             REAL,
            put_call_ratio_vol      REAL,        -- total put vol / total call vol
            put_call_ratio_oi       REAL,        -- put OI / call OI
            call_skew_25d           REAL,        -- 25-delta call IV - ATM IV
            put_skew_25d            REAL,
            total_call_volume       INTEGER,
            total_put_volume        INTEGER,
            total_call_oi           INTEGER,
            total_put_oi            INTEGER,
            unusual_volume_flag     INTEGER,     -- 1 if any contract vol > 2x OI
            unusual_oi_jump         INTEGER,     -- 1 if largest OI change > 200% vs 5 day avg
            nearest_expiration      TEXT,
            chain_count             INTEGER      -- # strikes in nearest expiry
        );

        CREATE INDEX IF NOT EXISTS idx_options_snap_symbol_time ON options_snapshots(symbol, snapshot_at);

        -- ── 13F institutional holdings ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS institutional_filers (
            cik             TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            short_name      TEXT,
            fund_type       TEXT,                -- hedge_fund / family_office / pension / etc
            notes           TEXT,
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS institutional_filings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cik             TEXT NOT NULL,
            accession_no    TEXT NOT NULL,
            period_end      TEXT NOT NULL,       -- Quarter end YYYY-MM-DD
            filed_at        TEXT,
            form_type       TEXT,                -- 13F-HR / 13F-NT
            total_value     REAL,                -- total portfolio value USD
            holdings_count  INTEGER,
            fetched_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(cik, accession_no)
        );

        CREATE TABLE IF NOT EXISTS institutional_holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cik             TEXT NOT NULL,
            period_end      TEXT NOT NULL,
            symbol          TEXT,                -- may be empty if CUSIP unresolved
            cusip           TEXT NOT NULL,
            issuer_name     TEXT,
            shares          REAL,
            value_usd       REAL,                -- value at period end
            percent_of_port REAL,                -- % of filer's total portfolio
            change_type     TEXT,                -- new / added / reduced / held / liquidated (vs prior qtr)
            change_shares   REAL,                -- delta vs prior qtr
            change_pct      REAL,                -- % change vs prior qtr
            UNIQUE(cik, period_end, cusip)
        );

        CREATE INDEX IF NOT EXISTS idx_inst_sym_period ON institutional_holdings(symbol, period_end);
        CREATE INDEX IF NOT EXISTS idx_inst_cik_period ON institutional_holdings(cik, period_end);
        CREATE INDEX IF NOT EXISTS idx_inst_change ON institutional_holdings(change_type, period_end);

        -- Aggregate per-symbol per-quarter (pre-computed for fast queries)
        CREATE TABLE IF NOT EXISTS institutional_flow (
            symbol              TEXT NOT NULL,
            period_end          TEXT NOT NULL,
            buyer_count         INTEGER,          -- filers with new or added positions
            seller_count        INTEGER,          -- filers with reduced or liquidated
            holder_count        INTEGER,          -- total filers holding at period end
            new_position_count  INTEGER,
            liquidated_count    INTEGER,
            total_value_held    REAL,             -- sum of value_usd across filers
            total_shares_held   REAL,
            net_flow_shares     REAL,             -- sum of change_shares across filers
            net_flow_direction  TEXT,             -- 'bullish' / 'bearish' / 'mixed'
            updated_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (symbol, period_end)
        );

        CREATE INDEX IF NOT EXISTS idx_inst_flow_symbol ON institutional_flow(symbol);

        -- Current/latest fundamental snapshot (faster than fetching from API every time)
        CREATE TABLE IF NOT EXISTS fundamentals_current (
            symbol                  TEXT PRIMARY KEY,
            pe_ratio                REAL,
            forward_pe              REAL,
            pb_ratio                REAL,
            peg_ratio               REAL,
            ev_ebitda               REAL,
            price_to_sales          REAL,
            eps                     REAL,
            dividend_yield          REAL,
            beta                    REAL,
            market_cap              REAL,
            enterprise_value        REAL,
            shares_outstanding      REAL,
            fifty_two_week_high     REAL,
            fifty_two_week_low      REAL,
            updated_at              TEXT DEFAULT (datetime('now'))
        );
    """)

    # Migration: add failure_analysis column to analyst_outcomes
    try:
        conn.execute("ALTER TABLE analyst_outcomes ADD COLUMN failure_analysis TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Migration: intra-window extremes so we can tell direction failures apart
    # from timing failures (close-to-close eval misses stocks that hit target
    # then reversed before EoD).
    for col, col_type in [
        ("high_in_window",      "REAL"),
        ("low_in_window",       "REAL"),
        ("peak_favorable_move", "REAL"),
        ("max_adverse_move",    "REAL"),
        ("directional_hit",     "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE analyst_outcomes ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass

    # Migration: archive the briefing Claude saw per report (for attribution)
    try:
        conn.execute("ALTER TABLE analyst_reports ADD COLUMN briefing_json TEXT")
        conn.commit()
    except Exception:
        pass

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


def get_all_latest_snapshots() -> list[dict]:
    """Latest snapshot for every tracked symbol (single query)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT ps.*
           FROM price_snapshots ps
           INNER JOIN (
               SELECT symbol, MAX(recorded_at) AS max_at
               FROM price_snapshots
               GROUP BY symbol
           ) latest ON ps.symbol = latest.symbol AND ps.recorded_at = latest.max_at
           ORDER BY ps.symbol"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_movers(hours: int = 24, limit: int = 10) -> dict:
    """Top gainers and losers by % change within the last N hours."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT ps.*
           FROM price_snapshots ps
           INNER JOIN (
               SELECT symbol, MAX(recorded_at) AS max_at
               FROM price_snapshots
               WHERE recorded_at >= datetime('now', 'localtime', ?)
               GROUP BY symbol
           ) latest ON ps.symbol = latest.symbol AND ps.recorded_at = latest.max_at
           WHERE ps.change_pct IS NOT NULL
           ORDER BY ps.change_pct DESC""",
        (f"-{hours} hours",)
    ).fetchall()
    conn.close()
    all_rows = [dict(r) for r in rows]
    return {
        "gainers": all_rows[:limit],
        "losers": list(reversed(all_rows[-limit:])),
        "total_tracked": len(all_rows),
    }


def get_price_at_time(symbol: str, timestamp: str) -> dict | None:
    """Snapshot closest to a given timestamp for a symbol."""
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM price_snapshots
           WHERE symbol = ?
           ORDER BY ABS(JULIANDAY(recorded_at) - JULIANDAY(?))
           LIMIT 1""",
        (symbol, timestamp)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


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
    """Get recent catalyst alerts, deduped by (event_type, headline)."""
    conn = get_connection()
    # Fetch more rows than needed so dedup doesn't shrink below limit
    rows = conn.execute(
        """SELECT * FROM catalyst_alerts
           WHERE scanned_at >= datetime('now', ?)
           ORDER BY confidence DESC, scanned_at DESC LIMIT ?""",
        (f"-{hours_back} hours", limit * 5)
    ).fetchall()
    conn.close()

    seen = {}
    for row in rows:
        r = dict(row)
        r["affected_industries"] = json.loads(r.pop("affected_json", "{}"))
        r["picks"] = json.loads(r.pop("picks_json", "[]"))
        key = (r.get("event_type", ""), (r.get("headline") or "").strip().lower())
        if key not in seen:
            seen[key] = r

    return list(seen.values())[:limit]


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


# ===== AI ANALYST =====

def save_analyst_report(report_id: str, run_type: str, market: str,
                        picks: list[dict], summary: str = "",
                        headlines_used: int = 0, articles_used: int = 0,
                        briefing: dict | None = None):
    """Save an AI analyst report with picks.
    briefing: optional structured stocks_context Claude saw (for attribution later).
    Applies confidence calibration: picks above 0.65 without a concrete named
    catalyst in their reasoning get capped at 0.65."""
    from src.evaluation.calibration import calibrate_confidence
    calibrated_picks = []
    capped_count = 0
    for p in picks or []:
        if not isinstance(p, dict):
            calibrated_picks.append(p)
            continue
        pc = dict(p)
        reasoning_bits = [p.get("reasoning", "")]
        # Bull/bear case arrays also describe the thesis
        reasoning_bits.extend(p.get("bull_case", []) or [])
        reasoning_bits.extend(p.get("bear_case", []) or [])
        combined_reasoning = " ".join(str(b) for b in reasoning_bits if b)
        new_conf, was_capped = calibrate_confidence(p.get("confidence", 0), combined_reasoning)
        if was_capped:
            capped_count += 1
            pc["confidence_original"] = p.get("confidence")
        pc["confidence"] = new_conf
        calibrated_picks.append(pc)
    if capped_count:
        import logging as _l
        _l.getLogger(__name__).info(
            f"save_analyst_report: capped confidence on {capped_count}/{len(picks)} picks"
        )

    conn = get_connection()
    briefing_json = json.dumps(briefing) if briefing else None
    conn.execute(
        """INSERT OR REPLACE INTO analyst_reports
           (report_id, run_type, market, picks_json, summary, headlines_used,
            articles_used, briefing_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (report_id, run_type, market, json.dumps(calibrated_picks), summary,
         headlines_used, articles_used, briefing_json)
    )
    conn.commit()
    conn.close()


def get_analyst_reports(days: int = 7, market: str = None,
                        limit: int = 50) -> list[dict]:
    """Get recent analyst reports."""
    conn = get_connection()
    clauses = ["created_at >= datetime('now', ?)"]
    params: list = [f"-{days} days"]
    if market:
        clauses.append("market = ?")
        params.append(market)
    where = "WHERE " + " AND ".join(clauses)
    params.append(limit)
    rows = conn.execute(
        f"""SELECT * FROM analyst_reports {where}
            ORDER BY created_at DESC LIMIT ?""", params
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r["picks"] = json.loads(r.pop("picks_json", "[]"))
        results.append(r)
    return results


def get_analyst_latest(market: str = None) -> dict | None:
    """Get the most recent analyst report."""
    reports = get_analyst_reports(days=7, market=market, limit=1)
    return reports[0] if reports else None


def get_last_evaluated_report(market: str = None) -> dict | None:
    """Most recent analyst report that has at least one outcome row.

    Lets the scorecard show the newest *scored* picks instead of today's
    unscored picks.
    """
    conn = get_connection()
    clauses = ["r.report_id IN (SELECT DISTINCT report_id FROM analyst_outcomes)"]
    params: list = []
    if market:
        clauses.append("r.market = ?")
        params.append(market)
    where = "WHERE " + " AND ".join(clauses)
    row = conn.execute(
        f"""SELECT r.* FROM analyst_reports r {where}
            ORDER BY r.created_at DESC LIMIT 1""", params
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    r["picks"] = json.loads(r.pop("picks_json", "[]"))
    return r


def list_evaluated_reports(market: str = None, days: int = 30, limit: int = 60) -> list[dict]:
    """All analyst reports with >=1 outcome row, newest first.

    Each row: report_id, run_type, market, created_at, picks_count, correct_count.
    Powers the scorecard dropdown.
    """
    conn = get_connection()
    clauses = ["o.report_id IS NOT NULL", "r.created_at >= datetime('now', ?)"]
    params: list = [f"-{days} days"]
    if market:
        clauses.append("r.market = ?")
        params.append(market)
    where = " AND ".join(clauses)
    params.append(limit)
    rows = conn.execute(
        f"""SELECT r.report_id, r.run_type, r.market, r.created_at,
                   COUNT(o.id)             AS picks_count,
                   SUM(o.is_correct)       AS correct_count
              FROM analyst_reports r
              JOIN analyst_outcomes o ON o.report_id = r.report_id
             WHERE {where}
          GROUP BY r.report_id
          ORDER BY r.created_at DESC
             LIMIT ?""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analyst_report_by_id(report_id: str) -> dict | None:
    """Fetch a single analyst report by its report_id (includes picks)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM analyst_reports WHERE report_id = ?", (report_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    r["picks"] = json.loads(r.pop("picks_json", "[]"))
    return r


def save_analyst_outcome(report_id: str, symbol: str, direction: str,
                         confidence: float, predicted_move: float,
                         actual_move: float, entry_price: float,
                         exit_price: float, is_correct: int,
                         reasoning: str = "",
                         high_in_window: float | None = None,
                         low_in_window: float | None = None,
                         peak_favorable_move: float | None = None,
                         max_adverse_move: float | None = None,
                         directional_hit: int | None = None):
    """Save outcome measurement for a single pick."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO analyst_outcomes
           (report_id, symbol, direction, confidence, predicted_move,
            actual_move_24h, entry_price, exit_price, is_correct, reasoning,
            high_in_window, low_in_window, peak_favorable_move, max_adverse_move,
            directional_hit, measured_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (report_id, symbol, direction, confidence, predicted_move,
         actual_move, entry_price, exit_price, is_correct, reasoning,
         high_in_window, low_in_window, peak_favorable_move, max_adverse_move,
         directional_hit)
    )
    conn.commit()
    conn.close()


def get_analyst_outcomes(report_id: str = None, days: int = 30) -> list[dict]:
    """Get analyst outcomes, optionally filtered by report."""
    conn = get_connection()
    if report_id:
        rows = conn.execute(
            "SELECT * FROM analyst_outcomes WHERE report_id = ? ORDER BY measured_at DESC",
            (report_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT o.*, r.market, r.run_type, r.created_at as report_created
               FROM analyst_outcomes o
               JOIN analyst_reports r ON o.report_id = r.report_id
               WHERE r.created_at >= datetime('now', ?)
               ORDER BY o.measured_at DESC""",
            (f"-{days} days",)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wrong_picks_without_analysis(limit: int = 20) -> list[dict]:
    """Wrong picks that have not yet been analysed for failure reasons."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT o.id, o.report_id, o.symbol, o.direction, o.confidence,
                  o.predicted_move, o.actual_move_24h, o.entry_price,
                  o.exit_price, o.reasoning, o.measured_at,
                  o.high_in_window, o.low_in_window, o.peak_favorable_move,
                  o.max_adverse_move, o.directional_hit,
                  r.picks_json, r.created_at as report_created, r.market
           FROM analyst_outcomes o
           JOIN analyst_reports r ON o.report_id = r.report_id
           WHERE o.is_correct = 0
             AND (o.failure_analysis IS NULL OR o.failure_analysis = '')
           ORDER BY o.measured_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_failure_analysis(outcome_id: int, analysis: dict) -> None:
    """Store the structured failure analysis for a wrong pick."""
    conn = get_connection()
    conn.execute(
        "UPDATE analyst_outcomes SET failure_analysis = ? WHERE id = ?",
        (json.dumps(analysis), outcome_id)
    )
    conn.commit()
    conn.close()


def get_wrong_picks_with_analysis(days: int = 30) -> list[dict]:
    """Wrong picks that have a failure_analysis, for batch reflection."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT o.id, o.symbol, o.direction, o.confidence,
                  o.actual_move_24h, o.failure_analysis,
                  r.market, r.run_type, r.created_at as report_created
           FROM analyst_outcomes o
           JOIN analyst_reports r ON o.report_id = r.report_id
           WHERE o.is_correct = 0
             AND o.failure_analysis IS NOT NULL
             AND o.failure_analysis != ''
             AND r.created_at >= datetime('now', ?)
           ORDER BY r.created_at DESC""",
        (f"-{days} days",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analyst_accuracy(days: int = 30) -> dict:
    """Get rolling accuracy statistics for the AI analyst."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT o.is_correct, o.direction, o.actual_move_24h, o.predicted_move,
                  r.created_at as report_date, r.market
           FROM analyst_outcomes o
           JOIN analyst_reports r ON o.report_id = r.report_id
           WHERE o.is_correct IS NOT NULL
           AND r.created_at >= datetime('now', ?)
           ORDER BY r.created_at ASC""",
        (f"-{days} days",)
    ).fetchall()
    conn.close()

    if not rows:
        return {"total": 0, "correct": 0, "accuracy_pct": None, "daily": []}

    total = len(rows)
    correct = sum(1 for r in rows if r["is_correct"] == 1)
    accuracy = round(correct / total * 100, 1) if total > 0 else None

    # Group by date for daily accuracy trend
    daily = {}
    for r in rows:
        date = r["report_date"][:10]
        if date not in daily:
            daily[date] = {"date": date, "total": 0, "correct": 0}
        daily[date]["total"] += 1
        if r["is_correct"] == 1:
            daily[date]["correct"] += 1

    for d in daily.values():
        d["accuracy_pct"] = round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else 0

    return {
        "total": total,
        "correct": correct,
        "accuracy_pct": accuracy,
        "daily": sorted(daily.values(), key=lambda x: x["date"]),
    }


def get_unevaluated_reports(hours_min: int = 24) -> list[dict]:
    """Get reports older than hours_min that haven't been fully evaluated yet."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.* FROM analyst_reports r
           WHERE r.created_at <= datetime('now', ?)
           AND r.report_id NOT IN (
               SELECT DISTINCT report_id FROM analyst_outcomes
           )
           ORDER BY r.created_at DESC LIMIT 10""",
        (f"-{hours_min} hours",)
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        r = dict(row)
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
