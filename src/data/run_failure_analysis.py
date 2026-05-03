"""
Per-pick failure analyser.

For each wrong analyst pick without a failure_analysis, calls Claude to
produce a structured JSON explanation of WHY the prediction failed.

Stores the result in analyst_outcomes.failure_analysis.
Also updates data/analyst_sample_weights.json so the weekly ML retrain
can boost sample weights for those stock+date combinations.

Usage:
    python -m src.data.run_failure_analysis           # up to 20 at a time
    python -m src.data.run_failure_analysis --limit 5
"""

import argparse
import json
import logging
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SAMPLE_WEIGHTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "analyst_sample_weights.json"
)

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a trading post-mortem analyst. Given a failed stock prediction,
identify exactly why it was wrong using only the information provided.
Respond with a single JSON object — no markdown, no explanation outside the JSON."""

def _build_prompt(pick: dict) -> str:
    symbol = pick["symbol"]
    direction = pick["direction"]
    confidence = round((pick.get("confidence") or 0) * 100)
    predicted_move = pick.get("predicted_move") or 0
    actual_move = pick.get("actual_move_24h") or 0
    entry = pick.get("entry_price") or 0
    exit_p = pick.get("exit_price") or 0
    reasoning = pick.get("reasoning") or ""
    report_created = pick.get("report_created") or ""
    peak_fav = pick.get("peak_favorable_move")
    max_adv = pick.get("max_adverse_move")
    dir_hit = pick.get("directional_hit")

    # Pull technicals from picks_json if available
    technicals_str = ""
    try:
        picks_list = json.loads(pick.get("picks_json") or "[]")
        matched = next((p for p in picks_list if p.get("symbol") == symbol), None)
        if matched:
            t = matched.get("technicals") or matched.get("technical_setup") or {}
            if isinstance(t, dict) and t:
                technicals_str = "\n".join(
                    f"  {k}: {v}" for k, v in list(t.items())[:8]
                )
            bull = matched.get("bull_case") or []
            bear = matched.get("bear_case") or []
            risks = matched.get("key_risks") or []
            if bull:
                reasoning += f"\nBull case: {'; '.join(bull[:3])}"
            if bear:
                reasoning += f"\nBear case: {'; '.join(bear[:3])}"
            if risks:
                reasoning += f"\nKey risks: {'; '.join(risks[:3])}"
    except Exception:
        pass

    actual_dir = "bullish" if actual_move > 0 else "bearish"

    if peak_fav is None or max_adv is None:
        intra_block = "Intra-window extremes: (not measured for this pick)"
    else:
        hit_str = "yes" if dir_hit else "no"
        intra_block = (
            f"Peak in your favour: {peak_fav:+.2f}%   (best the stock got vs entry, in your direction)\n"
            f"Max adverse move:    {max_adv:+.2f}%   (worst the stock got vs entry, against you)\n"
            f"Directional hit:     {hit_str}   (stock moved >=0.5% in your direction at some point)"
        )

    return f"""{SYSTEM_PROMPT}

FAILED PREDICTION
-----------------
Symbol:       {symbol}
Report date:  {report_created[:10]}
Predicted:    {direction}  ({'+' if predicted_move >= 0 else ''}{predicted_move:.1f}% move, {confidence}% confidence)
Actual:       {actual_dir}  ({'+' if actual_move >= 0 else ''}{actual_move:.2f}% in 24h close-to-close)
Entry price:  {entry:.4f}
Exit price:   {exit_p:.4f}

{intra_block}

Original reasoning:
{reasoning}

Signal context at prediction time:
{technicals_str if technicals_str else '(not available)'}

GUIDANCE on primary_reason
- IMPORTANT: if `Directional hit: yes` AND close-to-close was wrong, this is a
  TIMING failure — pick `timing`. The direction was right; the call would have
  worked with a tighter exit. Do NOT blame metrics for a timing failure.
- Default to `no_clear_signal` if the move looks like noise / nothing in the data
  predicted it. A 24h close move of <2% with no directional hit and no obvious
  catalyst usually IS noise — do NOT confabulate a metric-based reason.
- Use `narrative_momentum` when the stock kept moving on persistent retail/
  institutional narrative (popularity, hype, story stocks like AAPL/NVDA/Top
  Glove rallies) that the bot under-weighted vs metrics like PE/RSI.
- Use `operator_activity` for Bursa stocks where concentrated ownership /
  insider accumulation likely drove the move — invisible in standard signals.
- Only blame metric-flavoured reasons (`signal_conflict`, `overconfidence`,
  `momentum_reversal`) when the metrics actually predicted the wrong direction
  cleanly AND directional hit was no. If metrics were ambiguous, prefer
  `no_clear_signal`.

