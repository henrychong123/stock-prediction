"""
ML Model Trainer — trains stock prediction models using historical data.

Models:
1. XGBoost classifier: predicts direction (UP / DOWN / FLAT)
2. XGBoost regressor: predicts 5-day % change magnitude
3. LightGBM classifier: ensemble member for direction

Outputs:
- models/direction_xgb.json        (XGBoost direction classifier)
- models/direction_lgbm.txt        (LightGBM direction classifier)
- models/magnitude_xgb.json        (XGBoost magnitude regressor)
- models/feature_importance.csv     (ranked feature importance)
- models/metrics.json               (accuracy, F1, confusion matrix)

Usage:
    python src/data/train_model.py                  # train on all data
    python src/data/train_model.py --market MY      # Bursa stocks only
    python src/data/train_model.py --market US      # US stocks only
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score, f1_score, classification_report,
    mean_absolute_error, root_mean_squared_error, r2_score,
)
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import lightgbm as lgb
import joblib

from src.database import init_db, get_connection
from config.industries import CANONICAL_INDUSTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR = Path("models")

# ── Feature Configuration ─────────────────────────────────────────────────────

FEATURE_COLS = [
    # Price-based
    "open", "high", "low", "close", "volume",
    # Moving averages
    "sma_20", "sma_50", "ema_9", "ema_12", "ema_21", "ema_26",
    # MACD
    "macd", "signal_line", "macd_hist",
    # Oscillators
    "rsi", "stoch_k", "stoch_d", "williams_r",
    # Bollinger
    "bb_upper", "bb_lower",
    # Trend
    "adx", "plus_di", "minus_di",
    # Volatility & Volume
    "atr", "obv", "vwap", "cci", "psar",
    # Ichimoku
    "ichi_tenkan", "ichi_kijun", "ichi_span_a", "ichi_span_b",
    # Misc
    "volatility", "daily_return",
    # Market context
    "market_index_close", "vix_close",
    # Macro (from collect_historical.py — Phase 2)
    "treasury_10y", "treasury_2y", "yield_spread",
    "dxy_close",
    "sector_etf_return",
    "oil_close", "gold_close", "copper_close",
]

# Sentiment features (may be null for historical data)
SENTIMENT_COLS = [
    "news_sentiment", "news_count",
    "reddit_sentiment", "reddit_count",
    "figure_sentiment", "figure_count",
    "gdelt_tone", "fear_greed",
]

# Earnings features (computed from earnings_history in load_data)
EARNINGS_COLS = [
    "earnings_surprise",       # most recent EPS surprise %
    "days_since_earnings",     # trading days since last report
    "beat_rate_4q",            # % of last 4 quarters that were beats
    "earnings_momentum",       # trend: avg of last 2 surprises - avg of prior 2
]

INSIDER_COLS = [
    "insider_buy_ratio",       # buy transactions / total transactions (90-day window)
]

ANALYST_COLS = [
    "analyst_score",           # consensus score from -1 (all sell) to +1 (all buy)
]

# Target thresholds
UP_THRESHOLD = 1.0    # > 1% = UP
DOWN_THRESHOLD = -1.0  # < -1% = DOWN

# ── Data Loading ──────────────────────────────────────────────────────────────

def _merge_earnings_features(df: pd.DataFrame, earnings_df: pd.DataFrame) -> pd.DataFrame:
    """Compute earnings features for each training row based on earnings history."""
    # Initialize columns with defaults
    df["earnings_surprise"] = 0.0
    df["days_since_earnings"] = 999
    df["beat_rate_4q"] = 0.0
    df["earnings_momentum"] = 0.0

    for symbol in df["symbol"].unique():
        sym_earnings = earnings_df[earnings_df["symbol"] == symbol].copy()
        if sym_earnings.empty:
            continue

        sym_mask = df["symbol"] == symbol
        sym_dates = df.loc[sym_mask, "date"].values

        # Sort earnings by date
        sym_earnings = sym_earnings.sort_values("date")
        earn_dates = sym_earnings["date"].values
        surprises = sym_earnings["surprise_pct"].fillna(0).values

        for idx in df.loc[sym_mask].index:
            row_date = df.at[idx, "date"]

            # Find earnings on or before this date
            past = sym_earnings[sym_earnings["date"] <= row_date]
            if past.empty:
                continue

            # Most recent earnings surprise
            latest_idx = len(past) - 1
            df.at[idx, "earnings_surprise"] = surprises[latest_idx] if latest_idx < len(surprises) else 0

            # Days since last earnings
            try:
                last_earn_date = pd.Timestamp(past.iloc[-1]["date"])
                row_ts = pd.Timestamp(row_date)
                df.at[idx, "days_since_earnings"] = max((row_ts - last_earn_date).days, 0)
            except Exception:
                pass

            # Beat rate (last 4 quarters)
            recent = past.tail(4)
            beats = (recent["surprise_pct"].fillna(0) > 0).sum()
            df.at[idx, "beat_rate_4q"] = beats / len(recent)

            # Earnings momentum (avg of last 2 vs avg of prior 2)
            if len(past) >= 4:
                recent_avg = past["surprise_pct"].fillna(0).iloc[-2:].mean()
                prior_avg = past["surprise_pct"].fillna(0).iloc[-4:-2].mean()
                df.at[idx, "earnings_momentum"] = recent_avg - prior_avg

    return df


def _build_symbol_industry_map() -> dict[str, str]:
    """Build a mapping from stock symbol to canonical industry name.
    Uses GICS Sector from S&P 500 CSV for US stocks, BURSA_INDUSTRIES for MY stocks."""
    from config.settings import BURSA_INDUSTRIES

    # GICS Sector → Canonical industry name
    GICS_TO_CANONICAL = {
        "Information Technology": "Technology",
        "Health Care": "Healthcare",
        "Financials": "Banking & Finance",
        "Consumer Discretionary": "Consumer & Retail",
        "Communication Services": "Telecommunications",
        "Industrials": "Industrial & Manufacturing",
        "Consumer Staples": "Consumer & Retail",
        "Energy": "Oil & Gas",
        "Utilities": "Utilities & Energy",
        "Real Estate": "Property & Construction",
        "Materials": "Commodities & Mining",
    }

    mapping = {}

    # Bursa stocks → industry from BURSA_INDUSTRIES
    for industry, data in BURSA_INDUSTRIES.items():
        for s in data["stocks"]:
            mapping[s["symbol"]] = industry

    # S&P 500 stocks → industry from CSV via GICS Sector
    try:
        from pathlib import Path
        import csv, io
        csv_path = Path("data/sp500_tickers.csv")
        if csv_path.exists():
            text = csv_path.read_text(encoding="utf-8")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                sym = row.get("Symbol", "").strip()
                gics = row.get("GICS Sector", "").strip()
                if sym and gics:
                    canonical = GICS_TO_CANONICAL.get(gics, "")
                    if canonical:
                        mapping[sym] = canonical
    except Exception:
        pass

    return mapping


def _merge_gdelt_features(df: pd.DataFrame, gdelt_df: pd.DataFrame) -> pd.DataFrame:
    """Backfill GDELT tone per stock by mapping symbol → industry → GDELT tone for that date."""
    sym_industry = _build_symbol_industry_map()

    # Build a lookup: (date, industry) → avg_tone
    gdelt_lookup = {}
    for _, row in gdelt_df.iterrows():
        key = (row["date"], row["industry"])
        gdelt_lookup[key] = row["avg_tone"]

    # Initialize gdelt_tone column (overrides the daily_features one which is mostly NULL)
    tones = []
    for _, row in df.iterrows():
        industry = sym_industry.get(row["symbol"], "")
        tone = gdelt_lookup.get((row["date"], industry))
        tones.append(tone if tone is not None else 0.0)

    df["gdelt_tone"] = tones
    filled = sum(1 for t in tones if t != 0.0)
    log.info(f"GDELT tone backfill: {filled:,}/{len(df):,} rows ({filled/len(df)*100:.1f}%) have non-zero tone")
    return df


def _merge_insider_features(df: pd.DataFrame, insider_df: pd.DataFrame) -> pd.DataFrame:
    """Compute insider trading features: buy ratio over last 90 days per stock."""
    df["insider_buy_ratio"] = 0.5  # default: neutral

    for symbol in df["symbol"].unique():
        sym_insider = insider_df[insider_df["symbol"] == symbol]
        if sym_insider.empty:
            continue

        sym_mask = df["symbol"] == symbol
        sym_insider = sym_insider.sort_values("filing_date")

        for idx in df.loc[sym_mask].index:
            row_date = df.at[idx, "date"]
            # Look back 90 days
            cutoff = pd.Timestamp(row_date) - pd.Timedelta(days=90)
            recent = sym_insider[
                (sym_insider["filing_date"] <= row_date) &
                (sym_insider["filing_date"] >= cutoff.strftime("%Y-%m-%d"))
            ]
            if recent.empty:
                continue

            buys = recent["transaction_type"].apply(
                lambda t: str(t).upper().strip().startswith("P") or "BUY" in str(t).upper() or "PURCHASE" in str(t).upper()
            ).sum()
            total = len(recent)
            df.at[idx, "insider_buy_ratio"] = buys / total if total > 0 else 0.5

    return df


def _merge_analyst_features(df: pd.DataFrame, analyst_df: pd.DataFrame) -> pd.DataFrame:
    """Compute analyst consensus score from recommendation history."""
    df["analyst_score"] = 0.0  # default: neutral

    for symbol in df["symbol"].unique():
        sym_analyst = analyst_df[analyst_df["symbol"] == symbol]
        if sym_analyst.empty:
            continue

        sym_mask = df["symbol"] == symbol
        sym_analyst = sym_analyst.sort_values("date")

        for idx in df.loc[sym_mask].index:
            row_date = df.at[idx, "date"]
            past = sym_analyst[sym_analyst["date"] <= row_date]
            if past.empty:
                continue

            latest = past.iloc[-1]
            sb = latest.get("strong_buy", 0) or 0
            b = latest.get("buy", 0) or 0
            h = latest.get("hold", 0) or 0
            s = latest.get("sell", 0) or 0
            ss = latest.get("strong_sell", 0) or 0
            total = sb + b + h + s + ss
            if total > 0:
                # Score from -1 (all strong sell) to +1 (all strong buy)
                score = (sb * 2 + b * 1 + h * 0 - s * 1 - ss * 2) / (total * 2)
                df.at[idx, "analyst_score"] = round(score, 4)

    return df


def load_data(market: str = None) -> pd.DataFrame:
    """Load training data from SQLite, optionally filtered by market."""
    conn = get_connection()

    query = """
        SELECT t.*, d.news_sentiment, d.news_count,
               d.reddit_sentiment, d.reddit_count,
               d.figure_sentiment, d.figure_count,
               d.gdelt_tone AS daily_gdelt_tone, d.fear_greed
        FROM training_data t
        LEFT JOIN daily_features d ON t.symbol = d.symbol AND t.date = d.date
        ORDER BY t.symbol, t.date
    """
    df = pd.read_sql_query(query, conn)

    # Load earnings history and compute per-row features
    earnings_df = pd.read_sql_query(
        "SELECT symbol, date, surprise_pct FROM earnings_history ORDER BY symbol, date",
        conn,
    )

    # Load GDELT history for per-industry tone backfill
    gdelt_df = pd.read_sql_query(
        "SELECT date, industry, avg_tone FROM gdelt_history ORDER BY date",
        conn,
    )

    # Load insider history for insider features
    insider_df = pd.DataFrame()
    try:
        insider_df = pd.read_sql_query(
            "SELECT symbol, filing_date, transaction_type FROM insider_history ORDER BY symbol, filing_date",
            conn,
        )
    except Exception:
        pass

    # Load analyst history for analyst features
    analyst_df = pd.DataFrame()
    try:
        analyst_df = pd.read_sql_query(
            "SELECT symbol, date, strong_buy, buy, hold, sell, strong_sell FROM analyst_history ORDER BY symbol, date",
            conn,
        )
    except Exception:
        pass

    conn.close()

    # Compute earnings features per stock per training row
    if not earnings_df.empty:
        df = _merge_earnings_features(df, earnings_df)

    # Backfill GDELT tone per stock (map symbol → industry → GDELT tone for that date)
    if not gdelt_df.empty:
        df = _merge_gdelt_features(df, gdelt_df)

    # Merge insider features
    if not insider_df.empty:
        df = _merge_insider_features(df, insider_df)

    # Merge analyst features
    if not analyst_df.empty:
        df = _merge_analyst_features(df, analyst_df)

    if market:
        if market.upper() == "MY":
            df = df[df["symbol"].str.endswith(".KL")]
        elif market.upper() == "US":
            df = df[~df["symbol"].str.endswith(".KL")]

    log.info(f"Loaded {len(df):,} rows, {df['symbol'].nunique()} stocks")
    return df


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Prepare feature matrix X, direction target y_dir, magnitude target y_mag."""

    # Add engineered features
    df = df.copy()

    # Price relative to moving averages (normalized)
    for col in ["sma_20", "sma_50", "ema_9", "ema_21"]:
        if col in df.columns:
            df[f"close_vs_{col}"] = (df["close"] - df[col]) / df[col].abs().clip(lower=0.01)

    # RSI zones (binary features)
    df["rsi_oversold"] = (df["rsi"] < 30).astype(int)
    df["rsi_overbought"] = (df["rsi"] > 70).astype(int)

    # Stochastic zones
    df["stoch_oversold"] = (df["stoch_k"] < 20).astype(int)
    df["stoch_overbought"] = (df["stoch_k"] > 80).astype(int)

    # MACD crossover (MACD vs signal line position)
    df["macd_above_signal"] = (df["macd"] > df["signal_line"]).astype(int)

    # ADX strong trend
    df["adx_strong"] = (df["adx"] > 25).astype(int)

    # Ichimoku cloud position
    cloud_top = df[["ichi_span_a", "ichi_span_b"]].max(axis=1)
    cloud_bot = df[["ichi_span_a", "ichi_span_b"]].min(axis=1)
    df["above_cloud"] = (df["close"] > cloud_top).astype(int)
    df["below_cloud"] = (df["close"] < cloud_bot).astype(int)

    # Bollinger Band width (volatility measure)
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_width"] = bb_range / df["close"].clip(lower=0.01)

    # Volume ratio vs 20-day average
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

    # ── NEW: Calendar features (day of week, month) ───────────────────
    try:
        dates = pd.to_datetime(df["date"])
        df["day_of_week"] = dates.dt.dayofweek       # 0=Mon, 4=Fri
        df["month"] = dates.dt.month                   # 1-12
        df["is_monday"] = (dates.dt.dayofweek == 0).astype(int)
        df["is_friday"] = (dates.dt.dayofweek == 4).astype(int)
        df["is_month_end"] = (dates.dt.is_month_end).astype(int)
    except Exception:
        df["day_of_week"] = 0
        df["month"] = 0
        df["is_monday"] = 0
        df["is_friday"] = 0
        df["is_month_end"] = 0

    # ── NEW: Price gap (open vs previous close) ───────────────────────
    df["gap_pct"] = ((df["open"] - df["close"].shift(1)) / df["close"].shift(1).clip(lower=0.01)) * 100

    # ── NEW: Sector relative strength (stock return vs market) ────────
    stock_ret_20d = df["close"].pct_change(20)
    market_ret_20d = df["market_index_close"].pct_change(20)
    df["relative_strength"] = stock_ret_20d - market_ret_20d

    # ── NEW: Market regime (VIX + trend) ──────────────────────────────
    df["vix_high"] = (df["vix_close"] > 25).astype(int)
    df["vix_extreme"] = (df["vix_close"] > 35).astype(int)
    df["market_above_sma"] = (df["market_index_close"] > df["market_index_close"].rolling(50).mean()).astype(int)

    # ── NEW: Price momentum features ──────────────────────────────────
    df["momentum_5d"] = df["close"].pct_change(5) * 100
    df["momentum_20d"] = df["close"].pct_change(20) * 100
    df["acceleration"] = df["momentum_5d"] - df["momentum_5d"].shift(5)  # momentum change

    # ── NEW: 52-week proximity ────────────────────────────────────────
    rolling_high = df["high"].rolling(252, min_periods=20).max()
    rolling_low = df["low"].rolling(252, min_periods=20).min()
    price_range = (rolling_high - rolling_low).clip(lower=0.01)
    df["pct_from_52w_high"] = ((df["close"] - rolling_high) / rolling_high) * 100
    df["pct_from_52w_low"] = ((df["close"] - rolling_low) / rolling_low) * 100
    df["position_in_52w_range"] = (df["close"] - rolling_low) / price_range

    # ── NEW: Consecutive up/down days ─────────────────────────────────
    direction = (df["close"] > df["close"].shift(1)).astype(int)
    streaks = direction.groupby((direction != direction.shift()).cumsum()).cumcount() + 1
    df["up_streak"] = (streaks * direction).astype(int)
    df["down_streak"] = (streaks * (1 - direction)).astype(int)

    # ── NEW: Volume trend ─────────────────────────────────────────────
    vol_5d = df["volume"].rolling(5).mean()
    vol_20d = df["volume"].rolling(20).mean()
    df["volume_trend"] = vol_5d / vol_20d.clip(lower=1)

    # ── NEW: EMA convergence/divergence rate ─────���────────────────────
    df["ema_convergence"] = (df["ema_9"] - df["ema_21"]).pct_change(5)

    # ── Lagged features (must use groupby to avoid cross-stock bleed) ──
    for lag in [1, 5, 20]:
        df[f"rsi_lag{lag}"] = df.groupby("symbol")["rsi"].shift(lag)
        df[f"macd_lag{lag}"] = df.groupby("symbol")["macd"].shift(lag)
        df[f"volume_lag{lag}"] = df.groupby("symbol")["volume"].shift(lag)
        df[f"daily_return_lag{lag}"] = df.groupby("symbol")["daily_return"].shift(lag)

    # ── Fear & Greed proxy (computed from VIX + market momentum + breadth) ──
    vix_clamped = df["vix_close"].clip(15, 35)
    vix_component = (35 - vix_clamped) / 20 * 100
    mkt_ma125 = df.groupby("symbol")["market_index_close"].transform(
        lambda x: x.rolling(125, min_periods=20).mean()
    )
    momentum_component = ((df["market_index_close"] / mkt_ma125.clip(lower=0.01)) - 1).clip(-0.1, 0.1) * 500 + 50
    breadth_component = df.groupby("symbol")["daily_return"].transform(
        lambda x: x.rolling(20, min_periods=5).apply(lambda w: (w > 0).sum() / len(w), raw=True)
    ) * 100
    df["fear_greed_proxy"] = (vix_component + momentum_component + breadth_component) / 3

    # ── Cross-asset correlation features (rolling 20-day) ──
    if "oil_close" in df.columns:
        oil_ret = df.groupby("symbol")["oil_close"].pct_change()
        stock_ret = df.groupby("symbol")["close"].pct_change()
        df["corr_oil_20d"] = stock_ret.rolling(20, min_periods=10).corr(oil_ret)
    if "gold_close" in df.columns:
        gold_ret = df.groupby("symbol")["gold_close"].pct_change()
        stock_ret2 = df.groupby("symbol")["close"].pct_change()
        df["corr_gold_20d"] = stock_ret2.rolling(20, min_periods=10).corr(gold_ret)

    # All feature columns
    engineered_cols = [
        # Existing
        "close_vs_sma_20", "close_vs_sma_50", "close_vs_ema_9", "close_vs_ema_21",
        "rsi_oversold", "rsi_overbought",
        "stoch_oversold", "stoch_overbought",
        "macd_above_signal", "adx_strong",
        "above_cloud", "below_cloud",
        "bb_width", "vol_ratio",
        # Calendar
        "day_of_week", "month", "is_monday", "is_friday", "is_month_end",
        # Price gap
        "gap_pct",
        # Sector relative strength
        "relative_strength",
        # Market regime
        "vix_high", "vix_extreme", "market_above_sma",
        # Momentum
        "momentum_5d", "momentum_20d", "acceleration",
        # 52-week proximity
        "pct_from_52w_high", "pct_from_52w_low", "position_in_52w_range",
        # Streaks
        "up_streak", "down_streak",
        # Volume trend
        "volume_trend",
        # EMA convergence
        "ema_convergence",
        # Lagged features (12)
        "rsi_lag1", "rsi_lag5", "rsi_lag20",
        "macd_lag1", "macd_lag5", "macd_lag20",
        "volume_lag1", "volume_lag5", "volume_lag20",
        "daily_return_lag1", "daily_return_lag5", "daily_return_lag20",
        # Fear & Greed proxy
        "fear_greed_proxy",
        # Cross-asset correlations
        "corr_oil_20d", "corr_gold_20d",
    ]

    all_features = FEATURE_COLS + SENTIMENT_COLS + EARNINGS_COLS + INSIDER_COLS + ANALYST_COLS + engineered_cols
    available = [c for c in all_features if c in df.columns]

    X = df[available].copy()

    # Direction target: UP (>1%), DOWN (<-1%), FLAT (else)
    y_dir = pd.Series("FLAT", index=df.index)
    y_dir[df["price_change_5d"] > UP_THRESHOLD] = "UP"
    y_dir[df["price_change_5d"] < DOWN_THRESHOLD] = "DOWN"

    # Magnitude target
    y_mag = df["price_change_5d"].copy()

    # Drop rows where target is NaN (last 5 days of each stock)
    valid = df["price_change_5d"].notna()
    X = X[valid]
    y_dir = y_dir[valid]
    y_mag = y_mag[valid]

    # Coerce all columns to numeric (handles object types from LEFT JOIN)
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")

    # Replace inf values and fill NaNs with 0
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    log.info(f"Features: {len(available)} columns, {len(X):,} samples")
    log.info(f"Class distribution: {dict(y_dir.value_counts())}")

    return X, y_dir, y_mag


