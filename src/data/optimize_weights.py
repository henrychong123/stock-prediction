"""
Signal Weight Optimizer — uses historical data to find the optimal
weight combination for each signal type that maximizes prediction accuracy.

Method: scipy.optimize.minimize with constraints (weights sum to 1, min 5% each)
Optimizes separately for US and MY markets.

Usage:
    python src/data/optimize_weights.py              # optimize both markets
    python src/data/optimize_weights.py --market US  # US only
    python src/data/optimize_weights.py --market MY  # MY only

Output: models/optimized_weights.json
"""

import sys
import os
import json
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import numpy as np
import pandas as pd
from scipy.optimize import minimize, differential_evolution
from sklearn.metrics import accuracy_score

from src.database import init_db, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR = Path("models")

# Signal names matching the predictor output
SIGNAL_NAMES = [
    "technical",
    "news_sentiment",
    "social_sentiment",
    "geopolitical",
    "market_momentum",
    "ml_model",
]

# Thresholds for direction classification (matching train_model.py)
UP_THRESHOLD = 1.0
DOWN_THRESHOLD = -1.0


def load_training_data(market: str = None) -> pd.DataFrame:
    """Load training data with indicator columns."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM training_data ORDER BY symbol, date", conn)
    conn.close()

    if market:
        if market.upper() == "MY":
            df = df[df["symbol"].str.endswith(".KL")]
        elif market.upper() == "US":
            df = df[~df["symbol"].str.endswith(".KL")]

    # Drop rows without target
    df = df.dropna(subset=["price_change_5d"])
    log.info(f"Loaded {len(df):,} rows for {market or 'ALL'} market")
    return df


def compute_signal_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute simulated signal scores for each row from indicators.

    Each signal score is in [-1, +1] range, matching how combine_signals() works.
    """
    scores = pd.DataFrame(index=df.index)

    # ── Technical signal (from RSI, MACD, SMA, BB, momentum) ──────────
    tech = np.zeros(len(df))

    # MACD crossover
    macd_bull = (df["macd"] > df["signal_line"]).astype(float) * 0.2
    macd_bear = (df["macd"] <= df["signal_line"]).astype(float) * -0.2
    tech += macd_bull + macd_bear

    # RSI
    tech += (df["rsi"] < 30).astype(float) * 0.25
    tech += (df["rsi"] > 70).astype(float) * -0.25

    # SMA cross
    tech += (df["sma_20"] > df["sma_50"]).astype(float) * 0.2
    tech += (df["sma_20"] <= df["sma_50"]).astype(float) * -0.2

    # Bollinger
    tech += (df["close"] < df["bb_lower"]).astype(float) * 0.2
    tech += (df["close"] > df["bb_upper"]).astype(float) * -0.2

    # Stochastic
    tech += (df["stoch_k"] < 20).astype(float) * 0.15
    tech += (df["stoch_k"] > 80).astype(float) * -0.15

    # CCI
    tech += (df["cci"] < -100).astype(float) * 0.1
    tech += (df["cci"] > 100).astype(float) * -0.1

    # ADX amplification
    adx_strong = (df["adx"] > 25).astype(float)
    tech = tech * (1 + adx_strong * 0.3)

    scores["technical"] = tech.clip(-1, 1)

    # ── News sentiment (simulated from momentum/volatility as proxy) ──
    # We don't have historical news sentiment, so use price momentum as proxy
    momentum_5d = df["close"].pct_change(5) * 10  # scale to [-1, 1] range
    scores["news_sentiment"] = momentum_5d.clip(-1, 1).fillna(0)

    # ── Social sentiment (proxy: volume anomaly + momentum) ───────────
    vol_avg = df["volume"].rolling(20, min_periods=1).mean()
    vol_ratio = (df["volume"] / vol_avg.clip(lower=1)) - 1  # excess volume
    price_mom = df["close"].pct_change(3) * 5
    scores["social_sentiment"] = ((vol_ratio * 0.3 + price_mom * 0.7).clip(-1, 1)).fillna(0)

    # ── Geopolitical (proxy: VIX-based fear gauge) ────────────────────
    if "vix_close" in df.columns:
        vix = df["vix_close"].fillna(20)
        # VIX < 15 = calm (bullish), VIX > 30 = fear (bearish)
        geo = ((20 - vix) / 15).clip(-1, 1)
        scores["geopolitical"] = geo
    else:
        scores["geopolitical"] = 0

    # ── Market momentum (from daily returns + trend) ──────────────────
    ret_5d = df["daily_return"].rolling(5, min_periods=1).mean() * 50
    sma_trend = ((df["close"] - df["sma_50"]) / df["sma_50"].clip(lower=0.01)) * 5
    scores["market_momentum"] = ((ret_5d * 0.5 + sma_trend * 0.5).clip(-1, 1)).fillna(0)

    # ── ML model (use actual stored prediction if trained, else use RSI+MACD combo) ──
    rsi_score = ((50 - df["rsi"]) / 50).clip(-1, 1)  # RSI below 50 = bullish
    macd_score = (df["macd_hist"] * 100).clip(-1, 1)  # histogram direction
    ichimoku_score = np.zeros(len(df))
    span_top = df[["ichi_span_a", "ichi_span_b"]].max(axis=1)
    span_bot = df[["ichi_span_a", "ichi_span_b"]].min(axis=1)
    ichimoku_score = np.where(df["close"] > span_top, 0.5, np.where(df["close"] < span_bot, -0.5, 0))

    scores["ml_model"] = ((rsi_score * 0.3 + macd_score.fillna(0) * 0.3 + ichimoku_score * 0.4).clip(-1, 1)).fillna(0)

    return scores


