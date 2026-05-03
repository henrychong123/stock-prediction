"""DDL for the short-term subsystem. Idempotent; safe to call on every run."""

import sqlite3

from src.shortterm.db import get_connection

_DDL = """
CREATE TABLE IF NOT EXISTS news_fulltext (
  news_id        INTEGER PRIMARY KEY,
  url            TEXT NOT NULL,
  final_url      TEXT,
  title          TEXT,
  body           TEXT NOT NULL,
  char_count     INTEGER,
  scrape_status  TEXT NOT NULL,
  scraped_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_news_fulltext_scraped ON news_fulltext(scraped_at);

CREATE TABLE IF NOT EXISTS news_fulltext_mentions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  news_id      INTEGER NOT NULL,
  symbol       TEXT NOT NULL,
  match_type   TEXT,
  match_count  INTEGER DEFAULT 1,
  confidence   REAL,
  UNIQUE(news_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_ftm_symbol ON news_fulltext_mentions(symbol);

CREATE TABLE IF NOT EXISTS shortterm_briefings (
  briefing_id    TEXT PRIMARY KEY,
  cadence        TEXT NOT NULL,
  trigger_reason TEXT,
  article_count  INTEGER,
  briefing_json  TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shortterm_picks (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  briefing_id        TEXT NOT NULL REFERENCES shortterm_briefings(briefing_id),
  symbol             TEXT NOT NULL,
  name               TEXT,
  horizon            TEXT NOT NULL,
  direction          TEXT NOT NULL,
  confidence         REAL NOT NULL,
  confidence_original REAL,           -- Claude's pre-calibration conf (null if not capped)
  predicted_move_pct REAL NOT NULL,
  reasoning          TEXT,
  source_news_ids    TEXT,
  cascade_from       TEXT,
  cascade_relation   TEXT,
  cascade_discount   REAL,
  entry_price        REAL,
  ensemble_agreement INTEGER,         -- votes out of N_RUNS; null if non-ensemble
  ensemble_n_runs    INTEGER,
  created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stp_symbol_created ON shortterm_picks(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_stp_briefing ON shortterm_picks(briefing_id);

CREATE TABLE IF NOT EXISTS shortterm_outcomes (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  pick_id           INTEGER NOT NULL REFERENCES shortterm_picks(id),
  horizon           TEXT NOT NULL,
  entry_price       REAL,
  exit_price        REAL,
  actual_move_pct   REAL,
  direction_correct INTEGER,
  measured_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(pick_id, horizon)
);
"""


def init_shortterm_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(_DDL)
        # Idempotent migrations for columns added post-launch
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(shortterm_picks)").fetchall()}
        if "confidence_original" not in cols:
            conn.execute("ALTER TABLE shortterm_picks ADD COLUMN confidence_original REAL")
        if "ensemble_agreement" not in cols:
            conn.execute("ALTER TABLE shortterm_picks ADD COLUMN ensemble_agreement INTEGER")
        if "ensemble_n_runs" not in cols:
            conn.execute("ALTER TABLE shortterm_picks ADD COLUMN ensemble_n_runs INTEGER")

        # Intra-window extremes on outcomes — see analyst_outcomes parallel.
        ocols = {r["name"] for r in conn.execute("PRAGMA table_info(shortterm_outcomes)").fetchall()}
        for col, col_type in [
            ("high_in_window",      "REAL"),
            ("low_in_window",       "REAL"),
            ("peak_favorable_move", "REAL"),
            ("max_adverse_move",    "REAL"),
            ("directional_hit",     "INTEGER"),
        ]:
            if col not in ocols:
                conn.execute(f"ALTER TABLE shortterm_outcomes ADD COLUMN {col} {col_type}")
        conn.commit()
    finally:
        conn.close()