# ── Model Training ────────────────────────────────────────────────────────────

def train_direction_models(X: pd.DataFrame, y: pd.Series) -> dict:
    """Train XGBoost + LightGBM direction classifiers with time-series CV."""

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    classes = le.classes_

    # Time-series split (no data leakage)
    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, test_idx = splits[-1]  # use last split for final eval

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y_encoded[train_idx], y_encoded[test_idx]

    log.info(f"Train: {len(X_train):,}, Test: {len(X_test):,}")

    # ── XGBoost ───────────────────────────────────────────────────────────
    log.info("Training XGBoost direction classifier...")
    xgb_model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="mlogloss",
        early_stopping_rounds=50,
        verbosity=0,
    )
    xgb_model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    y_pred_xgb = xgb_model.predict(X_test)
    acc_xgb = accuracy_score(y_test, y_pred_xgb)
    f1_xgb = f1_score(y_test, y_pred_xgb, average="weighted")
    log.info(f"  XGBoost — Accuracy: {acc_xgb:.3f}, F1: {f1_xgb:.3f}")

    # ── LightGBM ──────────────────────────────────────────────────────────
    log.info("Training LightGBM direction classifier...")
    lgbm_model = lgb.LGBMClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbose=-1,
    )
    lgbm_model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.log_evaluation(period=0)],
    )

    y_pred_lgbm = lgbm_model.predict(X_test)
    acc_lgbm = accuracy_score(y_test, y_pred_lgbm)
    f1_lgbm = f1_score(y_test, y_pred_lgbm, average="weighted")
    log.info(f"  LightGBM — Accuracy: {acc_lgbm:.3f}, F1: {f1_lgbm:.3f}")

    # ── Ensemble (average probabilities) ──────────────────────────────────
    xgb_proba = xgb_model.predict_proba(X_test)
    lgbm_proba = lgbm_model.predict_proba(X_test)
    ensemble_proba = (xgb_proba + lgbm_proba) / 2
    y_pred_ensemble = ensemble_proba.argmax(axis=1)
    acc_ens = accuracy_score(y_test, y_pred_ensemble)
    f1_ens = f1_score(y_test, y_pred_ensemble, average="weighted")
    log.info(f"  Ensemble — Accuracy: {acc_ens:.3f}, F1: {f1_ens:.3f}")

    # Classification report
    report = classification_report(y_test, y_pred_ensemble,
                                    target_names=classes, output_dict=True)
    log.info("\n" + classification_report(y_test, y_pred_ensemble, target_names=classes))

    return {
        "xgb_model": xgb_model,
        "lgbm_model": lgbm_model,
        "label_encoder": le,
        "feature_names": list(X.columns),
        "metrics": {
            "xgb_accuracy": round(acc_xgb, 4),
            "xgb_f1": round(f1_xgb, 4),
            "lgbm_accuracy": round(acc_lgbm, 4),
            "lgbm_f1": round(f1_lgbm, 4),
            "ensemble_accuracy": round(acc_ens, 4),
            "ensemble_f1": round(f1_ens, 4),
            "report": report,
            "classes": list(classes),
            "train_size": len(X_train),
            "test_size": len(X_test),
        },
    }


