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


@app.route("/api/predict/<symbol>")
def api_predict(symbol):
    """Run prediction for a single stock."""
    from src.analysis.predictor import predict

    try:
        result = predict(symbol.upper())
        return jsonify({
            "symbol": result.symbol,
            "action": result.action,
            "confidence": result.confidence,
            "price_current": result.price_current,
            "signals": result.signals,
            "reasons": result.reasons,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quote/<symbol>")
def api_quote(symbol):
    """Get real-time quote for a stock."""
    from src.data_sources.stock_prices import get_realtime_quote

    try:
        quote = get_realtime_quote(symbol.upper())
        return jsonify(quote)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<symbol>")
def api_history(symbol):
    """Get historical price data for charting."""
    from src.data_sources.stock_prices import get_historical_prices

    period = request.args.get("period", "6mo")
    try:
        df = get_historical_prices(symbol.upper(), period=period)
        if df.empty:
            return jsonify({"error": "No data"}), 404

        data = {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "close": df["Close"].round(2).tolist(),
            "open": df["Open"].round(2).tolist(),
            "high": df["High"].round(2).tolist(),
            "low": df["Low"].round(2).tolist(),
            "volume": df["Volume"].tolist(),
            "sma_20": df["SMA_20"].round(2).tolist(),
            "sma_50": df["SMA_50"].round(2).tolist(),
            "rsi": df["RSI"].round(2).tolist(),
            "macd": df["MACD"].round(4).tolist(),
            "signal_line": df["Signal_Line"].round(4).tolist(),
            "bb_upper": df["BB_Upper"].round(2).tolist(),
            "bb_lower": df["BB_Lower"].round(2).tolist(),
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sectors")
def api_sectors():
    """Get analysis for all industry sectors."""
    from src.analysis.sector_analysis import analyze_all_sectors, SECTORS

    try:
        results = analyze_all_sectors()
        sectors = []
        for r in results:
            sectors.append({
                "name": r.name,
                "description": r.description,
                "etf": r.etf,
                "action": r.action,
                "confidence": r.confidence,
                "score": r.avg_score,
                "symbols": SECTORS[r.name]["symbols"],
                "signal_breakdown": r.signal_breakdown,
                "reasons": r.top_reasons,
            })
        return jsonify({"sectors": sectors, "timestamp": datetime.now().isoformat()})
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


@app.route("/api/news/fetch-all")
def api_news_fetch_all():
    """Fetch news from ALL platforms, save to DB, return combined."""
    from src.data_sources.news_sentiment import (
        fetch_market_news, fetch_influential_figure_news
    )
    from src.data_sources.geopolitical import fetch_geopolitical_events
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
