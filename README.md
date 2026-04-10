# StockSight

Multi-signal stock prediction dashboard with AI-powered analysis for US (S&P 500) and Bursa Malaysia markets.

Combines 7 signal sources — technical indicators (15+), news sentiment (FinBERT NLP), social media (Reddit), geopolitical events (GDELT), influential figure monitoring, earnings surprises (EPS beat/miss), and an XGBoost/LightGBM ML ensemble (~107 features) — into a single prediction with AI-optimized signal weights.

**New: Catalyst Alerts** — scans news every 30 minutes, detects market-moving events (tariffs, rate decisions, supply chain disruptions, etc.), and predicts which stocks will rise or fall in the next 24 hours.

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/henrychong123/stock-prediction.git
cd stock-prediction
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the dashboard
python web/app.py
# Open http://localhost:5000
```

## Dashboard

**5 tabs:**

| Tab | What It Does |
|-----|-------------|
| **Home** | Dashboard overview: sector heatmap, prediction summary, active catalyst alerts. Sub-tabs: Sectors (11 GICS heatmap), Report (daily rankings with filters), Trends (prediction history + charts). |
| **Stocks** | Unified stock analysis — search any stock (US or Bursa), 15+ indicators, ML prediction, earnings, fundamentals. Toggle to Bursa Market view: 80 stocks, 8 industries, watchlist, order book. |
| **Catalyst** | News-driven 24h stock picks (75% accuracy). Scans 13 sources every 30 min, detects stock mentions (219 aliases), expands via knowledge graph (parent/subsidiary, supplier/customer, GLC peers). US + Bursa split. |
| **News** | News Intelligence Hub with FinBERT sentiment, AI industry classification, 13 platform sources. |
| **Settings** | AI model transparency: 107 features, accuracy metrics, feature importance, signal weights, training data stats. |

## Prediction Engine

**Cache-first architecture** — Pre-computed predictions served from SQLite in ~150ms. Live computation only when cache is stale.

| Mode | Speed | What runs |
|------|-------|-----------|
| **Cached** (default) | ~150ms | Reads from database |
| **Fast** (cache miss) | ~3-5s | Technical indicators + ML model + Earnings |
| **Full** (toggle) | ~15s | Above + news + Reddit + GDELT + figures (parallel with progress UI) |

**7 Signal weights** (US defaults):
| Signal | Weight |
|--------|--------|
| Technical | 22% |
| News Sentiment | 18% |
| ML Model | 18% |
| Social Media | 12% |
| Earnings | 12% |
| Momentum | 10% |
| Geopolitical | 8% |

Weights are AI-optimized via differential evolution on 291K rows of historical data. The dashboard shows a doughnut chart with the live weight distribution.

## ML Model

```bash
# Train models (requires historical data collection first)
python src/data/collect_historical.py    # 589 stocks x 2 years (~30 min)
python src/data/collect_earnings.py      # EPS history for 506 US stocks (~10 min)
python src/data/train_model.py           # XGBoost + LightGBM
python src/data/optimize_weights.py      # optimize signal weights
```

- **Data:** 292,244 rows, 587 stocks (S&P 500 + Bursa), **107 features**
- **Accuracy:** **57.0%** ensemble (3-class: UP/DOWN/FLAT), MAE 2.86%, R² 0.179
- **Feature categories:** 36 base OHLCV + indicators, 8 market context (SPY, VIX, treasury yields, DXY, sector ETF), 8 sentiment (news, reddit, GDELT, fear & greed), 4 earnings, 2 alternative (insider, analyst), 3 cross-asset (oil, gold, copper), 45+ engineered (calendar, momentum, 52-week, streaks, regime, lags, correlations)
- **Top features:** market_index_close, gold_close, above_cloud, treasury_2y, month, volatility, vix_close
- **Models:** XGBoost classifier, LightGBM classifier, XGBoost regressor

## Background Workers

Pre-compute all data so the dashboard serves instantly:

| Worker | Schedule | What It Does |
|--------|----------|-------------|
| `price_tracker.py` | Every 5 min (market hours) | Price snapshots |
| `news_tracker.py` | Every 30 min | News articles + FinBERT sentiment |
| `catalyst_scanner.py` | Every 30 min | Detect catalyst events, predict next rising/falling stocks + knowledge graph cascade |
| `social_collector.py` | Every 2 hours | Collect news from 13 sources (Yahoo Finance, i3investor, RSS feeds) |
| `daily_collector.py` | Daily 6:00 PM | Sentiment features + GDELT update |
| `batch_predict.py` | Daily 6:30 PM | Predictions for all 80 Bursa stocks |

```bash
# Register all scheduled tasks (run once)
setup_daily_collector.bat

