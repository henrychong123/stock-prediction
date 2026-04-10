"""
Prediction engine that combines all data signals into a final stock prediction.

Combines:
1. Technical analysis (price trends, RSI, MACD, Bollinger Bands)
2. News sentiment (company news + market news via FinBERT)
3. Social media sentiment (Reddit discussions)
4. Geopolitical impact (GDELT events: wars, sanctions, policy)
5. Influential figure monitoring (Musk, Trump, etc. via news coverage)

Each signal is weighted according to config/settings.py SIGNAL_WEIGHTS.
"""

from dataclasses import dataclass
from pathlib import Path
from config.settings import SIGNAL_WEIGHTS

# ── ML Model Cache ────────────────────────────────────────────────────────────
_ml_models = None

def _load_ml_models():
    """Lazy-load trained ML models. Returns None if models don't exist."""
    global _ml_models
    if _ml_models is not None:
        return _ml_models

    model_dir = Path("models")
    xgb_path = model_dir / "direction_xgb.json"
    lgbm_path = model_dir / "direction_lgbm.txt"
    features_path = model_dir / "feature_names.joblib"
    le_path = model_dir / "label_encoder.joblib"

    if not all(p.exists() for p in [xgb_path, features_path, le_path]):
        _ml_models = False  # mark as unavailable
        return False

    try:
        import xgboost as xgb
        import lightgbm as lgb
        import joblib

        xgb_model = xgb.XGBClassifier()
        xgb_model.load_model(str(xgb_path))

        lgbm_model = None
        if lgbm_path.exists():
            lgbm_model = lgb.Booster(model_file=str(lgbm_path))

        feature_names = joblib.load(features_path)
        label_encoder = joblib.load(le_path)

        _ml_models = {
            "xgb": xgb_model,
            "lgbm": lgbm_model,
            "features": feature_names,
            "le": label_encoder,
        }
        return _ml_models
    except Exception:
        _ml_models = False
        return False