def simulate_prediction(signal_scores: pd.DataFrame, weights: np.ndarray) -> np.ndarray:
    """Simulate combined prediction using given weights.
    Returns predicted direction: 1=UP, 0=FLAT, -1=DOWN
    """
    # Normalize weights to sum to 1
    w = weights / weights.sum()

    # Weighted combination
    combined = np.zeros(len(signal_scores))
    for i, col in enumerate(SIGNAL_NAMES):
        if col in signal_scores.columns:
            combined += signal_scores[col].values * w[i]

    # Map to direction
    preds = np.zeros(len(combined), dtype=int)
    preds[combined > 0.1] = 1    # UP
    preds[combined < -0.1] = -1  # DOWN
    return preds


def get_actual_direction(df: pd.DataFrame) -> np.ndarray:
    """Get actual 5-day direction: 1=UP, 0=FLAT, -1=DOWN"""
    actual = np.zeros(len(df), dtype=int)
    actual[df["price_change_5d"] > UP_THRESHOLD] = 1
    actual[df["price_change_5d"] < DOWN_THRESHOLD] = -1
    return actual


def objective(weights: np.ndarray, signal_scores: pd.DataFrame,
              actual: np.ndarray) -> float:
    """Objective function to minimize (negative accuracy)."""
    preds = simulate_prediction(signal_scores, weights)
    acc = accuracy_score(actual, preds)
    return -acc  # minimize negative accuracy = maximize accuracy


