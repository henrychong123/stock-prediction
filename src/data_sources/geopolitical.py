"""
Geopolitical event tracking using the GDELT Project.

GDELT monitors news from virtually every country in 100+ languages,
updating every 15 minutes. It tracks events, tone/sentiment, and themes.

Data source:
- GDELT Doc API: Free, no API key needed, massive coverage
"""

import pandas as pd
from datetime import datetime, timedelta

from config.settings import GEOPOLITICAL_KEYWORDS


def fetch_geopolitical_events(
    keywords: list[str] | None = None,
    days_back: int = 7,
    max_records: int = 50,
) -> list[dict]:
    """Fetch geopolitical events from GDELT matching keywords.

    Args:
        keywords: Search terms (defaults to GEOPOLITICAL_KEYWORDS from config)
        days_back: How many days back to search
        max_records: Maximum number of records to return

    Returns:
        List of event dicts with title, url, source, tone, date
    """
    try:
        from gdeltdoc import GdeltDoc, Filters
    except ImportError:
        return [{"error": "gdelt-doc-api not installed. Run: pip install gdelt-doc-api"}]

    if keywords is None:
        keywords = GEOPOLITICAL_KEYWORDS

    all_events = []
    gd = GdeltDoc()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    for keyword in keywords:
        try:
            filters = Filters(
                keyword=keyword,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                num_records=max_records // len(keywords),
            )
            articles = gd.article_search(filters)

            if articles is not None and not articles.empty:
                for _, row in articles.iterrows():
                    all_events.append({
                        "keyword": keyword,
                        "title": row.get("title", ""),
                        "url": row.get("url", ""),
                        "source": row.get("domain", "unknown"),
                        "tone": row.get("tone", 0),
                        "date": str(row.get("seendate", "")),
                        "language": row.get("language", "English"),
                    })
        except Exception as e:
            all_events.append({
                "keyword": keyword,
                "error": str(e),
            })

    # Sort by date (most recent first)
    all_events.sort(key=lambda x: x.get("date", ""), reverse=True)
    return all_events[:max_records]


def get_geopolitical_signal() -> dict:
    """Analyze geopolitical events and return a market impact signal.

    Uses stored GDELT history data first (instant, no API call).
    Falls back to live GDELT API if no stored data available.

    Returns:
        Dict with signal, strength, event counts, and key events
    """
    # ── Try stored data first (instant, no rate limit issues) ─────────
    try:
        from src.database import get_connection
        from datetime import datetime, timedelta

        conn = get_connection()
        # Get average tone from last 3 days of stored GDELT data
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT industry, avg_tone, article_count FROM gdelt_history WHERE date >= ? ORDER BY date DESC",
            (three_days_ago,)
        ).fetchall()
        conn.close()

        if rows:
            tones = [r["avg_tone"] for r in rows if r["avg_tone"] is not None]
            total_articles = sum(r["article_count"] or 0 for r in rows)
            if tones:
                avg_tone = sum(tones) / len(tones)
                normalized = max(min(avg_tone / 5, 1), -1)  # stored tones are -5 to +5 range
                strength = (normalized + 1) / 2

                if normalized > 0.1:
                    signal = "bullish"
                elif normalized < -0.1:
                    signal = "bearish"
                else:
                    signal = "neutral"

                # Group by industry for breakdown
                industry_tones = {}
                for r in rows:
                    ind = r["industry"]
                    if ind not in industry_tones:
                        industry_tones[ind] = []
                    if r["avg_tone"] is not None:
                        industry_tones[ind].append(r["avg_tone"])

                top_industries = sorted(
                    [(ind, sum(t)/len(t)) for ind, t in industry_tones.items() if t],
                    key=lambda x: abs(x[1]), reverse=True
                )[:5]
                reasons = [f"[{ind}] avg tone {tone:+.2f}" for ind, tone in top_industries]

                return {
                    "signal": signal,
                    "strength": round(strength, 3),
                    "avg_tone": round(avg_tone, 3),
                    "event_count": total_articles,
                    "reasons": reasons,
                    "source": "stored",
                }
    except Exception:
        pass

    # ── Fallback: live GDELT API ──────────────────────────────────────
    events = fetch_geopolitical_events()

    if not events or "error" in events[0]:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "event_count": 0,
            "reasons": ["No geopolitical data available"],
        }

    valid_events = [e for e in events if "error" not in e]
    if not valid_events:
        return {"signal": "neutral", "strength": 0.5, "event_count": 0, "reasons": ["No events found"]}

    tones = [e.get("tone", 0) for e in valid_events if isinstance(e.get("tone"), (int, float))]
    if not tones:
        return {"signal": "neutral", "strength": 0.5, "event_count": len(valid_events), "reasons": ["No tone data"]}

    avg_tone = sum(tones) / len(tones)
    normalized = max(min(avg_tone / 10, 1), -1)
    strength = (normalized + 1) / 2

    if normalized > 0.1:
        signal = "bullish"
    elif normalized < -0.1:
        signal = "bearish"
    else:
        signal = "neutral"

    keyword_counts = {}
    for e in valid_events:
        kw = e.get("keyword", "unknown")
        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    sorted_events = sorted(valid_events, key=lambda x: abs(x.get("tone", 0)), reverse=True)
    top_events = [f"[{e.get('keyword')}] {e.get('title', 'N/A')}" for e in sorted_events[:5]]

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "avg_tone": round(avg_tone, 3),
        "event_count": len(valid_events),
        "keyword_breakdown": keyword_counts,
        "reasons": top_events,
        "source": "live",
    }
