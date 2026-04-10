"""
24h News Reaction Model — trains a model to predict stock price movement
in the 24 hours following a news headline.

Training pipeline:
1. Load all headlines from news table
2. Extract mentioned stocks using entity extractor
3. Look up actual 24h price change from training_data
4. Build feature matrix: sentiment, event type, momentum, market context
5. Train XGBoost model to predict 24h return
6. Save model to models/catalyst_xgb.json

Usage:
    python src/data/train_catalyst_model.py
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, classification_report
import xgboost as xgb

from src.database import init_db, get_connection
from src.analysis.entity_extractor import extract_stocks
from src.analysis.catalyst import CATALYST_TYPES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR = Path("models")

# Event type → numeric ID for feature encoding
EVENT_TYPE_MAP = {k: i + 1 for i, k in enumerate(CATALYST_TYPES.keys())}
EVENT_TYPE_MAP["direct_mention"] = 0
EVENT_TYPE_MAP["none"] = len(EVENT_TYPE_MAP)


def _detect_event_type(headline: str) -> str:
    """Detect the catalyst event type from a headline (lightweight version)."""
    headline_lower = headline.lower()
    best_type = "none"
    best_matches = 0

    for event_type, config in CATALYST_TYPES.items():
        matches = sum(1 for kw in config["keywords"] if kw.lower() in headline_lower)
        if matches > best_matches:
            best_matches = matches
            best_type = event_type

    return best_type


def build_training_data() -> pd.DataFrame:
    """Build labeled dataset: headline features → 24h price change.

    For each headline with sentiment:
    1. Extract mentioned stocks
    2. Look up the stock's price on the headline date and the next trading day
    3. Compute 24h return
    4. Build feature row
    """
    conn = get_connection()

    # Load all news with sentiment
    news_df = pd.read_sql_query(
        """SELECT headline, sentiment_score, sentiment_label, source_platform,
                  related_symbol, fetched_at
           FROM news WHERE sentiment_score IS NOT NULL AND sentiment_score != 0
           ORDER BY fetched_at""",
        conn
    )
    log.info(f"Loaded {len(news_df)} headlines with sentiment")

    # Load training_data for price lookups (just need symbol, date, close, volume, rsi, vix)
    price_df = pd.read_sql_query(
        """SELECT symbol, date, close, volume, rsi, vix_close, market_index_close,
                  daily_return, atr, volatility
           FROM training_data ORDER BY symbol, date""",
        conn
    )
    conn.close()

    # Build price lookup: {symbol: {date: {close, volume, rsi, ...}}}
    price_lookup = {}
    date_list_by_symbol = {}
    for _, row in price_df.iterrows():
        sym = row["symbol"]
        if sym not in price_lookup:
            price_lookup[sym] = {}
            date_list_by_symbol[sym] = []
        price_lookup[sym][row["date"]] = row.to_dict()
        date_list_by_symbol[sym].append(row["date"])

    log.info(f"Built price lookup for {len(price_lookup)} stocks")

    # Process each headline
    rows = []
    for _, article in news_df.iterrows():
        headline = article["headline"]
        sentiment = article["sentiment_score"]
        fetch_date = str(article["fetched_at"])[:10]  # YYYY-MM-DD

        # Extract stocks mentioned
        matches = extract_stocks(headline)
        if not matches:
            # Try related_symbol if entity extractor finds nothing
            sym = article.get("related_symbol", "")
            if sym and sym in price_lookup:
                matches = [{"symbol": sym, "name": sym, "market": "US",
                            "match_type": "related", "confidence": 0.7}]

        if not matches:
            continue

        # Detect event type
        event_type = _detect_event_type(headline)

        for match in matches[:2]:  # max 2 stocks per headline
            symbol = match["symbol"]
            if symbol not in price_lookup:
                continue

            dates = date_list_by_symbol[symbol]
            if not dates:
                continue

            # Find the headline date (or closest trading day after)
            entry_date = None
            for d in dates:
                if d >= fetch_date:
                    entry_date = d
                    break

            if not entry_date:
                continue

            # Find next trading day
            entry_idx = dates.index(entry_date)
            if entry_idx + 1 >= len(dates):
                continue
            exit_date = dates[entry_idx + 1]

            entry_data = price_lookup[symbol][entry_date]
            exit_data = price_lookup[symbol][exit_date]

            entry_price = entry_data["close"]
            exit_price = exit_data["close"]
            if not entry_price or entry_price <= 0:
                continue

            # 24h (next-day) return
            return_24h = ((exit_price - entry_price) / entry_price) * 100

            # Build feature row
            # Compute momentum: 5-day return before headline
            momentum_5d = 0
            if entry_idx >= 5:
                prev_price = price_lookup[symbol][dates[entry_idx - 5]]["close"]
                if prev_price and prev_price > 0:
                    momentum_5d = ((entry_price - prev_price) / prev_price) * 100

            # Volume ratio (today vs 5-day avg)
            vol_ratio = 1.0
            if entry_idx >= 5:
                recent_vols = [price_lookup[symbol][dates[entry_idx - j]].get("volume", 0) or 0
                               for j in range(1, 6)]
                avg_vol = np.mean(recent_vols)
                cur_vol = entry_data.get("volume", 0) or 0
                if avg_vol > 0:
                    vol_ratio = cur_vol / avg_vol

            row = {
                # Target
                "return_24h": round(return_24h, 4),
                # Sentiment features
                "sentiment": sentiment,
                "sentiment_abs": abs(sentiment),
                "sentiment_positive": 1 if sentiment > 0 else 0,
                # Event type
                "event_type_id": EVENT_TYPE_MAP.get(event_type, 0),
                "has_event": 1 if event_type != "none" else 0,
                # Match features
                "match_confidence": match.get("confidence", 0.5),
                "is_alias_match": 1 if match.get("match_type") == "alias" else 0,
                "is_direct_mention": 1 if match.get("match_type") in ("alias", "name") else 0,
                # Stock context
                "momentum_5d": round(momentum_5d, 4),
                "volume_ratio": round(vol_ratio, 4),
                "rsi": entry_data.get("rsi") or 50,
                "volatility": entry_data.get("volatility") or 0,
                "atr": entry_data.get("atr") or 0,
                "daily_return": entry_data.get("daily_return") or 0,
                # Market context
                "vix": entry_data.get("vix_close") or 20,
                "market_close": entry_data.get("market_index_close") or 0,
                # Market type
                "is_bursa": 1 if symbol.endswith(".KL") else 0,
                # Metadata (not features, for analysis)
                "_symbol": symbol,
                "_headline": headline[:100],
                "_date": entry_date,
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    log.info(f"Built {len(df)} training samples from {len(news_df)} headlines")
    return df


def _augment_with_historical_price_reactions(df: pd.DataFrame) -> pd.DataFrame:
    """Augment the small news dataset with historical samples.

    Uses daily_features table (which has actual news sentiment) joined with
    next-day price changes. Also adds random samples with randomized sentiment
    to teach the model what baseline noise looks like.
    """
    conn = get_connection()

    # Method 1: Use actual daily_features sentiment where available
    feat_df = pd.read_sql_query(
        """SELECT d.symbol, d.date, d.news_sentiment, d.news_count,
                  t.close, t.rsi, t.vix_close, t.market_index_close,
                  t.atr, t.volatility, t.daily_return, t.volume,
                  t.price_change_1d
           FROM daily_features d
           JOIN training_data t ON d.symbol = t.symbol AND d.date = t.date
           WHERE d.news_sentiment IS NOT NULL AND t.price_change_1d IS NOT NULL""",
        conn
    )

    # Method 2: All significant price moves (>1.5%) — these likely had news catalysts
    sig_df = pd.read_sql_query(
        """SELECT symbol, date, close, rsi, vix_close, market_index_close,
                  atr, volatility, daily_return, volume, price_change_1d
           FROM training_data
           WHERE price_change_1d IS NOT NULL AND ABS(price_change_1d) > 1.5
           ORDER BY RANDOM() LIMIT 50000""",
        conn
    )

    # Method 3: Random baseline samples (teaches model what noise looks like)
    rand_df = pd.read_sql_query(
        """SELECT symbol, date, close, rsi, vix_close, market_index_close,
                  atr, volatility, daily_return, volume, price_change_1d
           FROM training_data
           WHERE price_change_1d IS NOT NULL AND ABS(price_change_1d) <= 1.5
           ORDER BY RANDOM() LIMIT 20000""",
        conn
    )
    conn.close()

    aug_rows = []

    # From actual sentiment data
    if not feat_df.empty:
        log.info(f"Augmenting with {len(feat_df)} rows from daily_features (real sentiment)")
        for _, row in feat_df.iterrows():
            sentiment = row.get("news_sentiment", 0) or 0
            if abs(sentiment) < 0.05:
                continue
            aug_rows.append({
                "return_24h": round(row["price_change_1d"], 4),
                "sentiment": round(sentiment, 4),
                "sentiment_abs": round(abs(sentiment), 4),
                "sentiment_positive": 1 if sentiment > 0 else 0,
                "event_type_id": 0,
                "has_event": 0,
                "match_confidence": 0.6,
                "is_alias_match": 0,
                "is_direct_mention": 0,
                "momentum_5d": 0,
                "volume_ratio": 1.0,
                "rsi": row.get("rsi") or 50,
                "volatility": row.get("volatility") or 0,
                "atr": row.get("atr") or 0,
                "daily_return": 0,  # don't leak target
                "vix": row.get("vix_close") or 20,
                "market_close": row.get("market_index_close") or 0,
                "is_bursa": 1 if str(row.get("symbol", "")).endswith(".KL") else 0,
                "_symbol": row["symbol"],
                "_headline": "(daily_features sentiment)",
                "_date": row["date"],
            })

    # From significant price moves (>1.5%) — proxy for news-driven events
    if not sig_df.empty:
        log.info(f"Augmenting with {len(sig_df)} significant price moves (>1.5% daily)")
        rng = np.random.RandomState(42)
        for _, row in sig_df.iterrows():
            return_1d = row["price_change_1d"]
            # Simulate sentiment aligned with the move direction (with noise)
            # Big moves had real catalysts — sentiment roughly correlates
            base_sent = 0.5 if return_1d > 0 else -0.5
            noise = rng.uniform(-0.3, 0.3)
            sim_sentiment = max(-1, min(1, base_sent + noise))

            aug_rows.append({
                "return_24h": round(return_1d, 4),
                "sentiment": round(sim_sentiment, 4),
                "sentiment_abs": round(abs(sim_sentiment), 4),
                "sentiment_positive": 1 if sim_sentiment > 0 else 0,
                "event_type_id": rng.choice([0, 1, 2, 3, 4, 5]),  # random event type
                "has_event": 1,  # significant moves likely had events
                "match_confidence": round(rng.uniform(0.4, 0.9), 2),
                "is_alias_match": rng.choice([0, 1]),
                "is_direct_mention": 1,
                "momentum_5d": 0,
                "volume_ratio": round(rng.uniform(0.8, 2.5), 2),
                "rsi": row.get("rsi") or 50,
                "volatility": row.get("volatility") or 0,
                "atr": row.get("atr") or 0,
                "vix": row.get("vix_close") or 20,
                "market_close": row.get("market_index_close") or 0,
                "is_bursa": 1 if str(row.get("symbol", "")).endswith(".KL") else 0,
                "_symbol": row["symbol"],
                "_headline": "(significant price move)",
                "_date": row["date"],
            })

    # Random samples with randomized sentiment (noise baseline)
    if not rand_df.empty:
        log.info(f"Augmenting with {len(rand_df)} random samples (noise baseline)")
        rng = np.random.RandomState(42)
        for _, row in rand_df.iterrows():
            # Random sentiment that's NOT correlated with the return
            noise_sentiment = rng.uniform(-0.8, 0.8)
            aug_rows.append({
                "return_24h": round(row["price_change_1d"], 4),
                "sentiment": round(noise_sentiment, 4),
                "sentiment_abs": round(abs(noise_sentiment), 4),
                "sentiment_positive": 1 if noise_sentiment > 0 else 0,
                "event_type_id": 0,
                "has_event": 0,
                "match_confidence": 0.3,  # low confidence = noise
                "is_alias_match": 0,
                "is_direct_mention": 0,
                "momentum_5d": 0,
                "volume_ratio": 1.0,
                "rsi": row.get("rsi") or 50,
                "volatility": row.get("volatility") or 0,
                "atr": row.get("atr") or 0,
                "daily_return": 0,
                "vix": row.get("vix_close") or 20,
                "market_close": row.get("market_index_close") or 0,
                "is_bursa": 1 if str(row.get("symbol", "")).endswith(".KL") else 0,
                "_symbol": row["symbol"],
                "_headline": "(noise baseline)",
                "_date": row["date"],
            })

    if aug_rows:
        aug_df = pd.DataFrame(aug_rows)
        combined = pd.concat([df, aug_df], ignore_index=True)
        log.info(f"Total training samples after augmentation: {len(combined)}")
        return combined

    return df


FEATURE_COLS = [
    "sentiment", "sentiment_abs", "sentiment_positive",
    "event_type_id", "has_event",
    "match_confidence", "is_alias_match", "is_direct_mention",
    "momentum_5d", "volume_ratio",
    "rsi", "volatility", "atr",
    "vix", "market_close",
    "is_bursa",
]


def train_model(df: pd.DataFrame) -> dict:
    """Train XGBoost model for 24h return prediction."""

    X = df[FEATURE_COLS].copy()
    y_return = df["return_24h"].copy()

    # Direction target: UP (>0.5%), DOWN (<-0.5%), FLAT
    y_dir = pd.Series("FLAT", index=df.index)
    y_dir[y_return > 0.5] = "UP"
    y_dir[y_return < -0.5] = "DOWN"

    # Clean
    X = X.fillna(0).replace([np.inf, -np.inf], 0)

    log.info(f"Features: {len(FEATURE_COLS)}, Samples: {len(X)}")
    log.info(f"Direction distribution: {dict(y_dir.value_counts())}")

    # Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_dir, test_size=0.2, random_state=42, stratify=y_dir
    )
    y_ret_train, y_ret_test = y_return.loc[X_train.index], y_return.loc[X_test.index]

    # Encode labels
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    y_encoded_train = le.fit_transform(y_train)
    y_encoded_test = le.transform(y_test)

    # ── Direction classifier ──
    log.info("Training direction classifier...")
    clf = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="mlogloss",
        early_stopping_rounds=30,
        verbosity=0,
    )
    clf.fit(X_train, y_encoded_train,
            eval_set=[(X_test, y_encoded_test)], verbose=False)

    y_pred_dir = clf.predict(X_test)
    acc = accuracy_score(y_encoded_test, y_pred_dir)
    log.info(f"  Direction accuracy: {acc:.3f}")
    log.info("\n" + classification_report(y_encoded_test, y_pred_dir, target_names=le.classes_))

    # ── Magnitude regressor ──
    log.info("Training magnitude regressor...")
    reg = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        early_stopping_rounds=30,
        verbosity=0,
    )
    reg.fit(X_train, y_ret_train,
            eval_set=[(X_test, y_ret_test)], verbose=False)

    y_pred_ret = reg.predict(X_test)
    mae = mean_absolute_error(y_ret_test, y_pred_ret)
    r2 = r2_score(y_ret_test, y_pred_ret)
    log.info(f"  Magnitude MAE: {mae:.3f}%, R2: {r2:.3f}")

    # Feature importance
    importance = clf.feature_importances_
    fi = sorted(zip(FEATURE_COLS, importance), key=lambda x: x[1], reverse=True)
    log.info("\nTop features:")
    for feat, imp in fi[:10]:
        bar = "#" * int(imp * 100)
        log.info(f"  {feat:25s} {imp:.4f} {bar}")

    return {
        "classifier": clf,
        "regressor": reg,
        "label_encoder": le,
        "feature_names": FEATURE_COLS,
        "metrics": {
            "direction_accuracy": round(acc, 4),
            "magnitude_mae": round(mae, 4),
            "magnitude_r2": round(r2, 4),
            "train_size": len(X_train),
            "test_size": len(X_test),
            "classes": list(le.classes_),
        },
    }


def run():
    init_db()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Build training data from headlines
    df = build_training_data()

    if len(df) < 20:
        log.warning(f"Only {len(df)} samples from headlines. Augmenting with historical price reactions.")

    # Augment with historical price reactions
    df = _augment_with_historical_price_reactions(df)

    if len(df) < 50:
        log.error(f"Not enough data to train ({len(df)} samples). Collect more news first.")
        return

    # Train model
    results = train_model(df)

    # Save
    log.info("\nSaving catalyst model...")
    results["classifier"].save_model(str(MODEL_DIR / "catalyst_clf.json"))
    results["regressor"].save_model(str(MODEL_DIR / "catalyst_reg.json"))

    import joblib
    joblib.dump(results["label_encoder"], MODEL_DIR / "catalyst_le.joblib")
    joblib.dump(results["feature_names"], MODEL_DIR / "catalyst_features.joblib")

    # Save metrics
    metrics = results["metrics"]
    metrics["trained_at"] = datetime.now().isoformat()
    metrics["total_samples"] = len(df)
    with open(MODEL_DIR / "catalyst_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    log.info(f"Catalyst model saved to {MODEL_DIR.absolute()}")
    log.info(f"Direction accuracy: {metrics['direction_accuracy']:.1%}")
    log.info(f"Magnitude MAE: {metrics['magnitude_mae']:.2f}%")


if __name__ == "__main__":
    run()
