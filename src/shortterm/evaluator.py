"""Measure 24h/3d/7d outcomes for due picks and regenerate MEMORY.md.

Silo: queries only shortterm_picks, shortterm_outcomes, and yfinance.
MEMORY.md is what feeds the reasoner's prompt next run — it's the
mechanism by which the agent learns from its own mistakes.
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from src.evaluation.correctness import is_correct_int
from src.shortterm import db
from src.shortterm.constants import (
    BRIEFING_RETENTION_DAYS,
    HORIZONS,
    MEMORY_MD_PATH,
    MEMORY_OUTCOME_LIMIT,
    MEMORY_REASONING_TRUNCATE,
    horizon_hours,
)

log = logging.getLogger(__name__)

_MEMORY_HEADER = "# MEMORY — Short-Term Reasoner Self-Reflection\n"


def _parse_sqlite_dt(s: str) -> datetime:
    s = s.replace("T", " ")
    if "." in s:
        s = s.split(".")[0]
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _yfinance_close_on_or_after(symbol: str, target_dt: datetime) -> float | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        start = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        end = (target_dt + timedelta(days=7)).strftime("%Y-%m-%d")
        hist = yf.Ticker(symbol).history(start=start, end=end)
    except Exception as e:
        log.debug(f"yfinance close lookup failed for {symbol}: {e}")
        return None
    if hist.empty:
        return None
    closes = hist["Close"].dropna()
    for dt, close in closes.items():
        dt_utc = dt.to_pydatetime()
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        if dt_utc >= target_dt:
            return round(float(close), 4)
    if closes.empty:
        return None
    log.info(f"{symbol}: no bar at/after {target_dt.isoformat()}; using last available close")
    return round(float(closes.iloc[-1]), 4)


def _yfinance_window_extremes(symbol: str, start_dt: datetime, end_dt: datetime
                              ) -> tuple[float, float, float] | None:
    """Return (close_at_or_after_end, max_high_in_window, min_low_in_window).
    Uses daily bars — sufficient for 24h/3d/7d horizons.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        start = start_dt.strftime("%Y-%m-%d")
        end = (end_dt + timedelta(days=2)).strftime("%Y-%m-%d")
        hist = yf.Ticker(symbol).history(start=start, end=end)
    except Exception as e:
        log.debug(f"yfinance window lookup failed for {symbol}: {e}")
        return None
    if hist.empty:
        return None

    in_window = hist[(hist.index >= start_dt) & (hist.index <= end_dt + timedelta(days=1))]
    if in_window.empty:
        return None

    closes = in_window["Close"].dropna()
    exit_close = None
    for dt, close in closes.items():
        dt_utc = dt.to_pydatetime()
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        if dt_utc >= end_dt:
            exit_close = round(float(close), 4)
            break
    if exit_close is None and not closes.empty:
        exit_close = round(float(closes.iloc[-1]), 4)
    if exit_close is None:
        return None

    return (
        exit_close,
        round(float(in_window["High"].max()), 4),
        round(float(in_window["Low"].min()), 4),
    )


def _due_picks() -> list[dict]:
    now_utc = datetime.now(timezone.utc)
    rows = db.fetchall(
        """SELECT p.id, p.symbol, p.horizon, p.direction, p.confidence,
                  p.predicted_move_pct, p.entry_price, p.created_at, p.reasoning
           FROM shortterm_picks p
           LEFT JOIN shortterm_outcomes o
             ON o.pick_id = p.id AND o.horizon = p.horizon
           WHERE o.id IS NULL
           ORDER BY p.created_at ASC"""
    )
    due: list[dict] = []
    for r in rows:
        created = _parse_sqlite_dt(r["created_at"])
        horizon_end = created + timedelta(hours=horizon_hours(r["horizon"]))
        if horizon_end > now_utc:
            continue
        due.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "horizon": r["horizon"],
            "direction": r["direction"],
            "confidence": r["confidence"],
            "predicted_move_pct": r["predicted_move_pct"],
            "entry_price": r["entry_price"],
            "created_at": created,
            "horizon_end": horizon_end,
            "reasoning": r["reasoning"] or "",
        })
    return due


