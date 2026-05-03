"""
Batch pattern reflection — turns accumulated failure analyses into structured
signal rules that are injected into future analyst briefings.

Reads all wrong picks with failure_analysis from the last N days, asks Claude
to identify systematic patterns, and writes structured rules to
data/analyst_signal_rules.json.

prepare_briefing.py reads that file and injects the rules as hard constraints
before Claude makes its next set of picks.

Usage:
    python -m src.data.run_batch_reflection            # last 30 days
    python -m src.data.run_batch_reflection --days 60
"""

import argparse
import json
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "analyst_signal_rules.json"
)
MIN_FAILURES_REQUIRED = 5  # Don't bother if too few data points


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(failures: list[dict], winners: list[dict], total_picks: int, correct_picks: int) -> str:
    accuracy_pct = round(correct_picks / total_picks * 100, 1) if total_picks else 0

    # Summarise failure reasons
    from collections import Counter
    reasons = Counter(f["primary_reason"] for f in failures)
    overweighted = Counter(f["overweighted_signal"] for f in failures)
    underweighted = Counter(f["underweighted_signal"] for f in failures)

    failures_summary = []
    for i, f in enumerate(failures[:30], 1):  # cap at 30 to fit context
        failures_summary.append(
            f"{i}. {f['symbol']} | predicted {f['direction']} | "
            f"actual {'+' if (f.get('actual_move_24h') or 0) > 0 else ''}"
            f"{(f.get('actual_move_24h') or 0):.2f}% | "
            f"reason: {f['primary_reason']} | "
            f"over-weighted: {f['overweighted_signal']} | "
            f"lesson: {f['lesson']}"
        )

    winners_summary = []
    for i, w in enumerate(winners[:30], 1):
        winners_summary.append(
            f"{i}. {w['symbol']} | predicted {w['direction']} ({round((w.get('confidence') or 0)*100)}%) | "
            f"actual {'+' if (w.get('actual_move_24h') or 0) > 0 else ''}"
            f"{(w.get('actual_move_24h') or 0):.2f}%"
        )
    winners_block = chr(10).join(winners_summary) if winners_summary else "(no winners in window)"

    return f"""You are reviewing your own stock predictions to extract systematic rules.
Be a strict empiricist: only emit a rule if the pattern you'd act on is ACTUALLY
absent from the winning picks. Otherwise the "rule" is just hindsight bias.

PERFORMANCE SUMMARY (last {len(failures)} failures out of {total_picks} total picks)
Overall accuracy: {accuracy_pct}%

FAILURE REASON BREAKDOWN:
{json.dumps(dict(reasons), indent=2)}

MOST OVER-WEIGHTED SIGNALS IN FAILURES:
{json.dumps(dict(overweighted), indent=2)}

MOST UNDER-WEIGHTED SIGNALS IN FAILURES:
{json.dumps(dict(underweighted), indent=2)}

INDIVIDUAL FAILURE RECORDS:
{chr(10).join(failures_summary)}

WINNING PICKS in same window (counterfactual — these worked):
{winners_block}

RULE EMISSION GUARDRAILS (read carefully)
1. Before emitting any rule, mentally check: would this rule have ALSO blocked
   the winning picks above? If yes, the rule is rationalisation, not signal.
   Suppress it.
2. Skip rules whose `primary_reason` is `no_clear_signal` — those failures
   were noise, not patterns to learn from.
3. Prefer NO rule over a weak rule. Returning an empty `rules` array is a
   valid outcome and better than emitting noise that constrains future picks.
4. For each emitted rule, fill `n_winners_with_pattern` honestly — count how
   many of the winning picks above match the rule's condition. The rule is
   only credible if `n_winners_with_pattern <= supported_by_n_failures / 3`.

Respond ONLY with this JSON (no markdown):
{{
  "updated_at": "<today's date YYYY-MM-DD>",
  "sample_size": {len(failures)},
  "overall_accuracy_pct": {accuracy_pct},
  "summary": "<2-3 sentence narrative. If patterns are weak or mostly noise, say so explicitly.>",
  "rules": [
    {{
      "id": "rule_1",
      "condition": "<human-readable signal condition, be specific>",
      "bias": "<what mistake you tend to make under this condition>",
      "action": "<what to do differently: skip | reduce_confidence | flip_direction | require_confirmation>",
      "confidence": "<high | medium | low — how sure you are this rule is real>",
      "supported_by_n_failures": <integer>,
      "n_winners_with_pattern": <integer — winners above that ALSO match this condition>
    }}
  ]
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
        log.warning("Claude CLI not found")
        return None
    try:
        result = subprocess.run(
            [cmd, "-p", "-", "--output-format", "json", "--max-turns", "1", "--allowedTools", ""],
            capture_output=True, text=True, timeout=120,
            input=prompt, shell=cmd.endswith(".cmd"),
            cwd=os.path.expanduser("~"),
        )
        if result.returncode != 0:
            log.warning("Claude returned code %d", result.returncode)
            return None

        output = result.stdout.strip()
        try:
            cli_resp = json.loads(output)
            text = cli_resp.get("result", "") if isinstance(cli_resp, dict) else str(cli_resp)
        except json.JSONDecodeError:
            text = output

        if "```" in text:
            import re
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()

        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        log.warning("Claude call failed: %s", e)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def _filter_rules_by_counterfactual(rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop rules where the pattern is too prevalent in winners to be a real signal.
    Threshold: n_winners_with_pattern must be <= supported_by_n_failures / 3.
    Returns (kept, dropped)."""
    kept, dropped = [], []
    for r in rules:
        n_fail = r.get("supported_by_n_failures") or 0
        n_win = r.get("n_winners_with_pattern")
        # If field is missing, treat as untrustworthy and drop (forces Claude to fill it)
        if n_win is None:
            r["_dropped_reason"] = "missing n_winners_with_pattern"
            dropped.append(r)
            continue
        if n_fail < 3:
            r["_dropped_reason"] = f"too few failures ({n_fail} < 3)"
            dropped.append(r)
            continue
        if n_win > n_fail / 3:
            r["_dropped_reason"] = f"counterfactual: {n_win} winners match vs {n_fail} failures"
            dropped.append(r)
            continue
        kept.append(r)
    return kept, dropped


