"""
One-shot rule-based evaluator.

Finds analyst reports older than --hours-min (default 24) with no outcomes yet,
fetches the 24h-later price for each pick, determines correctness by
direction-vs-actual-move, and writes rows to analyst_outcomes.

Designed for both manual runs and scheduled crons (3x/day matching report times).
No Claude-in-the-loop — the reflection file is not updated here; the separate
daily-evaluation Claude task still handles that if wired up.

Usage:
    python -m src.data.run_evaluation              # evaluate anything >=23h old
    python -m src.data.run_evaluation --hours-min 24   # strict 24h gate

Default is 23h (not 24) because the claude-analyst task takes a few minutes,
so yesterday's 09:15 schedule produces a row with created_at ~09:20. Evaluating
at today's 09:20 with a 24h gate would miss it; 23h gives a safe margin.
"""

import argparse
import logging
import math
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return default


from src.evaluation.correctness import is_correct_int as _is_correct


def evaluate(hours_min: int = 23) -> dict:
    import yfinance as yf
    from src.database import init_db, get_unevaluated_reports, save_analyst_outcome

    init_db()

    reports = get_unevaluated_reports(hours_min=hours_min)
    if not reports:
        log.info("No reports older than %sh awaiting evaluation", hours_min)
        return {"reports": 0, "picks": 0, "correct": 0}

    log.info("Evaluating %d report(s) older than %sh", len(reports), hours_min)

    total_picks = 0
    correct = 0
    reports_processed = 0

    for report in reports:
        report_id = report["report_id"]
        picks = report.get("picks", [])
        if not picks:
            continue

        report_picks = 0
        for pick in picks:
            symbol = pick.get("symbol", "")
            entry_price = _safe_float(pick.get("current_price", 0))
            if not symbol or not entry_price:
                continue

            try:
                # 1h bars over 2 days = ~14-26 intraday bars depending on
                # weekend/holiday position. Lets us see intra-period extremes
                # so a directionally-right call that reversed isn't logged
                # identically to a call that was wrong from the start.
                hist = yf.Ticker(symbol).history(period="2d", interval="1h")
                if hist.empty:
                    log.warning("No price data for %s — skipping", symbol)
                    continue
                exit_price = _safe_float(hist["Close"].iloc[-1])
                high_in_window = _safe_float(hist["High"].max())
                low_in_window = _safe_float(hist["Low"].min())
                time.sleep(0.25)
            except Exception as e:
                log.warning("Price fetch failed for %s: %s", symbol, e)
                continue

            if not exit_price:
                continue

            # Skip when price hasn't moved — happens on weekends / holidays when
            # yfinance returns the last trading day's close for both entry and "24h later".
            # Recording these as losses would tank the scorecard with garbage data.
            if exit_price == entry_price:
                log.info("  skip %s: entry == exit (market closed or pre-open?)", symbol)
                continue

            actual_move = round((exit_price - entry_price) / entry_price * 100, 2)
            direction = pick.get("direction", "")
            is_correct = _is_correct(direction, actual_move)

            # Intra-window extremes (sign convention: positive = in your favour,
            # negative = against you, for either bullish or bearish picks).
            if direction == "bearish":
                peak_favorable_move = round((entry_price - low_in_window) / entry_price * 100, 2)
                max_adverse_move = round((entry_price - high_in_window) / entry_price * 100, 2)
            else:  # bullish (default for unknown — same as actual_move sign)
                peak_favorable_move = round((high_in_window - entry_price) / entry_price * 100, 2)
                max_adverse_move = round((low_in_window - entry_price) / entry_price * 100, 2)
            directional_hit = 1 if peak_favorable_move >= 0.5 else 0

            save_analyst_outcome(
                report_id=report_id,
                symbol=symbol,
                direction=direction,
                confidence=_safe_float(pick.get("confidence", 0)),
                predicted_move=_safe_float(pick.get("predicted_move", 0)),
                actual_move=actual_move,
                entry_price=entry_price,
                exit_price=exit_price,
                is_correct=is_correct,
                reasoning="rule-based eval",
                high_in_window=high_in_window,
                low_in_window=low_in_window,
                peak_favorable_move=peak_favorable_move,
                max_adverse_move=max_adverse_move,
                directional_hit=directional_hit,
            )

            total_picks += 1
            report_picks += 1
            if is_correct:
                correct += 1

        if report_picks:
            reports_processed += 1
            log.info("  %s (%s %s): %d picks saved", report_id, report.get("run_type"), report.get("market"), report_picks)

    accuracy = round(correct / total_picks * 100, 1) if total_picks else None
    log.info("Done: %d reports, %d picks, %d correct (%s%% )", reports_processed, total_picks, correct, accuracy)
    return {"reports": reports_processed, "picks": total_picks, "correct": correct, "accuracy_pct": accuracy}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hours-min", type=int, default=23)
    args = p.parse_args()
    evaluate(hours_min=args.hours_min)
