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


@app.route("/pro")
def pro_dashboard():
    """Professional analyst dashboard."""
    return render_template("pro.html")


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


@app.route("/api/markets")
def api_markets():
    """Get available markets and their config."""
    from config.settings import MARKETS, MY_STOCK_NAMES

    return jsonify({
        "markets": MARKETS,
        "my_stock_names": MY_STOCK_NAMES,
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