def optimize_market(df: pd.DataFrame, market_name: str) -> dict:
    """Optimize weights for one market."""
    log.info(f"\n{'='*50}")
    log.info(f"Optimizing weights for {market_name} market ({len(df):,} samples)")
    log.info(f"{'='*50}")

    signal_scores = compute_signal_scores(df)
    actual = get_actual_direction(df)

    n_signals = len(SIGNAL_NAMES)

    # ── Default weights baseline ──────────────────────────────────────
    from config.settings import SIGNAL_WEIGHTS, MY_SIGNAL_WEIGHTS
    default_w = MY_SIGNAL_WEIGHTS if market_name == "MY" else SIGNAL_WEIGHTS
    default_arr = np.array([default_w.get(s, 0.1) for s in SIGNAL_NAMES])
    default_arr = default_arr / default_arr.sum()

    default_preds = simulate_prediction(signal_scores, default_arr)
    default_acc = accuracy_score(actual, default_preds)
    log.info(f"Default weights accuracy: {default_acc:.4f}")

    # ── Optimization using differential evolution (global optimizer) ──
    bounds = [(0.05, 0.50)] * n_signals  # each weight between 5% and 50%

    # Constraint: weights sum to 1
    def constraint_sum(w):
        return w.sum() - 1.0

    log.info("Running differential evolution optimization...")

    result = differential_evolution(
        objective,
        bounds=bounds,
        args=(signal_scores, actual),
        maxiter=200,
        seed=42,
        tol=1e-6,
        polish=True,
        workers=1,
    )

    # Normalize result to sum to 1
    opt_weights = result.x / result.x.sum()
    opt_acc = -result.fun

    log.info(f"Optimized accuracy: {opt_acc:.4f} (improvement: {opt_acc - default_acc:+.4f})")

    # Also try scipy minimize with multiple starting points
    log.info("Refining with scipy minimize...")
    best_acc = opt_acc
    best_weights = opt_weights.copy()

    for trial in range(10):
        x0 = np.random.dirichlet(np.ones(n_signals))  # random starting point on simplex
        try:
            res = minimize(
                objective,
                x0,
                args=(signal_scores, actual),
                method="SLSQP",
                bounds=bounds,
                constraints={"type": "eq", "fun": constraint_sum},
                options={"maxiter": 500},
            )
            if res.success:
                w = res.x / res.x.sum()
                acc = -res.fun
                if acc > best_acc:
                    best_acc = acc
                    best_weights = w
        except Exception:
            continue

    log.info(f"Best accuracy: {best_acc:.4f}")

    # Build result
    weight_dict = {}
    for i, name in enumerate(SIGNAL_NAMES):
        weight_dict[name] = round(float(best_weights[i]), 4)

    log.info(f"\nOptimized weights for {market_name}:")
    for name, w in sorted(weight_dict.items(), key=lambda x: -x[1]):
        bar = "#" * int(w * 50)
        log.info(f"  {name:20s} {w:.1%} {bar}")

    return {
        "weights": weight_dict,
        "accuracy_before": round(float(default_acc), 4),
        "accuracy_after": round(float(best_acc), 4),
        "improvement": round(float(best_acc - default_acc), 4),
        "samples": len(df),
    }


def run(market: str = None):
    init_db()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    if market and market.upper() in ("US", "MY"):
        df = load_training_data(market.upper())
        results[market.upper()] = optimize_market(df, market.upper())
    else:
        # Optimize both markets
        for m in ["US", "MY"]:
            df = load_training_data(m)
            if len(df) > 100:
                results[m] = optimize_market(df, m)
            else:
                log.warning(f"Skipping {m}: insufficient data ({len(df)} rows)")

    # Save results
    output = {
        **results,
        "optimized_at": datetime.now().isoformat(),
        "method": "differential_evolution + SLSQP refinement",
        "signal_names": SIGNAL_NAMES,
    }

    path = MODEL_DIR / "optimized_weights.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    log.info(f"\nSaved to {path}")

    # Summary
    log.info("\n" + "=" * 50)
    log.info("OPTIMIZATION SUMMARY")
    log.info("=" * 50)
    for m, r in results.items():
        log.info(f"  {m}: {r['accuracy_before']:.1%} → {r['accuracy_after']:.1%} ({r['improvement']:+.1%})")


if __name__ == "__main__":
    args = sys.argv[1:]
    market = None
    for i, a in enumerate(args):
        if a == "--market" and i + 1 < len(args):
            market = args[i + 1]
    run(market=market)