# Or run catalyst scanner manually
python catalyst_scanner.py              # single scan
python catalyst_scanner.py --loop       # continuous (every 30 min)
```

## Data Collection

| Script | What | Size |
|--------|------|------|
| `collect_historical.py` | 2yr OHLCV + indicators + macro (yields, DXY, commodities, sector ETFs) | 292K rows |
| `collect_gdelt_history.py` | 2yr daily GDELT tone for 14 industries | 14.5K records |
| `collect_earnings.py` | Historical EPS actual vs estimate for US stocks | 2,010 records |
| `collect_insider.py` | Insider buy/sell transactions from SEC filings | 174K transactions |
| `collect_analyst.py` | Analyst buy/hold/sell recommendations | 2,012 records |
| `collect_news_history.py` | Historical news + FinBERT sentiment backfill | 1,193+ daily records |
| `daily_collector.py` | Daily sentiment/macro per stock | grows daily |
| `export_training.py` | Export to CSV for training | ~16MB |

Stock universe: `config/stock_universe.py` — 503 S&P 500 + 81 Bursa + 5 indices = 589 stocks.

## Industry Categories

All industry names are centralized in `config/industries.py` (single source of truth):
- 15 stock industries (Banking & Finance, Technology, Oil & Gas, etc.)
- 4 meta-categories for news classification (Geopolitical, Malaysia Economy, Global Markets, General Market)
- Guard test prevents naming drift across modules

## Project Structure

```
stock-prediction/
├── web/
│   ├── app.py                          # Flask app + 50+ API endpoints
│   ├── templates/dashboard.html        # Single-page dashboard
│   └── static/
│       ├── js/
│       │   ├── app.js                  # Core: state, API, charts, cache
│       │   ├── main.js                 # Tab router, event delegation
│       │   ├── tab-analysis.js         # Analysis (indicators, ML, earnings, weights)
│       │   ├── tab-sectors.js          # Sector heatmap
│       │   ├── tab-news.js             # News hub
│       │   ├── tab-trends.js           # Prediction trends
│       │   ├── tab-report.js           # Daily report
│       │   ├── tab-model.js            # AI model transparency dashboard
│       │   ├── tab-bursa.js            # Bursa market + watchlist + auto-refresh
│       │   ├── tab-catalyst.js        # Catalyst alerts + stock picks + auto-refresh
│       │   ├── tab-home.js            # Home dashboard + sub-tabs
│       │   ├── tab-stocks.js          # Stocks wrapper (analysis + bursa)
│       │   └── tab-settings.js        # Settings wrapper (model info)
│       └── css/dashboard.css
├── src/
│   ├── data_sources/
│   │   ├── stock_prices.py             # yfinance + 15 indicators
│   │   ├── news_sentiment.py           # Finnhub + Google News RSS + FinBERT
│   │   ├── news_my.py                  # Malaysia news (RSS)
│   │   ├── geopolitical.py             # GDELT (stored data first)
│   │   ├── social_media.py             # Reddit + figure boost
│   │   ├── earnings.py                 # EPS surprise, beat rate, upcoming dates
│   │   ├── insider.py                  # Insider trading (Finnhub SEC filings)
│   │   ├── analyst.py                  # Analyst consensus (Finnhub recommendations)
│   │   ├── yahoo_news.py              # Yahoo Finance News API (free)
│   │   ├── market_news_rss.py         # Benzinga, MarketWatch, CNBC, FMT, Malay Mail RSS
│   │   ├── bursa_news.py              # i3investor + KLSE Screener
│   │   ├── youtube_sentiment.py       # YouTube Data API (optional)
│   │   └── order_book.py              # IB Gateway L2 / yfinance L1
│   ├── analysis/
│   │   ├── predictor.py                # 7-signal combiner, fast/full modes
│   │   ├── catalyst.py                 # News catalyst detector + stock ranker + knowledge graph
│   │   ├── entity_extractor.py         # Stock mention detection (219 aliases)
│   │   ├── llm_analyzer.py             # Ollama Phi-3 Mini wrapper
│   │   ├── industry_classifier.py      # Keyword + AI classification + DB cache
│   │   └── market_indicators.py        # Fear & Greed index
│   ├── data/
│   │   ├── collect_historical.py       # 2yr backfill + macro (yields, DXY, commodities)
│   │   ├── collect_gdelt_history.py    # 2yr GDELT backfill
│   │   ├── collect_earnings.py         # Historical EPS from Finnhub
│   │   ├── collect_insider.py          # Insider transactions from Finnhub
│   │   ├── collect_analyst.py          # Analyst recommendations from Finnhub
│   │   ├── collect_news_history.py     # Historical news sentiment backfill
│   │   ├── daily_collector.py          # Daily sentiment collector
│   │   ├── batch_predict.py            # Batch predictions
│   │   ├── train_model.py              # ML training (~107 features)
│   │   ├── optimize_weights.py         # Weight optimization
│   │   └── export_training.py          # CSV export
│   └── database.py                     # SQLite (13 tables)
├── config/
│   ├── settings.py                     # API keys, weights, industries
│   ├── stock_universe.py              # S&P 500 + Bursa stock list
│   └── industries.py                  # Canonical industry names (single source)
├── catalyst_scanner.py                 # News catalyst scanner (every 30 min)
├── config/stock_knowledge.py           # Bursa stock relationship graph
├── tests/                              # 271 tests, 21 files
├── models/                             # Trained ML models + weights
├── .github/workflows/ci.yml           # GitHub Actions CI
├── setup_daily_collector.bat           # Schedule background workers
├── CLAUDE.md                           # Project context for Claude Code
└── README.md
```

## Testing

**271 tests** across 21 files — all run offline with mocked APIs (~20s):

```bash
python -m pytest tests/ -v
```

CI runs automatically via GitHub Actions on push to `main`, `master`, and `claude/*` branches.

## API Keys (Optional)

| Key | Source | Required? |
|-----|--------|-----------|
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | Optional (US news + earnings) |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) | Optional (social) |
| `REDDIT_CLIENT_SECRET` | Same | Optional |
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Optional (MY news) |

The dashboard works without any API keys using yfinance (free) + ML model predictions.

## Tech Stack

- **Backend:** Python 3.11, Flask, SQLite
- **Frontend:** Vanilla JS (8 modules), Chart.js 4, CSS custom properties
- **ML:** XGBoost, LightGBM, scikit-learn, scipy
- **NLP:** FinBERT (ProsusAI/finbert), BART zero-shot (facebook/bart-large-mnli)
- **Data:** yfinance, Finnhub, GDELT, Reddit PRAW, Google News RSS
- **Order Book:** IB Gateway (ib_insync) with yfinance fallback
- **Testing:** pytest (217 tests), GitHub Actions CI

## Disclaimer

For educational and research purposes only. Not investment advice. Past predictions do not guarantee future results.
