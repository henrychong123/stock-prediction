"""
GDELT Historical Backfill — downloads 2 years of daily media tone data
per industry keyword set from the GDELT database.

GDELT (Global Database of Events, Language, and Tone) tracks global news media
and provides tone scores for articles. We use this as a historical proxy for
news sentiment per industry.

Usage:
    python src/data/collect_gdelt_history.py              # full 2-year backfill
    python src/data/collect_gdelt_history.py --months 6   # last 6 months only
    python src/data/collect_gdelt_history.py --industry "Technology"  # single industry
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_gdelt_history_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Industry → keywords mapping (canonical source)
from config.industries import GDELT_KEYWORDS as INDUSTRY_KEYWORDS


def fetch_gdelt_tone(keyword: str, start_date: str, end_date: str) -> list[dict]:
    """Query GDELT timeline tone for a keyword in a date range.
    Returns list of {date, tone} records.
    Falls back to article search if timeline is rate-limited."""
    try:
        from gdeltdoc import GdeltDoc, Filters
        gd = GdeltDoc()

        f = Filters(
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
        )

        # Try timeline tone first (returns daily aggregated tone)
        try:
            df = gd.timeline_search("timelinetone", f)
            if df is not None and not df.empty:
                results = []
                for _, row in df.iterrows():
                    date_val = str(row.get("datetime", ""))[:10]
                    tone_val = row.get("Average Tone") or row.get(df.columns[-1])
                    if date_val and tone_val is not None:
                        results.append({"date": date_val, "tone": float(tone_val)})
                return results
        except Exception:
            pass  # Fall through to article search

        # Fallback: article search (no tone column, but we can count volume)
        try:
            articles = gd.article_search(f)
            if articles is not None and not articles.empty:
                # Group by date, count articles as activity indicator
                articles["date"] = articles["seendate"].astype(str).str[:10]
                daily = articles.groupby("date").size().reset_index(name="count")
                results = []
                for _, row in daily.iterrows():
                    results.append({
                        "date": row["date"],
                        "tone": 0,  # no tone from article search, use count as proxy
                        "count": int(row["count"]),
                    })
                return results
        except Exception:
            pass

        return []

    except ImportError:
        log.error("gdeltdoc not installed. Run: pip install gdeltdoc")
        return []
    except Exception as e:
        log.warning(f"  GDELT query failed for '{keyword}' ({start_date} to {end_date}): {e}")
        return []


def collect_industry(industry: str, keywords: list[str],
                     start: datetime, end: datetime) -> int:
    """Collect GDELT data for one industry across the date range.
    Queries in 30-day chunks to avoid API limits.
    Returns total rows saved."""

    rows_saved = 0
    chunk_days = 30
    current = start

    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        start_str = current.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")

        # Collect articles for all keywords in this chunk
        all_tones = {}  # date → list of tones

        for kw in keywords:
            records = fetch_gdelt_tone(kw, start_str, end_str)
            for rec in records:
                d = rec.get("date", "")[:10]
                if d:
                    if d not in all_tones:
                        all_tones[d] = {"tones": [], "count": 0}
                    if rec.get("tone", 0) != 0:
                        all_tones[d]["tones"].append(rec["tone"])
                    all_tones[d]["count"] += rec.get("count", 1)

            time.sleep(5)  # longer delay to avoid GDELT rate limits

        # Aggregate daily tones
        batch = []
        for date, data in sorted(all_tones.items()):
            avg_tone = sum(data["tones"]) / len(data["tones"]) if data["tones"] else 0
            batch.append({
                "date": date,
                "industry": industry,
                "avg_tone": round(avg_tone, 4),
                "article_count": data["count"],
                "keywords": ",".join(keywords),
            })

        if batch:
            save_gdelt_history_batch(batch)
            rows_saved += len(batch)

        log.info(f"  {start_str} to {end_str}: {len(all_tones)} days with data")
        current = chunk_end

    return rows_saved


def run(months: int = 24, industry_filter: str = None):
    init_db()

    end = datetime.now()
    start = end - timedelta(days=months * 30)

    industries = INDUSTRY_KEYWORDS
    if industry_filter:
        industries = {k: v for k, v in industries.items() if k.lower() == industry_filter.lower()}
        if not industries:
            log.error(f"Unknown industry: {industry_filter}")
            log.info(f"Available: {', '.join(INDUSTRY_KEYWORDS.keys())}")
            return

    total_industries = len(industries)
    total_rows = 0

    log.info(f"GDELT Historical Backfill")
    log.info(f"  Period: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')} ({months} months)")
    log.info(f"  Industries: {total_industries}")
    log.info(f"  Chunks: ~{months} per industry (30-day windows)")
    log.info("")

    for i, (industry, keywords) in enumerate(industries.items(), 1):
        log.info(f"[{i}/{total_industries}] {industry} (keywords: {keywords})")
        count = collect_industry(industry, keywords, start, end)
        total_rows += count
        log.info(f"  → {count} daily records saved")
        time.sleep(2)  # pause between industries

    log.info(f"\nDone — {total_rows} total records across {total_industries} industries")


if __name__ == "__main__":
    args = sys.argv[1:]
    months = 24
    industry = None

    for i, a in enumerate(args):
        if a == "--months" and i + 1 < len(args):
            months = int(args[i + 1])
        if a == "--industry" and i + 1 < len(args):
            industry = args[i + 1]

    run(months=months, industry_filter=industry)
