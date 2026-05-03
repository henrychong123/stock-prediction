"""Narrow SQLite surface for the short-term subsystem.

Only this module opens DB connections from src/shortterm/. All queries are
validated against TABLE_WHITELIST so the silo can never accidentally read
long-term ML tables (predictions, training_data, analyst_reports, etc).
"""

import os
import re
import sqlite3
from typing import Iterable

from src.shortterm.constants import TABLE_WHITELIST

_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "predictions.db")
)

_FROM_RE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _validate_sql(sql: str) -> None:
    for m in _FROM_RE.finditer(sql):
        table = m.group(1).lower()
        if table not in TABLE_WHITELIST:
            raise ValueError(
                f"shortterm.db SQL references non-whitelisted table '{table}'. "
                f"Allowed: {sorted(TABLE_WHITELIST)}"
            )


def get_db_path() -> str:
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def execute(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
    _validate_sql(sql)
    return conn.execute(sql, params)


def executemany(conn: sqlite3.Connection, sql: str, seq: Iterable) -> sqlite3.Cursor:
    _validate_sql(sql)
    return conn.executemany(sql, seq)


def fetchall(sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return list(execute(conn, sql, params).fetchall())
    finally:
        conn.close()


def fetchone(sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return execute(conn, sql, params).fetchone()
    finally:
        conn.close()


def insert_news_fulltext(
    news_id: int,
    url: str,
    final_url: str | None,
    title: str | None,
    body: str,
    scrape_status: str,
) -> None:
    conn = get_connection()
    try:
        execute(
            conn,
            """INSERT OR REPLACE INTO news_fulltext
               (news_id, url, final_url, title, body, char_count, scrape_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (news_id, url, final_url, title, body, len(body), scrape_status),
        )
        conn.commit()
    finally:
        conn.close()


def insert_fulltext_mentions(news_id: int, mentions: list[dict]) -> int:
    if not mentions:
        return 0
    conn = get_connection()
    try:
        rows = [
            (news_id, m["symbol"], m.get("match_type"), m.get("match_count", 1), m.get("confidence"))
            for m in mentions
        ]
        executemany(
            conn,
            """INSERT OR IGNORE INTO news_fulltext_mentions
               (news_id, symbol, match_type, match_count, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def insert_briefing(briefing_id: str, cadence: str, trigger_reason: str,
                    article_count: int, briefing_json: str, prompt_version: str) -> None:
    conn = get_connection()
    try:
        execute(
            conn,
            """INSERT INTO shortterm_briefings
               (briefing_id, cadence, trigger_reason, article_count, briefing_json, prompt_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (briefing_id, cadence, trigger_reason, article_count, briefing_json, prompt_version),
        )
        conn.commit()
    finally:
        conn.close()


_PICK_COLUMNS = (
    "briefing_id", "symbol", "name", "horizon", "direction", "confidence",
    "confidence_original",
    "predicted_move_pct", "reasoning", "source_news_ids",
    "cascade_from", "cascade_relation", "cascade_discount", "entry_price",
    "ensemble_agreement", "ensemble_n_runs",
)

_INSERT_PICK_SQL = (
    "INSERT INTO shortterm_picks ("
    + ", ".join(_PICK_COLUMNS)
    + ") VALUES ("
    + ", ".join("?" for _ in _PICK_COLUMNS)
    + ")"
)


def _pick_row(pick: dict) -> tuple:
    return tuple(pick.get(c) for c in _PICK_COLUMNS)


def insert_pick(pick: dict) -> int:
    conn = get_connection()
    try:
        cur = execute(conn, _INSERT_PICK_SQL, _pick_row(pick))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_picks_batch(picks: list[dict]) -> int:
    if not picks:
        return 0
    conn = get_connection()
    try:
        executemany(conn, _INSERT_PICK_SQL, [_pick_row(p) for p in picks])
        conn.commit()
        return len(picks)
    finally:
        conn.close()


def delete_briefings_older_than(days: int) -> int:
    conn = get_connection()
    try:
        cur = execute(
            conn,
            "DELETE FROM shortterm_briefings WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def insert_outcome(
    pick_id: int, horizon: str, entry_price: float | None,
    exit_price: float | None, actual_move_pct: float | None,
    direction_correct: int | None,
    high_in_window: float | None = None,
    low_in_window: float | None = None,
    peak_favorable_move: float | None = None,
    max_adverse_move: float | None = None,
    directional_hit: int | None = None,
) -> None:
    conn = get_connection()
    try:
        execute(
            conn,
            """INSERT OR IGNORE INTO shortterm_outcomes
               (pick_id, horizon, entry_price, exit_price, actual_move_pct, direction_correct,
                high_in_window, low_in_window, peak_favorable_move, max_adverse_move,
                directional_hit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pick_id, horizon, entry_price, exit_price, actual_move_pct, direction_correct,
             high_in_window, low_in_window, peak_favorable_move, max_adverse_move,
             directional_hit),
        )
        conn.commit()
    finally:
        conn.close()