Analyse the failure and respond ONLY with this JSON:
{{
  "primary_reason": "<one of: signal_conflict | overconfidence | macro_ignored | news_misread | timing | momentum_reversal | low_liquidity | narrative_momentum | operator_activity | no_clear_signal | other>",
  "overweighted_signal": "<one of: technical | sentiment | momentum | macro | news | fundamentals | none>",
  "underweighted_signal": "<one of: technical | sentiment | momentum | macro | news | fundamentals | narrative | none>",
  "lesson": "<one concrete rule for next time, max 20 words. Use 'none' if reason was no_clear_signal>",
  "market_condition": "<one of: trending | ranging | volatile | gap_day | unknown>"
}}"""


# ── Claude call ───────────────────────────────────────────────────────────────

def _get_claude_cmd() -> str | None:
    candidates = [
        "claude",
        os.path.expanduser("~\\AppData\\Roaming\\npm\\claude.cmd"),
        os.path.expanduser("~/.npm-global/bin/claude"),
        "/usr/local/bin/claude",
    ]
    for cmd in candidates:
        try:
            r = subprocess.run(
                [cmd, "--version"], capture_output=True, timeout=5, shell=cmd.endswith(".cmd")
            )
            if r.returncode == 0:
                return cmd
        except Exception:
            pass
    return None


def _call_claude(prompt: str) -> dict | None:
    cmd = _get_claude_cmd()
    if not cmd:
        log.warning("Claude CLI not found — skipping analysis")
        return None
    try:
        result = subprocess.run(
            [cmd, "-p", "-", "--output-format", "json", "--max-turns", "1", "--allowedTools", ""],
            capture_output=True, text=True, timeout=60,
            input=prompt, shell=cmd.endswith(".cmd"),
            cwd=os.path.expanduser("~"),
        )
        if result.returncode != 0:
            log.warning("Claude returned code %d: %s", result.returncode, result.stderr[:100])
            return None

        output = result.stdout.strip()
        try:
            cli_resp = json.loads(output)
            text = cli_resp.get("result", "") if isinstance(cli_resp, dict) else str(cli_resp)
        except json.JSONDecodeError:
            text = output

        # Strip markdown fences
        if "```" in text:
            import re
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()

        # Extract first JSON object
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        log.warning("Claude call failed: %s", e)
    return None


# ── Sample weights ────────────────────────────────────────────────────────────

def _load_sample_weights() -> dict:
    if os.path.exists(SAMPLE_WEIGHTS_PATH):
        try:
            with open(SAMPLE_WEIGHTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_sample_weights(weights: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(SAMPLE_WEIGHTS_PATH)), exist_ok=True)
    with open(SAMPLE_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(limit: int = 20) -> dict:
    from src.database import (
        init_db,
        get_wrong_picks_without_analysis,
        save_failure_analysis,
        get_analyst_outcomes,
    )
    init_db()

    wrong_picks = get_wrong_picks_without_analysis(limit=limit)
    if not wrong_picks:
        log.info("No unanalysed wrong picks found")
        return {"analysed": 0}

    log.info("Found %d wrong pick(s) to analyse", len(wrong_picks))

    sample_weights = _load_sample_weights()
    analysed = 0

    for pick in wrong_picks:
        outcome_id = pick["id"]
        symbol = pick["symbol"]
        report_date = (pick.get("report_created") or "")[:10]
        log.info("  Analysing %s (outcome id=%d)...", symbol, outcome_id)

        prompt = _build_prompt(pick)
        analysis = _call_claude(prompt)

        if analysis:
            # Validate expected keys
            expected = {"primary_reason", "overweighted_signal", "underweighted_signal",
                        "lesson", "market_condition"}
            if not expected.issubset(analysis.keys()):
                log.warning("    Incomplete analysis for %s — skipping", symbol)
                continue

            save_failure_analysis(outcome_id, analysis)
            log.info("    %s → %s (over: %s, under: %s)",
                     symbol, analysis["primary_reason"],
                     analysis["overweighted_signal"], analysis["underweighted_signal"])

            # Boost sample weight for this stock+date in ML training
            weight_key = f"{symbol}_{report_date}"
            sample_weights[weight_key] = 3.0  # wrong pick → strong learning signal
            analysed += 1
        else:
            log.warning("    No analysis returned for %s", symbol)

        time.sleep(1)  # rate-limit Claude calls

    # Also add mild weight boost for correct picks (reinforce good signals)
    try:
        from src.database import get_analyst_outcomes
        correct = [o for o in get_analyst_outcomes(days=30) if o.get("is_correct") == 1]
        for o in correct:
            # Pull report date from DB join — created_at is in analyst_reports
            from src.database import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT created_at FROM analyst_reports WHERE report_id = ?",
                (o["report_id"],)
            ).fetchone()
            conn.close()
            if row:
                report_date = str(row["created_at"])[:10]
                key = f"{o['symbol']}_{report_date}"
                if key not in sample_weights:
                    sample_weights[key] = 1.5  # correct pick → mild reinforcement
    except Exception as e:
        log.warning("Could not boost correct pick weights: %s", e)

    _save_sample_weights(sample_weights)
    log.info("Sample weights updated: %d entries in %s", len(sample_weights), SAMPLE_WEIGHTS_PATH)
    log.info("Done: %d/%d picks analysed", analysed, len(wrong_picks))
    return {"analysed": analysed, "total": len(wrong_picks)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=20,
                   help="Max wrong picks to analyse per run (default 20)")
    args = p.parse_args()
    run(limit=args.limit)