def train_magnitude_model(X: pd.DataFrame, y: pd.Series) -> dict:
    """Train XGBoost regressor for magnitude prediction."""

    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, test_idx = splits[-1]

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    log.info("Training XGBoost magnitude regressor...")
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        early_stopping_rounds=50,
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = root_mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    log.info(f"  MAE: {mae:.3f}%, RMSE: {rmse:.3f}%, R2: {r2:.3f}")

    return {
        "model": model,
        "metrics": {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
        },
    }


def save_feature_importance(xgb_model, feature_names: list[str]):
    """Save ranked feature importance to CSV."""
    importance = xgb_model.feature_importances_
    fi = pd.DataFrame({
        "feature": feature_names,
        "importance": importance,
    }).sort_values("importance", ascending=False)
    fi.to_csv(MODEL_DIR / "feature_importance.csv", index=False)
    log.info(f"\nTop 15 features:")
    for _, row in fi.head(15).iterrows():
        bar = "#" * int(row["importance"] * 100)
        log.info(f"  {row['feature']:25s} {row['importance']:.4f} {bar}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(market: str = None):
    init_db()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    df = load_data(market)
    if len(df) < 100:
        log.error("Not enough data to train. Run collect_historical.py first.")
        return

    # Prepare features
    X, y_dir, y_mag = prepare_features(df)

    # Train direction models
    dir_results = train_direction_models(X, y_dir)

    # Train magnitude model
    mag_results = train_magnitude_model(X, y_mag)

    # Save models
    log.info("\nSaving models...")
    dir_results["xgb_model"].save_model(str(MODEL_DIR / "direction_xgb.json"))
    dir_results["lgbm_model"].booster_.save_model(str(MODEL_DIR / "direction_lgbm.txt"))
    mag_results["model"].save_model(str(MODEL_DIR / "magnitude_xgb.json"))

    # Save label encoder + feature names
    joblib.dump(dir_results["label_encoder"], MODEL_DIR / "label_encoder.joblib")
    joblib.dump(dir_results["feature_names"], MODEL_DIR / "feature_names.joblib")

    # Save feature importance
    save_feature_importance(dir_results["xgb_model"], dir_results["feature_names"])

    # Save metrics
    metrics = {
        "direction": dir_results["metrics"],
        "magnitude": mag_results["metrics"],
        "trained_at": datetime.now().isoformat(),
        "market": market or "ALL",
        "total_samples": len(X),
        "stocks": df["symbol"].nunique(),
    }
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    log.info(f"\nModels saved to {MODEL_DIR.absolute()}")
    log.info(f"Direction ensemble: {dir_results['metrics']['ensemble_accuracy']:.1%} accuracy")
    log.info(f"Magnitude MAE: {mag_results['metrics']['mae']:.2f}%")


if __name__ == "__main__":
    args = sys.argv[1:]
    market = None
    for i, a in enumerate(args):
        if a == "--market" and i + 1 < len(args):
            market = args[i + 1]
    run(market=market)