def measure_due_outcomes() -> dict:
    due = _due_picks()
    counts = {"measured": 0, "skipped_no_price": 0, "skipped_no_move": 0}
    for p in due:
        window = _yfinance_window_extremes(p["symbol"], p["created_at"], p["horizon_end"])
        if window is None or p["entry_price"] is None or p["entry_price"] <= 0:
            counts["skipped_no_price"] += 1
            continue
        exit_price, high_w, low_w = window
        # Skip when price hasn't moved — likely weekend/holiday (yfinance returns
        # the same last trading day's close). Counting these as losses poisons MEMORY.md.
        if exit_price == p["entry_price"]:
            counts["skipped_no_move"] += 1
            continue
        entry = p["entry_price"]
        actual_move = (exit_price - entry) / entry * 100.0
        correct = is_correct_int(p["direction"], actual_move)

        if (p["direction"] or "").lower() == "bearish":
            peak_fav = round((entry - low_w) / entry * 100.0, 2)
            max_adv = round((entry - high_w) / entry * 100.0, 2)
        else:
            peak_fav = round((high_w - entry) / entry * 100.0, 2)
            max_adv = round((low_w - entry) / entry * 100.0, 2)
        dir_hit = 1 if peak_fav >= 0.5 else 0

        db.insert_outcome(
            pick_id=p["id"],
            horizon=p["horizon"],
            entry_price=entry,
            exit_price=exit_price,
            actual_move_pct=round(actual_move, 4),
            direction_correct=correct,
            high_in_window=high_w,
            low_in_window=low_w,
            peak_favorable_move=peak_fav,
            max_adverse_move=max_adv,
            directional_hit=dir_hit,
        )
        counts["measured"] += 1
    log.info(f"evaluator: {counts}")
    return counts


def empty_horizon_buckets() -> dict:
    return {h: {"n": 0, "correct": 0, "pct": None} for h in HORIZONS}


def accuracy_for_window(days: int | None) -> dict:
    if days is None:
        where = "1=1"
        params: tuple = ()
    else:
        where = "measured_at >= datetime('now', ?)"
        params = (f"-{days} days",)
    rows = db.fetchall(
        f"""SELECT horizon, direction_correct
            FROM shortterm_outcomes
            WHERE {where}""",
        params,
    )
    buckets = empty_horizon_buckets()
    for r in rows:
        h = r["horizon"]
        if h not in buckets:
            continue
        buckets[h]["n"] += 1
        if r["direction_correct"]:
            buckets[h]["correct"] += 1
    for v in buckets.values():
        v["pct"] = round(v["correct"] / v["n"] * 100.0, 1) if v["n"] else None
    return buckets


_accuracy_for_window = accuracy_for_window


def _recent_outcomes(n: int, correct: bool) -> list[dict]:
    rows = db.fetchall(
        """SELECT p.symbol, p.horizon, p.direction, p.predicted_move_pct,
                  p.reasoning, o.actual_move_pct, o.measured_at
           FROM shortterm_outcomes o
           JOIN shortterm_picks p ON p.id = o.pick_id
           WHERE o.direction_correct = ?
           ORDER BY o.measured_at DESC
           LIMIT ?""",
        (1 if correct else 0, n),
    )
    return [
        {
            "symbol": r["symbol"],
            "horizon": r["horizon"],
            "direction": r["direction"],
            "predicted_move_pct": r["predicted_move_pct"],
            "actual_move_pct": r["actual_move_pct"],
            "reasoning": r["reasoning"] or "",
            "measured_at": r["measured_at"],
        }
        for r in rows
    ]