def run(days: int = 30) -> dict:
    from src.database import (
        init_db, get_wrong_picks_with_analysis, get_analyst_accuracy,
        get_analyst_outcomes,
    )

    init_db()

    failures = get_wrong_picks_with_analysis(days=days)
    if len(failures) < MIN_FAILURES_REQUIRED:
        log.info(
            "Only %d analysed failures (need %d) — skipping batch reflection",
            len(failures), MIN_FAILURES_REQUIRED
        )
        return {"rules": 0, "failures_used": len(failures)}

    accuracy = get_analyst_accuracy(days=days)
    total_picks = accuracy.get("total", 0)
    correct_picks = accuracy.get("correct", 0)

    # Winning picks for counterfactual comparison
    winners = [
        o for o in get_analyst_outcomes(days=days)
        if o.get("is_correct") == 1
    ]

    log.info(
        "Running batch reflection on %d failures vs %d winners (%d total, %.1f%% accuracy)",
        len(failures), len(winners), total_picks,
        round(correct_picks / total_picks * 100, 1) if total_picks else 0
    )

    prompt = _build_prompt(failures, winners, total_picks, correct_picks)
    rules_data = _call_claude(prompt)

    if not rules_data:
        log.warning("No rules returned from Claude")
        return {"rules": 0, "failures_used": len(failures)}

    raw_rules = rules_data.get("rules", [])
    kept, dropped = _filter_rules_by_counterfactual(raw_rules)
    rules_data["rules"] = kept
    rules_data["dropped_rules"] = dropped  # kept for transparency / debugging

    log.info("Generated %d rules; %d kept, %d dropped by counterfactual guard",
             len(raw_rules), len(kept), len(dropped))
    for r in kept:
        log.info("  KEEP [%s] %s → %s (fail=%d, win=%d)",
                 r.get("confidence", "?"), r.get("condition", ""), r.get("action", ""),
                 r.get("supported_by_n_failures", 0), r.get("n_winners_with_pattern", 0))
    for r in dropped:
        log.info("  DROP %s — %s", r.get("condition", ""), r.get("_dropped_reason", ""))

    # Write to disk
    os.makedirs(os.path.dirname(os.path.abspath(RULES_PATH)), exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(rules_data, f, indent=2, ensure_ascii=False)

    log.info("Signal rules written to %s", RULES_PATH)
    return {
        "rules": len(kept),
        "dropped": len(dropped),
        "failures_used": len(failures),
        "winners_used": len(winners),
        "summary": rules_data.get("summary", ""),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30,
                   help="How many days of failures to include (default 30)")
    args = p.parse_args()
    run(days=args.days)