def _get_ml_signal(symbol: str) -> dict | None:
    """Run the trained ML model on current data for a stock.
    Returns a signal dict like other signals, or None if models unavailable."""
    import math
    models = _load_ml_models()
    if not models:
        return None

    try:
        import pandas as pd
        import numpy as np
        import yfinance as yf
        from src.data_sources.stock_prices import get_historical_prices
        from datetime import datetime

        df = get_historical_prices(symbol, period="3mo")
        if df.empty or len(df) < 50:
            return None

        latest = df.iloc[-1]
        close = latest["Close"]

        # Build feature vector matching training columns
        raw = {
            "open": latest["Open"], "high": latest["High"], "low": latest["Low"],
            "close": close, "volume": latest["Volume"],
            "sma_20": latest.get("SMA_20"), "sma_50": latest.get("SMA_50"),
            "ema_9": latest.get("EMA_9"), "ema_12": latest.get("EMA_12"),
            "ema_21": latest.get("EMA_21"), "ema_26": latest.get("EMA_26"),
            "macd": latest.get("MACD"), "signal_line": latest.get("Signal_Line"),
            "macd_hist": latest.get("MACD_Hist"),
            "rsi": latest.get("RSI"), "stoch_k": latest.get("Stoch_K"),
            "stoch_d": latest.get("Stoch_D"), "williams_r": latest.get("Williams_R"),
            "bb_upper": latest.get("BB_Upper"), "bb_lower": latest.get("BB_Lower"),
            "adx": latest.get("ADX"), "plus_di": latest.get("Plus_DI"),
            "minus_di": latest.get("Minus_DI"),
            "atr": latest.get("ATR"), "obv": latest.get("OBV"),
            "vwap": latest.get("VWAP"), "cci": latest.get("CCI"),
            "psar": latest.get("PSAR"),
            "ichi_tenkan": latest.get("Ichi_Tenkan"), "ichi_kijun": latest.get("Ichi_Kijun"),
            "ichi_span_a": latest.get("Ichi_SpanA"), "ichi_span_b": latest.get("Ichi_SpanB"),
            "volatility": latest.get("Volatility"), "daily_return": latest.get("Daily_Return"),
            "market_index_close": 0, "vix_close": 0,
        }

        # ── Fetch live macro data for context features ──
        try:
            spy_data = yf.Ticker("SPY").history(period="5d")
            if not spy_data.empty:
                raw["market_index_close"] = float(spy_data["Close"].iloc[-1])
        except Exception:
            pass

        try:
            vix_data = yf.Ticker("^VIX").history(period="5d")
            if not vix_data.empty:
                raw["vix_close"] = float(vix_data["Close"].iloc[-1])
        except Exception:
            pass

        # Treasury yields
        try:
            tnx = yf.Ticker("^TNX").history(period="5d")
            irx = yf.Ticker("^IRX").history(period="5d")
            if not tnx.empty:
                raw["treasury_10y"] = float(tnx["Close"].iloc[-1])
            if not irx.empty:
                raw["treasury_2y"] = float(irx["Close"].iloc[-1])
            if raw.get("treasury_10y") and raw.get("treasury_2y"):
                raw["yield_spread"] = raw["treasury_10y"] - raw["treasury_2y"]
        except Exception:
            pass

        # Dollar index
        try:
            dxy = yf.Ticker("DX-Y.NYB").history(period="5d")
            if not dxy.empty:
                raw["dxy_close"] = float(dxy["Close"].iloc[-1])
            else:
                uup = yf.Ticker("UUP").history(period="5d")
                if not uup.empty:
                    raw["dxy_close"] = float(uup["Close"].iloc[-1])
        except Exception:
            pass

        # Cross-asset prices
        for ticker, key in [("CL=F", "oil_close"), ("GC=F", "gold_close"), ("HG=F", "copper_close")]:
            try:
                data = yf.Ticker(ticker).history(period="5d")
                if not data.empty:
                    raw[key] = float(data["Close"].iloc[-1])
            except Exception:
                pass

        # Sector ETF return
        raw["sector_etf_return"] = 0
        try:
            from src.data.collect_historical import GICS_SECTOR_ETF, _build_symbol_sector_map
            sector_map = _build_symbol_sector_map()
            gics = sector_map.get(symbol)
            if gics:
                etf = GICS_SECTOR_ETF.get(gics)
                if etf:
                    etf_data = yf.Ticker(etf).history(period="5d")
                    if not etf_data.empty and len(etf_data) >= 2:
                        ret = (etf_data["Close"].iloc[-1] / etf_data["Close"].iloc[-2] - 1) * 100
                        raw["sector_etf_return"] = float(ret)
        except Exception:
            pass

        # ── Engineered features (must match training) ──
        for col in ["sma_20", "sma_50", "ema_9", "ema_21"]:
            val = raw.get(col)
            if val and close and val != 0:
                raw[f"close_vs_{col}"] = (close - val) / abs(val)
            else:
                raw[f"close_vs_{col}"] = 0

        rsi = raw.get("rsi") or 50
        raw["rsi_oversold"] = 1 if rsi < 30 else 0
        raw["rsi_overbought"] = 1 if rsi > 70 else 0

        sk = raw.get("stoch_k") or 50
        raw["stoch_oversold"] = 1 if sk < 20 else 0
        raw["stoch_overbought"] = 1 if sk > 80 else 0

        raw["macd_above_signal"] = 1 if (raw.get("macd") or 0) > (raw.get("signal_line") or 0) else 0
        raw["adx_strong"] = 1 if (raw.get("adx") or 0) > 25 else 0

        span_a = raw.get("ichi_span_a") or 0
        span_b = raw.get("ichi_span_b") or 0
        raw["above_cloud"] = 1 if close > max(span_a, span_b) else 0
        raw["below_cloud"] = 1 if close < min(span_a, span_b) else 0

        bb_range = (raw.get("bb_upper") or 0) - (raw.get("bb_lower") or 0)
        raw["bb_width"] = bb_range / max(close, 0.01)

        # Volume ratio (use DataFrame for rolling)
        vol_series = df["Volume"]
        vol_avg_20 = vol_series.rolling(20).mean().iloc[-1]
        raw["vol_ratio"] = float(vol_series.iloc[-1] / vol_avg_20) if vol_avg_20 > 0 else 1.0

        # Calendar features
        now = datetime.now()
        raw["day_of_week"] = now.weekday()
        raw["month"] = now.month
        raw["is_monday"] = 1 if now.weekday() == 0 else 0
        raw["is_friday"] = 1 if now.weekday() == 4 else 0
        raw["is_month_end"] = 1 if (now + pd.Timedelta(days=1)).month != now.month else 0

        # Gap %
        if len(df) >= 2:
            prev_close = df["Close"].iloc[-2]
            raw["gap_pct"] = ((latest["Open"] - prev_close) / max(abs(prev_close), 0.01)) * 100
        else:
            raw["gap_pct"] = 0

        # Relative strength (stock 20d return vs market 20d return)
        if len(df) >= 21:
            stock_ret_20d = (df["Close"].iloc[-1] / df["Close"].iloc[-21]) - 1
            mkt_close = raw.get("market_index_close", 0)
            # Can't compute market 20d return from single value; use 0 as proxy
            raw["relative_strength"] = float(stock_ret_20d)
        else:
            raw["relative_strength"] = 0

        # Market regime
        vix_val = raw.get("vix_close", 0) or 0
        raw["vix_high"] = 1 if vix_val > 25 else 0
        raw["vix_extreme"] = 1 if vix_val > 35 else 0
        # market_above_sma: need 50-day SPY MA. Approximate from available data.
        raw["market_above_sma"] = 1  # default bullish; overridden if we have data

        # Momentum features (from DataFrame)
        if len(df) >= 21:
            raw["momentum_5d"] = float((df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100) if len(df) >= 6 else 0
            raw["momentum_20d"] = float((df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100)
            raw["acceleration"] = raw["momentum_5d"] - float((df["Close"].iloc[-6] / df["Close"].iloc[-11] - 1) * 100) if len(df) >= 11 else 0
        else:
            raw["momentum_5d"] = raw["momentum_20d"] = raw["acceleration"] = 0

        # 52-week proximity (use 3mo data as best available)
        high_max = float(df["High"].max())
        low_min = float(df["Low"].min())
        price_range = max(high_max - low_min, 0.01)
        raw["pct_from_52w_high"] = ((close - high_max) / high_max) * 100
        raw["pct_from_52w_low"] = ((close - low_min) / low_min) * 100 if low_min > 0 else 0
        raw["position_in_52w_range"] = (close - low_min) / price_range

        # Streaks
        returns = df["Close"].pct_change()
        ups = 0
        for r in returns.iloc[::-1]:
            if r > 0:
                ups += 1
            else:
                break
        downs = 0
        for r in returns.iloc[::-1]:
            if r < 0:
                downs += 1
            else:
                break
        raw["up_streak"] = ups
        raw["down_streak"] = downs

        # Volume trend
        vol_5d = vol_series.tail(5).mean()
        vol_20d = vol_series.tail(20).mean()
        raw["volume_trend"] = float(vol_5d / max(vol_20d, 1))

        # EMA convergence
        ema9_series = df.get("EMA_9")
        ema21_series = df.get("EMA_21")
        if ema9_series is not None and ema21_series is not None and len(df) >= 6:
            diff_now = float(ema9_series.iloc[-1] - ema21_series.iloc[-1])
            diff_5d = float(ema9_series.iloc[-6] - ema21_series.iloc[-6]) if len(df) >= 6 else diff_now
            raw["ema_convergence"] = (diff_now - diff_5d) / max(abs(diff_5d), 0.01)
        else:
            raw["ema_convergence"] = 0

        # Lagged features (from DataFrame history)
        for lag in [1, 5, 20]:
            idx = -1 - lag
            if abs(idx) <= len(df):
                raw[f"rsi_lag{lag}"] = float(df["RSI"].iloc[idx]) if "RSI" in df.columns else 0
                raw[f"macd_lag{lag}"] = float(df["MACD"].iloc[idx]) if "MACD" in df.columns else 0
                raw[f"volume_lag{lag}"] = float(df["Volume"].iloc[idx])
                raw[f"daily_return_lag{lag}"] = float(df["Daily_Return"].iloc[idx]) if "Daily_Return" in df.columns else 0
            else:
                raw[f"rsi_lag{lag}"] = raw[f"macd_lag{lag}"] = raw[f"volume_lag{lag}"] = raw[f"daily_return_lag{lag}"] = 0

        # Fear & Greed proxy
        vix_clamped = max(15, min(35, vix_val))
        vix_comp = (35 - vix_clamped) / 20 * 100
        raw["fear_greed_proxy"] = vix_comp  # simplified (single-point, no rolling)

        # Cross-asset correlations (simplified: 0 for single-point inference)
        raw["corr_oil_20d"] = 0
        raw["corr_gold_20d"] = 0

        # Sentiment features (use daily_features if available, else 0)
        for col in ["news_sentiment", "news_count", "reddit_sentiment", "reddit_count",
                     "figure_sentiment", "figure_count", "gdelt_tone", "fear_greed"]:
            if col not in raw:
                raw[col] = 0

        # GDELT industry-specific tone (from stored data)
        try:
            from src.database import get_gdelt_tone_for_date
            from src.data.train_model import _build_symbol_industry_map
            ind_map = _build_symbol_industry_map()
            industry = ind_map.get(symbol, "")
            if industry:
                today = datetime.now().strftime("%Y-%m-%d")
                gdelt = get_gdelt_tone_for_date(today, industry)
                if gdelt:
                    raw["gdelt_tone"] = gdelt.get("avg_tone", 0) or 0
        except Exception:
            pass

        # Insider / Analyst features (0 for now at inference; could look up from DB)
        raw.setdefault("insider_buy_ratio", 0.5)
        raw.setdefault("analyst_score", 0.0)

        # Build DataFrame matching feature names
        feature_names = models["features"]
        row = {f: raw.get(f, 0) for f in feature_names}
        # Clean NaN
        for k, v in row.items():
            try:
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    row[k] = 0
                else:
                    row[k] = float(v)
            except (TypeError, ValueError):
                row[k] = 0

        X = pd.DataFrame([row], columns=feature_names)

        # Predict
        le = models["le"]
        xgb_proba = models["xgb"].predict_proba(X)[0]

        # Ensemble with LightGBM if available
        if models["lgbm"]:
            lgbm_proba = models["lgbm"].predict(X)[0]
            # LightGBM Booster returns raw proba differently
            n_classes = len(le.classes_)
            if len(lgbm_proba) == n_classes:
                proba = (xgb_proba + lgbm_proba) / 2
            else:
                proba = xgb_proba
        else:
            proba = xgb_proba

        pred_idx = proba.argmax()
        pred_label = le.classes_[pred_idx]
        pred_conf = proba[pred_idx]

        # Convert to signal format
        if pred_label == "UP":
            signal = "bullish"
            strength = 0.5 + (pred_conf * 0.5)  # 0.5 to 1.0
        elif pred_label == "DOWN":
            signal = "bearish"
            strength = 0.5 - (pred_conf * 0.5)  # 0.0 to 0.5
        else:
            signal = "neutral"
            strength = 0.5

        return {
            "signal": signal,
            "strength": round(strength, 3),
            "ml_prediction": pred_label,
            "ml_confidence": round(float(pred_conf), 3),
            "ml_probabilities": {le.classes_[i]: round(float(p), 3) for i, p in enumerate(proba)},
            "reasons": [f"ML model predicts {pred_label} ({pred_conf:.0%} confidence)"],
        }
    except Exception as e:
        return None


@dataclass
class PredictionResult:
    symbol: str
    action: str  # "STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"
    confidence: float  # 0-1
    price_current: float
    signals: dict
    reasons: list[str]
    weight_source: str = "default"  # "default" or "ai_optimized"
    weights_used: dict = None

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  PREDICTION: {self.symbol} → {self.action}",
            f"  Confidence: {self.confidence*100:.1f}%",
            f"  Current Price: ${self.price_current:.2f}",
            f"{'='*60}",
            "",
            "  Signal Breakdown:",
        ]

        for name, signal in self.signals.items():
            direction = signal.get("signal", "neutral")
            strength = signal.get("strength", 0.5)
            weight = SIGNAL_WEIGHTS.get(name, 0)
            icon = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "●"
            lines.append(
                f"    {icon} {name:20s} {direction:8s} "
                f"(strength: {strength:.2f}, weight: {weight:.0%})"
            )

        lines.append("")
        lines.append("  Key Reasons:")
        for i, reason in enumerate(self.reasons[:8], 1):
            lines.append(f"    {i}. {reason}")

        lines.append(f"{'='*60}")
        return "\n".join(lines)


_optimized_weights_cache = None

def _load_optimized_weights() -> dict | None:
    """Load AI-optimized weights from models/optimized_weights.json if fresh."""
    global _optimized_weights_cache
    if _optimized_weights_cache is not None:
        return _optimized_weights_cache

    path = Path("models/optimized_weights.json")
    if not path.exists():
        _optimized_weights_cache = False
        return None

    try:
        import json
        with open(path) as f:
            data = json.load(f)

        # Check freshness (< 7 days old)
        from datetime import datetime, timedelta
        optimized_at = datetime.fromisoformat(data.get("optimized_at", "2000-01-01"))
        if datetime.now() - optimized_at > timedelta(days=7):
            _optimized_weights_cache = False
            return None

        _optimized_weights_cache = data
        return data
    except Exception:
        _optimized_weights_cache = False
        return None


def get_active_weights(market: str = "US") -> tuple[dict, str]:
    """Get the active weights and their source.
    Returns (weights_dict, source_label).
    """
    opt = _load_optimized_weights()
    if opt and market.upper() in opt:
        w = opt[market.upper()].get("weights", {})
        if w:
            return w, "ai_optimized"

    # Fallback to config defaults
    if market.upper() == "MY":
        from config.settings import MY_SIGNAL_WEIGHTS
        return MY_SIGNAL_WEIGHTS, "default"
    return SIGNAL_WEIGHTS, "default"


def combine_signals(signals: dict, weights: dict | None = None,
                    market: str = "US") -> tuple[str, float, str]:
    """Combine weighted signals into a final prediction.

    Args:
        signals: Dict mapping signal name to signal dict (with 'signal' and 'strength')
        weights: Optional custom weights dict. If None, uses optimized or default.
        market: "US" or "MY" — used to select optimized weights.

    Returns:
        Tuple of (action, confidence, weight_source)
    """
    if weights is None:
        weights, weight_source = get_active_weights(market)
    else:
        weight_source = "custom"

    weighted_score = 0
    total_weight = 0

    for name, signal_data in signals.items():
        weight = weights.get(name, 0)
        if weight == 0:
            continue

        strength = signal_data.get("strength", 0.5)
        # Convert strength (0-1) to directional score (-1 to +1)
        directional = (strength - 0.5) * 2
        weighted_score += directional * weight
        total_weight += weight

    if total_weight > 0:
        final_score = weighted_score / total_weight
    else:
        final_score = 0

    # Map score to action
    if final_score > 0.4:
        action = "STRONG BUY"
    elif final_score > 0.15:
        action = "BUY"
    elif final_score > -0.15:
        action = "HOLD"
    elif final_score > -0.4:
        action = "SELL"
    else:
        action = "STRONG SELL"

    # Confidence is based on how far from neutral and signal agreement
    confidence = min(abs(final_score) * 1.5, 1.0)

    return action, round(confidence, 3), weight_source


def predict(symbol: str, fast: bool = True) -> PredictionResult:
    """Run prediction pipeline for a stock.

    Args:
        symbol: Stock ticker
        fast: If True (default), only uses technical + ML signals (~3-5 seconds).
              If False, also fetches news/social/geopolitical (~30-120 seconds).
    """
    from src.data_sources.stock_prices import get_realtime_quote, get_technical_signal

    # Detect market
    is_my = symbol.endswith(".KL") or symbol.startswith("^KL")
    if is_my:
        from config.settings import MY_SIGNAL_WEIGHTS, MY_GEOPOLITICAL_KEYWORDS
        weights = MY_SIGNAL_WEIGHTS
    else:
        weights = SIGNAL_WEIGHTS

    import time as _time
    _t0 = _time.time()

    # ── FAST MODE: Technical + ML only (no external API calls) ────────────
    # Used for interactive dashboard analysis (~3-5 seconds)
    technical = get_technical_signal(symbol)
    ml_signal = _get_ml_signal(symbol)

    # ── Earnings signal (fast — Finnhub single call, ~1s) ──────────────
    earnings = {"signal": "neutral", "strength": 0.5, "reasons": ["No earnings data"]}
    try:
        from src.data_sources.earnings import get_earnings_signal
        earnings = get_earnings_signal(symbol)
    except Exception:
        pass

    if fast:
        # Use neutral defaults for slow sources
        news = {"signal": "neutral", "strength": 0.5, "reasons": ["Fast mode — run batch for full analysis"]}
        social = {"signal": "neutral", "strength": 0.5, "reasons": ["Fast mode"]}
        geopolitical = {"signal": "neutral", "strength": 0.5, "reasons": []}
        print(f"  {symbol}: fast mode — technical + ML in {_time.time() - _t0:.1f}s")

    else:
        # ── FULL MODE: All sources (for batch predictions) ────────────────
        from src.data_sources.news_sentiment import get_news_signal, fetch_influential_figure_news
        from src.data_sources.geopolitical import get_geopolitical_signal
        from src.data_sources.social_media import get_social_signal
        from concurrent.futures import ThreadPoolExecutor, as_completed

        print(f"  {symbol}: full mode (parallel)...")

        def _get_news():
            if is_my:
                from src.data_sources.news_my import get_my_news_signal
                return get_my_news_signal(symbol)
            return get_news_signal(symbol)

        def _get_social():
            return get_social_signal(symbol)

        def _get_geo():
            geo = get_geopolitical_signal()
            if is_my:
                try:
                    from src.data_sources.geopolitical import fetch_geopolitical_events
                    my_events = fetch_geopolitical_events(keywords=MY_GEOPOLITICAL_KEYWORDS, max_records=20)
                    if my_events and "error" not in my_events[0]:
                        tones = [e.get("tone", 0) for e in my_events if isinstance(e.get("tone"), (int, float))]
                        if tones:
                            avg_tone = sum(tones) / len(tones)
                            gs = geo.get("strength", 0.5)
                            ms = (max(min(avg_tone / 10, 1), -1) + 1) / 2
                            geo["strength"] = round((gs * 0.4) + (ms * 0.6), 3)
                except Exception:
                    pass
            return geo

        def _get_figures():
            if is_my:
                from src.data_sources.news_my import fetch_my_influential_news
                return fetch_my_influential_news()
            return fetch_influential_figure_news()

        results = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_get_news): "news",
                pool.submit(_get_social): "social",
                pool.submit(_get_geo): "geopolitical",
                pool.submit(_get_figures): "figures",
            }
            for future in as_completed(futures, timeout=60):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=30)
                except Exception:
                    results[name] = None

        news = results.get("news") or {"signal": "neutral", "strength": 0.5, "reasons": ["No news data"]}
        social = results.get("social") or {"signal": "neutral", "strength": 0.5, "reasons": ["No social data"]}
        geopolitical = results.get("geopolitical") or {"signal": "neutral", "strength": 0.5, "reasons": []}
        figure_news = results.get("figures") or []

        # Blend figure sentiment into social
        if figure_news and isinstance(figure_news, list) and figure_news and "error" not in figure_news[0]:
            figure_scores = [n["sentiment"]["score"] for n in figure_news if "sentiment" in n]
            if figure_scores:
                avg_figure = sum(figure_scores) / len(figure_scores)
                blended = (social.get("strength", 0.5) * 0.6) + (((avg_figure + 1) / 2) * 0.4)
                social["strength"] = round(blended, 3)
                social["reasons"] = social.get("reasons", []) + [
                    f"[{n['figure']}] {n['headline']}" for n in figure_news[:3]
                ]

        print(f"  {symbol}: full mode done in {_time.time() - _t0:.1f}s")

    # Market momentum signal (derived from technical data)
    momentum = {
        "signal": technical.get("signal", "neutral"),
        "strength": technical.get("strength", 0.5),
    }

    signals = {
        "technical": technical,
        "news_sentiment": news,
        "social_sentiment": social,
        "geopolitical": geopolitical,
        "market_momentum": momentum,
        "earnings": earnings,
    }
    if ml_signal:
        signals["ml_model"] = ml_signal

    # Get current price
    quote = get_realtime_quote(symbol)
    current_price = quote.get("current_price", 0)

    # Combine signals (with AI-optimized or default weights)
    market = "MY" if is_my else "US"
    action, confidence, weight_source = combine_signals(signals, market=market)

    # Get the active weights for score computation
    active_weights, _ = get_active_weights(market)

    # Compute directional score for DB storage
    score = 0
    for name, sig in signals.items():
        w = active_weights.get(name, 0)
        s = sig.get("strength", 0.5)
        score += ((s - 0.5) * 2) * w

    # Collect all reasons
    all_reasons = []
    for name, sig in signals.items():
        for reason in sig.get("reasons", [])[:2]:
            all_reasons.append(f"[{name}] {reason}")

    # Save to database
    try:
        from src.database import save_prediction
        save_prediction(symbol, action, confidence, current_price, score, signals, all_reasons)
    except Exception:
        pass

    return PredictionResult(
        symbol=symbol,
        action=action,
        confidence=confidence,
        price_current=current_price,
        signals=signals,
        reasons=all_reasons,
        weight_source=weight_source,
        weights_used=active_weights,
    )
