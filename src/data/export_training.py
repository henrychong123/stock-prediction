"""
Export Training Data — joins training_data + daily_features into CSV files
ready for ML model training.

Output: data/training/<SYMBOL>.csv (one file per stock)
Also: data/training/_all_stocks.csv (combined)

Usage:
    python src/data/export_training.py              # export all stocks
    python src/data/export_training.py AAPL 1155.KL # export specific stocks
    python src/data/export_training.py --combined    # only the combined file
"""

import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pandas as pd
from src.database import init_db, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/training")


def export_stock(symbol: str, conn) -> int:
    """Export one stock's training data to CSV. Returns row count."""
    # Join training_data with daily_features on (symbol, date)
    query = """
        SELECT
            t.*,
            d.news_sentiment, d.news_count,
            d.reddit_sentiment, d.reddit_count,
            d.figure_sentiment, d.figure_count,
            d.gdelt_tone, d.fear_greed
        FROM training_data t
        LEFT JOIN daily_features d ON t.symbol = d.symbol AND t.date = d.date
        WHERE t.symbol = ?
        ORDER BY t.date
    """
    df = pd.read_sql_query(query, conn, params=(symbol,))

    if df.empty:
        log.warning(f"  {symbol}: no data")
        return 0

    # Drop internal columns
    drop_cols = ["id", "collected_at"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    # Save
    safe_name = symbol.replace(".", "_").replace("^", "IDX_")
    path = OUTPUT_DIR / f"{safe_name}.csv"
    df.to_csv(path, index=False)
    return len(df)


def export_combined(conn) -> int:
    """Export all stocks into a single CSV."""
    query = """
        SELECT
            t.*,
            d.news_sentiment, d.news_count,
            d.reddit_sentiment, d.reddit_count,
            d.figure_sentiment, d.figure_count,
            d.gdelt_tone, d.fear_greed
        FROM training_data t
        LEFT JOIN daily_features d ON t.symbol = d.symbol AND t.date = d.date
        ORDER BY t.symbol, t.date
    """
    df = pd.read_sql_query(query, conn)

    if df.empty:
        log.warning("No training data found")
        return 0

    drop_cols = ["id", "collected_at"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    path = OUTPUT_DIR / "_all_stocks.csv"
    df.to_csv(path, index=False)
    return len(df)


def show_summary(conn):
    """Print a summary of what's in the training database."""
    stats = conn.execute("""
        SELECT
            COUNT(DISTINCT symbol) as stocks,
            COUNT(*) as rows,
            MIN(date) as first_date,
            MAX(date) as last_date
        FROM training_data
    """).fetchone()

    daily_stats = conn.execute("""
        SELECT COUNT(DISTINCT symbol) as stocks, COUNT(*) as rows
        FROM daily_features
    """).fetchone()

    log.info("=" * 50)
    log.info("TRAINING DATA SUMMARY")
    log.info("=" * 50)
    log.info(f"  Stocks:     {stats['stocks']}")
    log.info(f"  Total rows: {stats['rows']:,}")
    log.info(f"  Date range: {stats['first_date']} to {stats['last_date']}")
    log.info(f"  Daily features: {daily_stats['rows']:,} rows for {daily_stats['stocks']} stocks")
    log.info("=" * 50)


def run(symbols: list[str] = None, combined_only=False):
    init_db()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()

    show_summary(conn)

    if combined_only:
        count = export_combined(conn)
        log.info(f"Exported combined CSV: {count:,} rows → {OUTPUT_DIR / '_all_stocks.csv'}")
        conn.close()
        return

    # Get list of symbols to export
    if symbols:
        stock_list = [s.upper() for s in symbols]
    else:
        rows = conn.execute("SELECT DISTINCT symbol FROM training_data ORDER BY symbol").fetchall()
        stock_list = [r["symbol"] for r in rows]

    total = len(stock_list)
    log.info(f"Exporting {total} stocks to {OUTPUT_DIR}/...")

    total_rows = 0
    for i, symbol in enumerate(stock_list, 1):
        count = export_stock(symbol, conn)
        if count > 0:
            total_rows += count
            log.info(f"  [{i}/{total}] {symbol}: {count} rows")

    # Also export combined
    combined_count = export_combined(conn)
    log.info(f"\nExported {total} individual CSVs + 1 combined ({combined_count:,} rows)")
    log.info(f"Output directory: {OUTPUT_DIR.absolute()}")

    conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    combined_only = "--combined" in args
    symbols = [a for a in args if not a.startswith("--")]
    run(symbols=symbols or None, combined_only=combined_only)