def _pattern_lines() -> list[str]:
    rows = db.fetchall(
        """SELECT p.symbol, p.direction, p.horizon, p.confidence, p.cascade_from,
                  o.direction_correct, o.actual_move_pct
           FROM shortterm_outcomes o
           JOIN shortterm_picks p ON p.id = o.pick_id"""
    )
    if not rows:
        return ["- No outcomes measured yet."]

    def _rate(c: int, n: int) -> str:
        return f"{c}/{n} ({c / n * 100:.1f}%)" if n else "n/a"

    def _conf_bucket(c: float) -> str:
        if c >= 0.8:
            return "high (>=0.80)"
        if c >= 0.6:
            return "medium (0.60-0.79)"
        return "low (<0.60)"

    bucket_n: Counter = Counter()
    bucket_c: Counter = Counter()
    cascade_n = {"direct": 0, "cascade": 0}
    cascade_c = {"direct": 0, "cascade": 0}
    dir_n: Counter = Counter()
    dir_c: Counter = Counter()
    mkt_n: Counter = Counter()
    mkt_c: Counter = Counter()
    hz_n: Counter = Counter()
    hz_c: Counter = Counter()
    dir_conf_n: Counter = Counter()    # (direction, bucket)
    dir_conf_c: Counter = Counter()

    for r in rows:
        correct = bool(r["direction_correct"])
        d = (r["direction"] or "").lower()
        h = r["horizon"]
        mkt = "MY" if (r["symbol"] or "").endswith(".KL") else "US"
        cb = _conf_bucket(r["confidence"] or 0)

        bucket_n[cb] += 1
        if correct:
            bucket_c[cb] += 1
        kind = "cascade" if r["cascade_from"] else "direct"
        cascade_n[kind] += 1
        if correct:
            cascade_c[kind] += 1
        dir_n[d] += 1
        if correct:
            dir_c[d] += 1
        mkt_n[mkt] += 1
        if correct:
            mkt_c[mkt] += 1
        hz_n[h] += 1
        if correct:
            hz_c[h] += 1
        dir_conf_n[(d, cb)] += 1
        if correct:
            dir_conf_c[(d, cb)] += 1

    lines: list[str] = []

    # Direction
    lines.append("**By direction:**")
    for d in ("bullish", "bearish"):
        if dir_n[d]:
            lines.append(f"- {d}: {_rate(dir_c[d], dir_n[d])}")

    # Horizon
    lines.append("\n**By horizon:**")
    for h in ("24h", "3d", "7d"):
        if hz_n[h]:
            lines.append(f"- {h}: {_rate(hz_c[h], hz_n[h])}")

    # Market
    lines.append("\n**By market:**")
    for mkt in ("MY", "US"):
        if mkt_n[mkt]:
            lines.append(f"- {mkt}: {_rate(mkt_c[mkt], mkt_n[mkt])}")

    # Confidence bucket
    lines.append("\n**By confidence bucket:**")
    for b in ["high (>=0.80)", "medium (0.60-0.79)", "low (<0.60)"]:
        if bucket_n.get(b):
            lines.append(f"- {b}: {_rate(bucket_c[b], bucket_n[b])}")

    # Direction × confidence (calibration-critical slice)
    lines.append("\n**Direction × confidence (calibration check):**")
    for d in ("bullish", "bearish"):
        for b in ["high (>=0.80)", "medium (0.60-0.79)", "low (<0.60)"]:
            n = dir_conf_n.get((d, b), 0)
            if n:
                lines.append(f"- {d} @ {b}: {_rate(dir_conf_c.get((d, b), 0), n)}")

    # Cascade vs direct
    lines.append("\n**By pick type:**")
    for kind in ("direct", "cascade"):
        if cascade_n[kind]:
            lines.append(f"- {kind}: {_rate(cascade_c[kind], cascade_n[kind])}")

    # Actionable rules — flag significant patterns (n>=5, rate<=35% or >=65%)
    rules: list[str] = []
    for d in ("bullish", "bearish"):
        n = dir_n[d]
        if n >= 10:
            pct = dir_c[d] / n * 100
            if pct < 40:
                rules.append(f"- [WARN] {d.title()} picks underperform ({pct:.0f}% / n={n}) — require stronger catalyst before emitting.")
            elif pct > 60:
                rules.append(f"- [OK] {d.title()} picks are working ({pct:.0f}% / n={n}) — lean into this direction when catalysts match.")
    for (d, b), n in dir_conf_n.items():
        if n >= 5:
            pct = dir_conf_c.get((d, b), 0) / n * 100
            if pct < 30:
                rules.append(f"- [WARN] {d} @ {b} is miscalibrated ({pct:.0f}% / n={n}) — cap or skip this bucket.")
    if rules:
        lines.append("\n**Rules derived from outcomes:**")
        lines.extend(rules)

    return lines or ["- Insufficient data."]


def _per_symbol_accuracy_lines(min_n: int = 3, top_k: int = 10) -> list[str]:
    """Rank tickers by their historical hit rate in the short-term pipeline.

    Surfaces the top_k best + top_k worst names so the reasoner can scale
    conviction by prior track record. Symbols with fewer than min_n outcomes
    are excluded (too noisy).
    """
    rows = db.fetchall(
        """SELECT p.symbol, COUNT(*) AS n,
                  SUM(CASE WHEN o.direction_correct=1 THEN 1 ELSE 0 END) AS correct,
                  AVG(o.actual_move_pct) AS avg_actual_move
           FROM shortterm_outcomes o
           JOIN shortterm_picks p ON p.id = o.pick_id
           GROUP BY p.symbol
           HAVING n >= ?""",
        (int(min_n),),
    )
    if not rows:
        return []
    enriched = []
    for r in rows:
        n = r["n"]; c = r["correct"]
        enriched.append({
            "symbol": r["symbol"], "n": n, "correct": c,
            "pct": round(c / n * 100, 1),
            "avg_move": round((r["avg_actual_move"] or 0), 2),
        })
    enriched.sort(key=lambda x: (-x["pct"], -x["n"]))
    best = enriched[:top_k]
    worst = enriched[-top_k:][::-1] if len(enriched) > top_k else []

    lines = ["\n## Per-symbol track record (n >= " + str(min_n) + ")\n"]
    lines.append("**Best:**")
    for e in best:
        lines.append(f"- `{e['symbol']}`: {e['correct']}/{e['n']} = {e['pct']}% "
                     f"(avg actual move {e['avg_move']:+.2f}%)")
    if worst:
        lines.append("\n**Worst — be more skeptical on these:**")
        for e in worst:
            lines.append(f"- `{e['symbol']}`: {e['correct']}/{e['n']} = {e['pct']}% "
                         f"(avg actual move {e['avg_move']:+.2f}%)")
    return lines


