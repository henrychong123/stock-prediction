"""
Flask web application for the stock prediction dashboard.

Serves the interactive visualization dashboard and JSON API endpoints.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, render_template, jsonify, request
from datetime import datetime

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/stock/<symbol>")
def stock_page(symbol):
    """Dedicated stock info page."""
    return render_template("stock.html", symbol=symbol.upper())


@app.route("/pro")
def pro_dashboard():
    """Professional analyst dashboard."""
    return render_template("pro.html")


@app.route("/api/predictions/latest")
def api_predictions_latest():
    """Get latest prediction for each symbol."""
    from src.database import get_latest_predictions
    try:
        preds = get_latest_predictions()
        return jsonify({"predictions": preds})
    except Exception as e:
        return jsonify({"error": str(e), "predictions": {}}), 500


@app.route("/api/batch-predict", methods=["POST"])
def api_batch_predict():
    """Trigger batch prediction for all Bursa stocks (runs in background)."""
    import threading
    from src.data.batch_predict import run as batch_run

    def _run():
        try:
            batch_run(include_us=False)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Batch prediction started in background"})


def _sanitize_for_json(obj):
    """Recursively clean NaN/Infinity/numpy types for JSON."""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 6)
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            v = float(obj)
            return None if math.isnan(v) else round(v, 6)
        if isinstance(obj, np.ndarray):
            return _sanitize_for_json(obj.tolist())
    except (ImportError, TypeError):
        pass
    return obj


@app.route("/api/predict/<symbol>")
def api_predict(symbol):
    """Get prediction for a stock.

    Strategy:
    1. Check DB for a recent prediction (< max_age minutes old) → serve instantly
    2. If stale or missing, compute live (fast mode by default)
    3. mode=full forces live computation with all signal sources
    4. mode=refresh forces fresh computation even if recent exists
    """
    import json as _json
    from datetime import datetime, timedelta

    sym = symbol.upper()
    mode = request.args.get("mode", "fast")  # fast | full | refresh
    max_age = int(request.args.get("max_age", 30))  # minutes

    # ── Try serving from DB (instant) ─────────────────────────────────
    if mode not in ("full", "refresh"):
        try:
            from src.database import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM predictions WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
                (sym,)
            ).fetchone()
            conn.close()

            if row and row["signals_json"]:
                created = datetime.fromisoformat(row["created_at"])
                # DB stores UTC via datetime('now'), compare with UTC
                from datetime import timezone
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                age_min = (now_utc - created).total_seconds() / 60

                if age_min < max_age:
                    signals = _json.loads(row["signals_json"])
                    reasons = _json.loads(row["reasons_json"]) if row["reasons_json"] else []

                    return jsonify(_sanitize_for_json({
                        "symbol": sym,
                        "action": row["action"],
                        "confidence": row["confidence"],
                        "price_current": row["price"],
                        "signals": signals,
                        "reasons": reasons,
                        "weight_source": "cached",
                        "weights_used": None,
                        "cached": True,
                        "cached_age_min": round(age_min, 1),
                    }))
        except Exception:
            pass  # fall through to live computation

    # ── Live computation ──────────────────────────────────────────────
    from src.analysis.predictor import predict

    try:
        fast = mode != "full"
        result = predict(sym, fast=fast)

        data = _sanitize_for_json({
            "symbol": result.symbol,
            "action": result.action,
            "confidence": result.confidence,
            "price_current": result.price_current,
            "signals": result.signals,
            "reasons": result.reasons,
            "weight_source": result.weight_source,
            "weights_used": result.weights_used,
            "cached": False,
        })
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/signal/news/<symbol>")
def api_signal_news(symbol):
    """Get news sentiment signal for a stock (slow — FinBERT)."""
    sym = symbol.upper()
    try:
        is_my = sym.endswith(".KL")
        if is_my:
            from src.data_sources.news_my import get_my_news_signal
            sig = get_my_news_signal(sym)
        else:
            from src.data_sources.news_sentiment import get_news_signal
            sig = get_news_signal(sym)
        return jsonify({"signal": sig})
    except Exception as e:
        return jsonify({"signal": {"signal": "neutral", "strength": 0.5, "reasons": [str(e)]}})


@app.route("/api/signal/social/<symbol>")
def api_signal_social(symbol):
    """Get social media sentiment signal."""
    try:
        from src.data_sources.social_media import get_social_signal
        sig = get_social_signal(symbol.upper())
        return jsonify({"signal": sig})
    except Exception as e:
        return jsonify({"signal": {"signal": "neutral", "strength": 0.5, "reasons": [str(e)]}})


@app.route("/api/signal/geopolitical")
def api_signal_geopolitical():
    """Get geopolitical signal."""
    try:
        from src.data_sources.geopolitical import get_geopolitical_signal
        sig = get_geopolitical_signal()
        return jsonify({"signal": sig})
    except Exception as e:
        return jsonify({"signal": {"signal": "neutral", "strength": 0.5, "reasons": [str(e)]}})


@app.route("/api/signal/earnings/<symbol>")
def api_signal_earnings(symbol):
    """Get earnings signal for a stock (EPS surprise, beat rate, upcoming dates)."""
    try:
        from src.data_sources.earnings import get_earnings_signal
        sig = get_earnings_signal(symbol.upper())
        return jsonify({"signal": sig})
    except Exception as e:
        return jsonify({"signal": {"signal": "neutral", "strength": 0.5, "reasons": [str(e)]}})


@app.route("/api/earnings/history/<symbol>")
def api_earnings_history(symbol):
    """Get stored earnings history for a stock."""
    from src.database import get_earnings_history
    try:
        history = get_earnings_history(symbol.upper())
        return jsonify({"earnings": history, "symbol": symbol.upper()})
    except Exception as e:
        return jsonify({"error": str(e), "earnings": []}), 500


@app.route("/api/model-info")
def api_model_info():
    """Get comprehensive model information for the Model tab."""
    import json as _json
    from pathlib import Path

    result = {}

    # Metrics
    metrics_path = Path("models/metrics.json")
    if metrics_path.exists():
        try:
            with open(metrics_path) as f:
                result["metrics"] = _json.load(f)
        except Exception:
            result["metrics"] = None

    # Feature importance (top 30)
    fi_path = Path("models/feature_importance.csv")
    if fi_path.exists():
        try:
            import csv
            with open(fi_path) as f:
                reader = csv.DictReader(f)
                features = []
                for row in reader:
                    features.append({
                        "feature": row["feature"],
                        "importance": round(float(row["importance"]), 4),
                    })
                result["feature_importance"] = features[:30]
        except Exception:
            result["feature_importance"] = []

    # Weights
    weights_path = Path("models/optimized_weights.json")
    if weights_path.exists():
        try:
            with open(weights_path) as f:
                result["weights"] = _json.load(f)
        except Exception:
            result["weights"] = None

    # Training data stats
    try:
        from src.database import get_connection
        conn = get_connection()
        stats = conn.execute("""
            SELECT COUNT(*) as rows, COUNT(DISTINCT symbol) as stocks,
                   MIN(date) as first_date, MAX(date) as last_date
            FROM training_data
        """).fetchone()
        daily = conn.execute("SELECT COUNT(*) as rows FROM daily_features").fetchone()
        gdelt = conn.execute("SELECT COUNT(*) as rows FROM gdelt_history").fetchone()
        earnings = conn.execute("SELECT COUNT(*) as rows FROM earnings_history").fetchone()
        conn.close()
        result["data"] = {
            "training_rows": stats["rows"],
            "stocks": stats["stocks"],
            "date_range": f"{stats['first_date']} to {stats['last_date']}",
            "daily_features_rows": daily["rows"],
            "gdelt_rows": gdelt["rows"],
            "earnings_rows": earnings["rows"],
        }
    except Exception:
        result["data"] = None

    # Feature categories (for the transparency table)
    result["feature_categories"] = [
        {"name": "Price", "features": ["open", "high", "low", "close", "volume"], "source": "yfinance", "count": 5},
        {"name": "Moving Averages", "features": ["SMA 20/50", "EMA 9/12/21/26"], "source": "Calculated", "count": 6},
        {"name": "MACD", "features": ["MACD", "Signal Line", "Histogram"], "source": "Calculated", "count": 3},
        {"name": "Oscillators", "features": ["RSI", "Stochastic %K/%D", "Williams %R", "CCI"], "source": "Calculated", "count": 5},
        {"name": "Trend", "features": ["ADX", "+DI/-DI", "Parabolic SAR"], "source": "Calculated", "count": 4},
        {"name": "Volatility", "features": ["ATR", "Bollinger Bands", "Volatility", "BB Width"], "source": "Calculated", "count": 5},
        {"name": "Volume", "features": ["OBV", "VWAP", "Volume Ratio", "Volume Trend"], "source": "Calculated", "count": 4},
        {"name": "Ichimoku", "features": ["Tenkan", "Kijun", "Span A/B", "Cloud Position"], "source": "Calculated", "count": 6},
        {"name": "Market Context", "features": ["SPY/KLCI Close", "VIX", "Market Regime", "Relative Strength"], "source": "yfinance", "count": 6},
        {"name": "Calendar", "features": ["Day of Week", "Month", "Monday/Friday Flags", "Month End"], "source": "Calculated", "count": 5},
        {"name": "Momentum", "features": ["5-day/20-day Momentum", "Acceleration", "Price Gap", "EMA Convergence"], "source": "Calculated", "count": 5},
        {"name": "52-Week", "features": ["% from High", "% from Low", "Position in Range"], "source": "Calculated", "count": 3},
        {"name": "Streaks", "features": ["Consecutive Up Days", "Consecutive Down Days"], "source": "Calculated", "count": 2},
        {"name": "Sentiment", "features": ["News Sentiment", "Reddit", "Figure Activity", "GDELT Tone", "Fear & Greed"], "source": "FinBERT / PRAW / GDELT", "count": 8},
        {"name": "Earnings", "features": ["EPS Surprise %", "Days Since Earnings", "Beat Rate", "Momentum"], "source": "Finnhub", "count": 4},
        {"name": "Engineered Signals", "features": ["MA Position Ratios", "Zone Flags (RSI/Stoch)", "MACD Cross", "ADX Strong"], "source": "Derived", "count": 8},
    ]

    return jsonify(result)


@app.route("/api/weights")
def api_weights():
    """Get current active signal weights and optimization status."""
    from src.analysis.predictor import get_active_weights
    import json
    from pathlib import Path

    us_weights, us_source = get_active_weights("US")
    my_weights, my_source = get_active_weights("MY")

    opt_info = None
    opt_path = Path("models/optimized_weights.json")
    if opt_path.exists():
        try:
            with open(opt_path) as f:
                opt = json.load(f)
            opt_info = {
                "optimized_at": opt.get("optimized_at"),
                "method": opt.get("method"),
                "us_improvement": opt.get("US", {}).get("improvement"),
                "my_improvement": opt.get("MY", {}).get("improvement"),
            }
        except Exception:
            pass

    return jsonify({
        "US": {"weights": us_weights, "source": us_source},
        "MY": {"weights": my_weights, "source": my_source},
        "optimization": opt_info,
    })


@app.route("/api/quote/<symbol>")
def api_quote(symbol):
    """Get real-time quote for a stock."""
    from src.data_sources.stock_prices import get_realtime_quote

    try:
        quote = get_realtime_quote(symbol.upper())
        return jsonify(quote)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quotes")
def api_quotes_batch():
    """Batch quotes for watchlist - lightweight endpoint for auto-refresh."""
    from src.data_sources.stock_prices import get_realtime_quote

    symbols = request.args.get("symbols", "").upper().split(",")
    symbols = [s.strip() for s in symbols if s.strip()]
    if not symbols:
        return jsonify({"error": "No symbols provided"}), 400

    quotes = []
    for symbol in symbols[:20]:  # Cap at 20 to respect rate limits
        try:
            q = get_realtime_quote(symbol)
            quotes.append(q)
        except Exception:
            quotes.append({"symbol": symbol, "error": "Failed to fetch"})

    return jsonify({"quotes": quotes, "timestamp": datetime.now().isoformat()})


@app.route("/api/market-overview")
def api_market_overview():
    """Market overview: major indices, VIX, commodities, crypto."""
    from src.data_sources.stock_prices import get_realtime_quote

    market = request.args.get("market", "US").upper()

    if market == "MY":
        indicators = {
            "index": ["^KLSE"],                                     # KLCI
            "banking": ["1155.KL", "1295.KL", "1023.KL"],          # Maybank, PBB, CIMB
            "oil_gas": ["5183.KL", "5235.KL"],                     # PetChem, PGas
            "telco": ["6947.KL", "6888.KL"],                       # CelcomDigi, Axiata
            "plantation": ["5285.KL", "2445.KL"],                  # Sime Darby P, KLK
            "others": ["5347.KL", "5225.KL", "8869.KL"],           # TNB, IHH, Press Metal
            "global_ref": ["GLD", "USO", "BTC-USD"],               # Global references
        }
    else:
        indicators = {
            "indices": ["SPY", "QQQ", "DIA", "IWM"],       # S&P500, Nasdaq, Dow, Russell
            "volatility": ["VXX"],                            # VIX proxy
            "commodities": ["GLD", "USO", "SLV"],            # Gold, Oil, Silver
            "crypto": ["BTC-USD", "ETH-USD"],                 # Bitcoin, Ethereum
            "bonds": ["TLT", "SHY"],                          # Long/short term bonds
            "sectors_top": ["XLK", "XLF", "XLE", "XLV"],     # Tech, Finance, Energy, Health
        }

    result = {}
    for category, symbols in indicators.items():
        result[category] = []
        for symbol in symbols:
            try:
                q = get_realtime_quote(symbol)
                result[category].append(q)
            except Exception:
                result[category].append({"symbol": symbol, "error": "Failed"})

    return jsonify({"overview": result, "timestamp": datetime.now().isoformat()})


@app.route("/api/history/<symbol>")
def api_history(symbol):
    """Get historical price data for charting."""
    from src.data_sources.stock_prices import get_historical_prices

    period = request.args.get("period", "6mo")
    try:
        df = get_historical_prices(symbol.upper(), period=period)
        if df.empty:
            return jsonify({"error": "No data"}), 404

        import math
        def _clean(lst):
            result = []
            for v in lst:
                try:
                    result.append(None if (v is None or math.isnan(v)) else float(v))
                except (TypeError, ValueError):
                    result.append(v)
            return result

        def _safe(col, decimals=2):
            if col in df.columns:
                return _clean(df[col].round(decimals).tolist())
            return []

        data = {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            # OHLCV
            "close": _safe("Close"), "open": _safe("Open"),
            "high": _safe("High"), "low": _safe("Low"),
            "volume": _clean(df["Volume"].tolist()),
            # Existing indicators
            "sma_20": _safe("SMA_20"), "sma_50": _safe("SMA_50"),
            "rsi": _safe("RSI"), "macd": _safe("MACD", 4),
            "signal_line": _safe("Signal_Line", 4),
            "bb_upper": _safe("BB_Upper"), "bb_lower": _safe("BB_Lower"),
            # New: Moving Averages
            "ema_9": _safe("EMA_9"), "ema_21": _safe("EMA_21"),
            # New: MACD Histogram
            "macd_hist": _safe("MACD_Hist", 4),
            # New: Stochastic
            "stoch_k": _safe("Stoch_K"), "stoch_d": _safe("Stoch_D"),
            # New: Williams %R
            "williams_r": _safe("Williams_R"),
            # New: ADX + DMI
            "adx": _safe("ADX"), "plus_di": _safe("Plus_DI"), "minus_di": _safe("Minus_DI"),
            # New: ATR
            "atr": _safe("ATR", 4),
            # New: OBV
            "obv": _clean(df["OBV"].tolist()) if "OBV" in df.columns else [],
            # New: VWAP
            "vwap": _safe("VWAP"),
            # New: CCI
            "cci": _safe("CCI"),
            # New: Parabolic SAR
            "psar": _safe("PSAR"),
            # New: Ichimoku
            "ichi_tenkan": _safe("Ichi_Tenkan"),
            "ichi_kijun": _safe("Ichi_Kijun"),
            "ichi_span_a": _safe("Ichi_SpanA"),
            "ichi_span_b": _safe("Ichi_SpanB"),
        }

        # Fibonacci levels (not time-series, just key levels)
        from src.data_sources.stock_prices import get_fibonacci_levels
        data["fibonacci"] = get_fibonacci_levels(df)

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fundamentals/<symbol>")
def api_fundamentals(symbol):
    """Get fundamental metrics for a stock."""
    import yfinance as yf

    try:
        info = yf.Ticker(symbol.upper()).info
        def _g(key):
            v = info.get(key)
            if v is None:
                return None
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return v

        return jsonify({
            "symbol": symbol.upper(),
            "pe_ratio": _g("trailingPE"),
            "forward_pe": _g("forwardPE"),
            "pb_ratio": _g("priceToBook"),
            "eps": _g("trailingEps"),
            "eps_growth": _g("earningsQuarterlyGrowth"),
            "roe": _g("returnOnEquity"),
            "debt_to_equity": _g("debtToEquity"),
            "free_cash_flow": _g("freeCashflow"),
            "revenue": _g("totalRevenue"),
            "profit_margin": _g("profitMargins"),
            "dividend_yield": _g("dividendYield"),
            "market_cap": _g("marketCap"),
            "beta": _g("beta"),
            "52w_high": _g("fiftyTwoWeekHigh"),
            "52w_low": _g("fiftyTwoWeekLow"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/market-movers")
def api_market_movers():
    """Get influential figure activity relevant to a stock."""
    from src.data_sources.news_sentiment import get_figure_signal

    symbol = request.args.get("symbol", "SPY").upper()
    try:
        data = get_figure_signal(symbol)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "figures": [], "total_mentions": 0}), 500


@app.route("/api/sectors")
def api_sectors():
    """Get analysis for all industry sectors."""
    from src.analysis.sector_analysis import analyze_all_sectors, get_sectors

    market = request.args.get("market", "US").upper()

    try:
        sectors_def = get_sectors(market)
        results = analyze_all_sectors(market=market)
        sectors = []
        for r in results:
            sectors.append({
                "name": r.name,
                "description": r.description,
                "etf": r.etf,
                "action": r.action,
                "confidence": r.confidence,
                "score": r.avg_score,
                "market": market,
                "symbols": sectors_def[r.name]["symbols"],
                "signal_breakdown": r.signal_breakdown,
                "reasons": r.top_reasons,
            })
        return jsonify({"sectors": sectors, "market": market, "timestamp": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sector/<sector_name>")
def api_sector_detail(sector_name):
    """Get detailed analysis for a single sector."""
    from src.analysis.sector_analysis import analyze_sector_etf, SECTORS

    # URL-decode and match sector name
    matched = None
    for name in SECTORS:
        if name.lower().replace(" ", "-") == sector_name.lower().replace(" ", "-"):
            matched = name
            break

    if not matched:
        return jsonify({"error": f"Unknown sector: {sector_name}"}), 404

    try:
        result = analyze_sector_etf(matched)
        return jsonify({
            "name": result.name,
            "description": result.description,
            "etf": result.etf,
            "action": result.action,
            "confidence": result.confidence,
            "score": result.avg_score,
            "symbols": SECTORS[matched]["symbols"],
            "signal_breakdown": result.signal_breakdown,
            "reasons": result.top_reasons,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news")
def api_news():
    """Get latest market news with sentiment and save to DB."""
    from src.data_sources.news_sentiment import fetch_market_news
    from src.database import save_news

    try:
        articles = fetch_market_news()
        # Save to database
        for a in articles:
            if "error" not in a:
                save_news(
                    platform="finnhub",
                    headline=a.get("headline", ""),
                    summary=a.get("summary", ""),
                    url=a.get("url", ""),
                    source_name=a.get("source", ""),
                    sentiment_label=a.get("sentiment", {}).get("label", ""),
                    sentiment_score=a.get("sentiment", {}).get("score", 0),
                )
        return jsonify({"articles": articles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/all")
def api_news_all():
    """Get all stored news from database (all platforms)."""
    from src.database import get_all_news, get_news_stats

    platform = request.args.get("platform")
    limit = int(request.args.get("limit", 200))
    try:
        news = get_all_news(limit=limit, platform=platform)
        stats = get_news_stats()
        return jsonify({"news": news, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/my")
def api_news_my():
    """Get Malaysian news from all MY sources (Google News, TheEdge, NewsAPI)."""
    from src.data_sources.news_my import fetch_all_my_news
    from src.database import save_news

    try:
        articles = fetch_all_my_news()
        for a in articles:
            save_news(
                platform=a.get("platform", "google-news-my"),
                headline=a.get("headline", ""),
                summary=a.get("summary", ""),
                url=a.get("url", ""),
                source_name=a.get("source", ""),
                sentiment_label=a.get("sentiment", {}).get("label", ""),
                sentiment_score=a.get("sentiment", {}).get("score", 0),
            )
        return jsonify({"articles": articles, "count": len(articles)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/fetch-all")
def api_news_fetch_all():
    """Fetch news from ALL platforms, save to DB, return combined."""
    from src.data_sources.news_sentiment import (
        fetch_market_news, fetch_influential_figure_news
    )
    from src.data_sources.geopolitical import fetch_geopolitical_events
    from src.data_sources.news_my import fetch_all_my_news, fetch_my_influential_news
    from src.database import save_news, get_all_news, get_news_stats

    saved_count = 0

    # 1. Finnhub market news
    try:
        articles = fetch_market_news()
        for a in articles:
            if "error" not in a:
                save_news(
                    platform="finnhub",
                    headline=a.get("headline", ""),
                    summary=a.get("summary", ""),
                    url=a.get("url", ""),
                    source_name=a.get("source", ""),
                    sentiment_label=a.get("sentiment", {}).get("label", ""),
                    sentiment_score=a.get("sentiment", {}).get("score", 0),
                )
                saved_count += 1
    except Exception:
        pass

    # 2. Influential figures news
    try:
        figure_news = fetch_influential_figure_news()
        for n in figure_news:
            if "error" not in n:
                save_news(
                    platform="finnhub-figures",
                    headline=n.get("headline", ""),
                    source_name=n.get("source", ""),
                    sentiment_label=n.get("sentiment", {}).get("label", ""),
                    sentiment_score=n.get("sentiment", {}).get("score", 0),
                    related_figure=n.get("figure", ""),
                )
                saved_count += 1
    except Exception:
        pass

    # 3. GDELT geopolitical events
    try:
        events = fetch_geopolitical_events(max_records=30)
        for e in events:
            if "error" not in e:
                tone = e.get("tone", 0)
                label = "positive" if tone > 1 else "negative" if tone < -1 else "neutral"
                save_news(
                    platform="gdelt",
                    headline=e.get("title", ""),
                    url=e.get("url", ""),
                    source_name=e.get("source", ""),
                    sentiment_label=label,
                    sentiment_score=round(tone / 10, 3),
                    related_symbol=e.get("keyword", ""),
                )
                saved_count += 1
    except Exception:
        pass

    # 4. Malaysia news (Google News RSS + TheEdge + NewsAPI)
    try:
        my_articles = fetch_all_my_news()
        for a in my_articles:
            save_news(
                platform=a.get("platform", "google-news-my"),
                headline=a.get("headline", ""),
                summary=a.get("summary", ""),
                url=a.get("url", ""),
                source_name=a.get("source", ""),
                sentiment_label=a.get("sentiment", {}).get("label", ""),
                sentiment_score=a.get("sentiment", {}).get("score", 0),
            )
            saved_count += 1
    except Exception:
        pass

    # 5. Malaysian influential figures
    try:
        my_figures = fetch_my_influential_news()
        for n in my_figures:
            save_news(
                platform="google-news-my",
                headline=n.get("headline", ""),
                source_name=n.get("source", ""),
                sentiment_label=n.get("sentiment", {}).get("label", ""),
                sentiment_score=n.get("sentiment", {}).get("score", 0),
                related_figure=n.get("figure", ""),
            )
            saved_count += 1
    except Exception:
        pass

    news = get_all_news(limit=200)
    stats = get_news_stats()
    return jsonify({
        "news": news,
        "stats": stats,
        "new_articles_saved": saved_count,
    })


@app.route("/api/geopolitical")
def api_geopolitical():
    """Get geopolitical events signal."""
    from src.data_sources.geopolitical import get_geopolitical_signal

    try:
        signal = get_geopolitical_signal()
        return jsonify(signal)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== BACKTESTING =====

@app.route("/api/backtest/<symbol>")
def api_backtest(symbol):
    """Run backtest for a symbol."""
    from src.analysis.backtester import backtest_technical

    period = request.args.get("period", "1y")
    hold_days = int(request.args.get("hold_days", 5))
    try:
        result = backtest_technical(symbol.upper(), period=period, hold_days=hold_days)
        return jsonify(result.summary() | {"trades": result.trades})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== PORTFOLIO =====

@app.route("/api/portfolio/summary")
def api_portfolio_summary():
    """Get portfolio summary with holdings and P&L."""
    from src.analysis.portfolio import get_portfolio_summary

    name = request.args.get("name", "default")
    try:
        return jsonify(get_portfolio_summary(name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio/trade", methods=["POST"])
def api_portfolio_trade():
    """Execute a virtual trade."""
    from src.analysis.portfolio import execute_trade

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    try:
        result = execute_trade(
            portfolio_name=data.get("portfolio", "default"),
            symbol=data.get("symbol", ""),
            action=data.get("action", "BUY"),
            quantity=float(data.get("quantity", 0)),
            price=float(data.get("price", 0)),
            signal_action=data.get("signal_action", ""),
            signal_confidence=float(data.get("signal_confidence", 0)),
            notes=data.get("notes", ""),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio/trades")
def api_portfolio_trades():
    """Get trade history."""
    from src.analysis.portfolio import get_trade_history

    name = request.args.get("name", "default")
    try:
        return jsonify({"trades": get_trade_history(name)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== ALERTS =====

@app.route("/api/alerts")
def api_alerts_list():
    """Get all alerts."""
    from src.analysis.alerts import get_alerts

    active_only = request.args.get("active", "true").lower() == "true"
    try:
        return jsonify({"alerts": get_alerts(active_only)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/create", methods=["POST"])
def api_alerts_create():
    """Create a new alert."""
    from src.analysis.alerts import create_alert

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    try:
        result = create_alert(
            symbol=data.get("symbol", ""),
            alert_type=data.get("alert_type", "price"),
            condition=data.get("condition", "above"),
            threshold=float(data.get("threshold", 0)),
            message=data.get("message", ""),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/check")
def api_alerts_check():
    """Check all active alerts against current data."""
    from src.analysis.alerts import check_alerts

    try:
        triggered = check_alerts()
        return jsonify({"triggered": triggered, "count": len(triggered)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
def api_alerts_delete(alert_id):
    from src.analysis.alerts import delete_alert
    try:
        delete_alert(alert_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== MARKET INDICATORS =====

@app.route("/api/fear-greed")
def api_fear_greed():
    """Get Fear & Greed Index."""
    from src.analysis.market_indicators import calculate_fear_greed

    market = request.args.get("market", "US").upper()
    try:
        return jsonify(calculate_fear_greed(market))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/correlations")
def api_correlations():
    """Get correlation matrix for given symbols."""
    from src.analysis.market_indicators import calculate_correlations

    symbols = request.args.get("symbols", "SPY,QQQ,AAPL,TSLA,GLD,TLT").split(",")
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    period = request.args.get("period", "6mo")
    try:
        return jsonify(calculate_correlations(symbols, period))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/earnings")
def api_earnings():
    """Get upcoming earnings calendar."""
    from src.analysis.market_indicators import get_earnings_calendar

    symbols = request.args.get("symbols", "").split(",")
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        from config.settings import DEFAULT_SYMBOLS
        symbols = DEFAULT_SYMBOLS
    try:
        return jsonify({"earnings": get_earnings_calendar(symbols)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== PREDICTION HISTORY & TRENDS =====

@app.route("/api/predictions/history")
def api_prediction_history():
    """Get stored prediction history."""
    from src.database import get_all_prediction_history

    limit = int(request.args.get("limit", 500))
    try:
        history = get_all_prediction_history(limit=limit)
        return jsonify({"predictions": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/predictions/trend/<symbol>")
def api_prediction_trend(symbol):
    """Get prediction score trend for a specific symbol."""
    from src.database import get_prediction_trend

    days = int(request.args.get("days", 30))
    try:
        trend = get_prediction_trend(symbol.upper(), days=days)
        # Filter out corrupt records stored before scoring system was working
        trend = [t for t in trend if not (t.get("score") == 0 and t.get("price") == 0 and t.get("confidence") == 0)]
        return jsonify({"symbol": symbol.upper(), "trend": trend})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/predictions/symbols")
def api_prediction_symbols():
    """Get list of all symbols that have been predicted."""
    from src.database import get_connection

    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT symbol, COUNT(*) as count,
                      MAX(created_at) as last_predicted
               FROM predictions GROUP BY symbol ORDER BY count DESC"""
        ).fetchall()
        conn.close()
        return jsonify({"symbols": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/industry-analysis")
def api_news_industry_analysis():
    """Classify stored news by industry and return AI verdict per sector."""
    from src.analysis.industry_classifier import analyze_industry_news
    from src.database import get_all_news, get_news_stats, get_news_latest_fetched

    limit = int(request.args.get("limit", 500))
    hours_back = request.args.get("hours_back")
    hours_back = int(hours_back) if hours_back else None
    try:
        news = get_all_news(limit=limit, hours_back=hours_back)
        industries = analyze_industry_news(news)
        stats = get_news_stats()
        return jsonify({
            "industries": industries,
            "total_articles": len(news),
            "stats": stats,
            "latest_fetched": get_news_latest_fetched(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/status")
def api_news_status():
    """Return latest fetch time and article counts — lightweight poll for the UI."""
    from src.database import get_news_latest_fetched, get_news_stats
    try:
        return jsonify({
            "latest_fetched": get_news_latest_fetched(),
            "stats": get_news_stats(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sectors/history")
def api_sector_history():
    """Get sector prediction history for trend charts."""
    from src.database import get_sector_history

    sector = request.args.get("sector")
    try:
        history = get_sector_history(sector_name=sector)
        return jsonify({"history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/markets")
def api_markets():
    """Get available markets and their config."""
    from config.settings import MARKETS, MY_STOCK_NAMES

    return jsonify({
        "markets": MARKETS,
        "my_stock_names": MY_STOCK_NAMES,
    })


# ===== WATCHLIST =====

@app.route("/api/watchlist")
def api_watchlist():
    """Get user's watchlist with live quotes."""
    import yfinance as yf
    from src.database import get_watchlist

    items = get_watchlist()
    results = []
    for item in items:
        sym = item["symbol"]
        quote = {}
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            price = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            if price and prev:
                quote = {
                    "price": round(price, 3),
                    "prev_close": round(prev, 3),
                    "change_abs": round(price - prev, 3),
                    "change_pct": round((price - prev) / prev * 100, 2),
                }
        except Exception:
            pass

        # Check alerts
        alert_triggered = None
        if quote.get("price"):
            if item.get("alert_above") and quote["price"] >= item["alert_above"]:
                alert_triggered = "above"
            elif item.get("alert_below") and quote["price"] <= item["alert_below"]:
                alert_triggered = "below"

        results.append({**item, **quote, "alert_triggered": alert_triggered})

    return jsonify({"watchlist": results})


@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    """Add a stock to the watchlist."""
    from src.database import add_to_watchlist

    data = request.get_json(force=True)
    symbol = data.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    name = data.get("name", "")
    note = data.get("note", "")
    alert_above = data.get("alert_above")
    alert_below = data.get("alert_below")

    added = add_to_watchlist(symbol, name=name, note=note,
                             alert_above=alert_above, alert_below=alert_below)
    return jsonify({"ok": True, "added": added, "symbol": symbol})


@app.route("/api/watchlist/<symbol>", methods=["DELETE"])
def api_watchlist_remove(symbol):
    """Remove a stock from the watchlist."""
    from src.database import remove_from_watchlist

    sym = symbol.strip().upper()
    removed = remove_from_watchlist(sym)
    return jsonify({"ok": True, "removed": removed, "symbol": sym})


@app.route("/api/watchlist/<symbol>", methods=["PUT"])
def api_watchlist_update(symbol):
    """Update note or alerts for a watchlist stock."""
    from src.database import update_watchlist_item

    data = request.get_json(force=True)
    sym = symbol.strip().upper()
    updated = update_watchlist_item(
        sym,
        note=data.get("note"),
        alert_above=data.get("alert_above"),
        alert_below=data.get("alert_below"),
    )
    return jsonify({"ok": True, "updated": updated, "symbol": sym})


# ===== BURSA MARKET =====

@app.route("/api/bursa/industries")
def api_bursa_industries():
    """Return industry structure with live quotes for all stocks."""
    import yfinance as yf
    from config.settings import BURSA_INDUSTRIES

    result = []
    for industry_name, industry_data in BURSA_INDUSTRIES.items():
        stocks_out = []
        for s in industry_data["stocks"]:
            sym = s["symbol"]
            try:
                fi = yf.Ticker(sym).fast_info
                price = fi.last_price or 0
                prev  = fi.previous_close or 0
                chg   = round(price - prev, 4) if prev else 0
                pct   = round(chg / prev * 100, 2) if prev else 0
                stocks_out.append({
                    "symbol":     sym,
                    "name":       s["name"],
                    "price":      round(float(price), 3) if price else None,
                    "change_abs": chg,
                    "change_pct": pct,
                    "volume":     int(fi.last_volume or 0),
                })
            except Exception:
                stocks_out.append({"symbol": sym, "name": s["name"],
                                   "price": None, "change_abs": 0, "change_pct": 0, "volume": 0})
        result.append({
            "industry": industry_name,
            "icon": industry_data["icon"],
            "stocks": stocks_out,
        })

    return jsonify({"industries": result, "timestamp": datetime.now().isoformat()})


@app.route("/api/bursa/watchlist")
def api_bursa_watchlist():
    """Live quotes for all Bursa watchlist stocks + KLCI index."""
    import yfinance as yf
    from config.settings import MARKETS, MY_STOCK_NAMES

    symbols = ["^KLSE"] + MARKETS["MY"]["default_symbols"]
    quotes = []
    for sym in symbols:
        try:
            fi = yf.Ticker(sym).fast_info
            price = fi.last_price or 0
            prev  = fi.previous_close or 0
            chg   = round(price - prev, 4) if prev else 0
            pct   = round(chg / prev * 100, 2) if prev else 0
            quotes.append({
                "symbol":    sym,
                "name":      MY_STOCK_NAMES.get(sym, sym),
                "price":     round(price, 3),
                "prev_close": round(prev, 3),
                "change_abs": chg,
                "change_pct": pct,
                "volume":    int(fi.last_volume or 0),
                "day_high":  round(fi.day_high or 0, 3),
                "day_low":   round(fi.day_low or 0, 3),
            })
        except Exception as e:
            quotes.append({"symbol": sym, "name": MY_STOCK_NAMES.get(sym, sym), "error": str(e)})

    return jsonify({"quotes": quotes, "timestamp": datetime.now().isoformat()})


@app.route("/api/resolve-symbol")
def api_resolve_symbol():
    """Resolve a user-typed name/alias to the correct Yahoo Finance ticker.
    e.g. 'INARI' -> '0166.KL', 'MAYBANK' -> '1155.KL'
    Returns {symbol, resolved} where resolved is the canonical ticker."""
    from config.settings import MY_STOCK_NAMES

    raw = request.args.get("q", "").strip().upper()
    if not raw:
        return jsonify({"error": "No query"}), 400

    # Already a valid-looking ticker — return as-is
    if raw.endswith(".KL") or raw.startswith("^"):
        return jsonify({"symbol": raw, "resolved": raw})

    # Build reverse map: name keywords → code
    for code, name in MY_STOCK_NAMES.items():
        name_upper = name.upper()
        # Match if query equals the first word of the name or is contained in the name
        if raw == name_upper or raw in name_upper or name_upper.startswith(raw):
            return jsonify({"symbol": raw, "resolved": code, "name": name})

    # Not found in Bursa map — return as-is (could be a US stock)
    return jsonify({"symbol": raw, "resolved": raw})


@app.route("/api/names")
def api_names():
    """Resolve display names for a list of symbols. Fast — uses fast_info only."""
    import yfinance as yf
    from config.settings import MY_STOCK_NAMES

    raw = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    result = {}
    for sym in symbols:
        try:
            name = MY_STOCK_NAMES.get(sym)
            if not name:
                t = yf.Ticker(sym)
                info = t.info
                name = info.get("longName") or info.get("shortName") or sym
            result[sym] = name
        except Exception:
            result[sym] = sym
    return jsonify(result)


@app.route("/api/prices")
def api_prices():
    """Resolve current prices for a list of symbols. Uses fast_info for speed.
    Falls back to appending .KL for Bursa symbols stored without the suffix."""
    import yfinance as yf

    raw = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    result = {}
    for sym in symbols:
        price = None
        for candidate in [sym, sym + ".KL"] if not sym.endswith(".KL") else [sym]:
            try:
                fi = yf.Ticker(candidate).fast_info
                p = fi.last_price or 0
                if p:
                    price = round(float(p), 3)
                    break
            except Exception:
                continue
        result[sym] = price
    return jsonify(result)


@app.route("/api/orderbook/<symbol>")
def api_order_book(symbol):
    """Order book / market depth. Uses IB Gateway if running, falls back to yfinance Level 1."""
    from src.data_sources.order_book import get_order_book
    depth = int(request.args.get("depth", 10))
    result = get_order_book(symbol.upper(), depth=depth)
    return jsonify(result)


@app.route("/api/ib/status")
def api_ib_status():
    """Check whether IB Gateway is connected."""
    from src.data_sources.order_book import ib_status
    return jsonify(ib_status())


@app.route("/api/bursa/quote/<symbol>")
def api_bursa_quote(symbol):
    """Full quote + fundamentals for one stock."""
    import yfinance as yf
    from config.settings import MY_STOCK_NAMES

    sym = symbol.upper()
    if not sym.endswith(".KL") and not sym.startswith("^"):
        sym += ".KL"
    try:
        t    = yf.Ticker(sym)
        fi   = t.fast_info
        info = t.info
        price = fi.last_price or 0
        prev  = fi.previous_close or 0
        chg   = round(price - prev, 4) if prev else 0
        pct   = round(chg / prev * 100, 2) if prev else 0
        return jsonify({
            "symbol":           sym,
            "name":             info.get("longName") or MY_STOCK_NAMES.get(sym, sym),
            "price":            round(price, 3),
            "prev_close":       round(prev, 3),
            "change_abs":       chg,
            "change_pct":       pct,
            "volume":           int(fi.last_volume or 0),
            "day_high":         round(fi.day_high or 0, 3),
            "day_low":          round(fi.day_low or 0, 3),
            "week52_high":      info.get("fiftyTwoWeekHigh"),
            "week52_low":       info.get("fiftyTwoWeekLow"),
            "market_cap":       info.get("marketCap"),
            "pe_ratio":         info.get("trailingPE"),
            "dividend_yield":   info.get("dividendYield"),
            "bid":              info.get("bid"),
            "ask":              info.get("ask"),
            "open":             info.get("regularMarketOpen"),
            "exchange":         info.get("exchange"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bursa/chart/<symbol>")
def api_bursa_chart(symbol):
    """Intraday or multi-day OHLCV data for charting."""
    import yfinance as yf

    sym = symbol.upper()
    if not sym.endswith(".KL") and not sym.startswith("^"):
        sym += ".KL"

    period   = request.args.get("period", "1d")
    interval = {"1d": "1m", "5d": "15m", "1mo": "1d", "3mo": "1d"}.get(period, "1d")

    try:
        hist = yf.Ticker(sym).history(period=period, interval=interval)
        if hist.empty:
            return jsonify({"error": "No data"}), 404

        fmt = "%H:%M" if period == "1d" else "%Y-%m-%d"
        return jsonify({
            "symbol": sym,
            "period": period,
            "times":  hist.index.strftime(fmt).tolist(),
            "open":   hist["Open"].round(3).tolist(),
            "close":  hist["Close"].round(3).tolist(),
            "high":   hist["High"].round(3).tolist(),
            "low":    hist["Low"].round(3).tolist(),
            "volume": hist["Volume"].tolist(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bursa/snapshot", methods=["POST"])
def api_bursa_snapshot():
    """Manually trigger a price snapshot (stores to DB)."""
    import subprocess
    import sys
    try:
        subprocess.Popen(
            [sys.executable, "price_tracker.py", "--force"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        return jsonify({"status": "snapshot started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bursa/accuracy")
def api_bursa_accuracy():
    """Prediction vs actual price comparison."""
    from src.database import get_prediction_accuracy
    limit = int(request.args.get("limit", 100))
    return jsonify(get_prediction_accuracy(limit=limit))


@app.route("/api/bursa/history/<symbol>")
def api_bursa_history(symbol):
    """Stored price snapshot history for a symbol."""
    from src.database import get_price_history
    sym   = symbol.upper()
    if not sym.endswith(".KL") and not sym.startswith("^"):
        sym += ".KL"
    hours = int(request.args.get("hours", 24))
    return jsonify({"symbol": sym, "history": get_price_history(sym, hours=hours)})


def _preload_models():
    """Pre-load heavy models at startup so first request is fast."""
    import threading

    def _load():
        try:
            # Pre-load FinBERT sentiment model (~30s)
            print("Pre-loading FinBERT sentiment model...")
            from src.data_sources.news_sentiment import _get_sentiment_pipeline
            _get_sentiment_pipeline()
            print("FinBERT loaded.")
        except Exception as e:
            print(f"FinBERT pre-load failed (non-critical): {e}")

        try:
            # Pre-load ML prediction models
            print("Pre-loading ML models...")
            from src.analysis.predictor import _load_ml_models
            _load_ml_models()
            print("ML models loaded.")
        except Exception:
            pass

    # Load in background thread so server starts immediately
    threading.Thread(target=_load, daemon=True).start()


# ===== CATALYST ALERTS =====

@app.route("/api/catalyst/alerts")
def api_catalyst_alerts():
    """Get current catalyst alerts (detected events + stock picks)."""
    from src.database import get_catalyst_alerts
    hours = int(request.args.get("hours", 24))
    try:
        alerts = get_catalyst_alerts(hours_back=hours)
        return jsonify({"alerts": alerts, "count": len(alerts)})
    except Exception as e:
        return jsonify({"error": str(e), "alerts": []}), 500


@app.route("/api/catalyst/scan", methods=["POST"])
def api_catalyst_scan():
    """Trigger a manual catalyst scan."""
    from src.analysis.catalyst import scan_catalysts
    from src.database import save_catalyst_scan
    import uuid

    hours = int(request.args.get("hours", 6))
    try:
        result = scan_catalysts(hours_back=hours, max_picks=10)
        scan_id = str(uuid.uuid4())[:8]
        save_catalyst_scan(scan_id, result.get("events", []), result.get("picks", []),
                           direct_picks=result.get("direct_picks", []))
        return jsonify({
            "scan_id": scan_id,
            "events": result.get("events", []),
            "picks": result.get("picks", []),
            "headlines_scanned": result.get("headlines_scanned", 0),
            "scanned_at": result.get("scanned_at", ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/catalyst/history")
def api_catalyst_history():
    """Get catalyst alert history with outcome tracking."""
    from src.database import get_catalyst_history
    days = int(request.args.get("days", 7))
    try:
        history = get_catalyst_history(days=days)
        return jsonify({"history": history, "count": len(history)})
    except Exception as e:
        return jsonify({"error": str(e), "history": []}), 500


# Pre-load models when imported by Gunicorn (preload_app=True)
# or when run directly
import os as _os
if _os.environ.get("GUNICORN_PRELOAD") or _os.environ.get("WERKZEUG_RUN_MAIN"):
    _preload_models()

if __name__ == "__main__":
    _preload_models()
    app.run(debug=True, host="0.0.0.0", port=5000)