def _load_analyst_rules() -> list[dict]:
    """Load cross-system signal rules generated by run_batch_reflection.
    Returns empty list if the file is missing or malformed."""
    import json
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "analyst_signal_rules.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rules", []) or []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _analyst_rules_lines() -> list[str]:
    """Render the analyst-system's batch reflection rules into MEMORY.md.
    Cross-pollinates learned analyst-pipeline rules into the short-term reasoner."""
    rules = _load_analyst_rules()
    if not rules:
        return []
    lines = ["\n## Cross-system rules (from analyst batch reflection)\n",
             "_These patterns were extracted from the long-term analyst's failure analyses. "
             "They apply to short-term picks too unless the news context contradicts them._\n"]
    for r in rules[:8]:  # cap to keep MEMORY.md bounded
        conf = r.get("confidence", "?")
        cond = r.get("condition", "")
        action = r.get("action", "")
        bias = r.get("bias", "")
        n = r.get("supported_by_n_failures", "?")
        lines.append(f"- **[{conf}]** When {cond} → {action}. _(bias: {bias}; n={n})_")
    return lines


def _sanitize_for_memory(text: str) -> str:
    """Strip markdown-breaking chars from past reasoning before embedding in MEMORY.md.
    Past reasoning is Claude's own output but may have been shaped by a prompt-injected
    article; MEMORY.md is loaded into every future prompt, so untrusted content here
    becomes persistent. Collapse whitespace, drop backticks/hashes/pipes, hard-cap len.
    """
    if not text:
        return ""
    cleaned = " ".join(text.split())
    for bad in ("`", "#", "|", "<", ">", "[", "]"):
        cleaned = cleaned.replace(bad, "")
    return cleaned[:MEMORY_REASONING_TRUNCATE]


def _format_outcome_line(o: dict) -> str:
    reasoning = _sanitize_for_memory(o.get("reasoning") or "")
    return (
        f"- **{o['symbol']}** {o['horizon']} {o['direction']} "
        f"(predicted {o['predicted_move_pct']:+.2f}%, actual {o['actual_move_pct']:+.2f}%): "
        f'"{reasoning}"'
    )


def _render_memory(acc_14d: dict, acc_30d: dict, acc_all: dict,
                   hits: list[dict], misses: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: list[str] = [_MEMORY_HEADER, f"_Last updated: {now}_\n"]

    # Render horizon columns dynamically from the active HORIZONS tuple so that
    # horizon additions/removals (we dropped 3d on 2026-04-20) don't break this.
    out.append("## Rolling Accuracy by Horizon\n")
    header = "| Window | " + " | ".join(HORIZONS) + " |"
    out.append(header)
    out.append("|" + "---|" * (len(HORIZONS) + 1))

    def _cell(b: dict) -> str:
        if b["pct"] is None:
            return "—"
        return f"{b['correct']}/{b['n']} ({b['pct']:.1f}%)"

    for label, acc in [("Last 14 days", acc_14d), ("Last 30 days", acc_30d), ("All time", acc_all)]:
        cells = " | ".join(_cell(acc.get(h) or {"n": 0, "correct": 0, "pct": None}) for h in HORIZONS)
        out.append(f"| {label} | {cells} |")

    out.append("\n## Recent Hits")
    if hits:
        out.extend(_format_outcome_line(h) for h in hits)
    else:
        out.append("- _None yet._")

    out.append("\n## Recent Misses")
    if misses:
        out.extend(_format_outcome_line(m) for m in misses)
    else:
        out.append("- _None yet._")

    out.append("\n## Patterns Observed\n")
    out.extend(_pattern_lines())
    out.extend(_per_symbol_accuracy_lines())
    out.extend(_analyst_rules_lines())

    out.append("")
    return "\n".join(out)


def rewrite_memory_md(path: str = MEMORY_MD_PATH) -> None:
    acc_14 = accuracy_for_window(14)
    acc_30 = accuracy_for_window(30)
    acc_all = accuracy_for_window(None)
    hits = _recent_outcomes(n=MEMORY_OUTCOME_LIMIT, correct=True)
    misses = _recent_outcomes(n=MEMORY_OUTCOME_LIMIT, correct=False)
    content = _render_memory(acc_14, acc_30, acc_all, hits, misses)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
    log.info(f"evaluator: MEMORY.md rewritten at {path}")


def purge_old_briefings(days: int = BRIEFING_RETENTION_DAYS) -> int:
    deleted = db.delete_briefings_older_than(days)
    if deleted:
        log.info(f"evaluator: purged {deleted} briefings older than {days} days")
    return deleted
