# StockSight — Project Context for Claude

This file gives Claude full context so sessions on any device start with a complete picture.

**Important:** Keep this file updated at the end of every Claude Code session before committing.

---

## Last Updated

**2026-04-08** — Session: Major data enhancement for ML model. Added 22+ new features (lagged indicators, treasury yields, DXY, sector ETF returns, cross-asset prices, Fear & Greed proxy, cross-asset correlations, insider buy ratio, analyst score). New data sources: insider trading (Finnhub), analyst consensus (Finnhub), historical news sentiment backfill (Finnhub + FinBERT). GDELT tone now backfilled per-stock via industry mapping. New collectors: collect_insider.py, collect_analyst.py, collect_news_history.py. New DB tables: insider_history, analyst_history. 8 new training_data columns for macro features. Predictor updated to compute all new features at inference time. 228 tests pass.

---

## What This Project Does

Multi-signal stock prediction dashboard that:
1. Gathers signals from technical analysis (15+ indicators), news sentiment (FinBERT), social media (Reddit), geopolitical events (GDELT), influential figure monitoring, **earnings surprises** (Finnhub), **insider trading**, and **analyst consensus**
2. Combines them with **AI-optimized weights** (via scipy differential evolution)
3. Runs **XGBoost + LightGBM ensemble** ML model as a 7th signal (~107 features)
4. **Catalyst Alerts**: scans news every 30 min, detects market-moving events, predicts next rising/falling stocks
5. Serves a Flask web dashboard with 8 tabs: Analysis, Sectors, News, Trends, Report, Model, Bursa, Catalyst
6. Supports US (S&P 500) + Bursa Malaysia markets
7. Pre-computes predictions via batch jobs, serves from cache (~150ms)

---

## Architecture Overview

```
Flask web app (web/app.py)
    ├── 8 JS modules (app.js, main.js, tab-*.js)
    ├── Pre-computed predictions served from SQLite cache
    └── Background workers (scheduled):
            ├── price_tracker.py      (every 5 min)
            ├── news_tracker.py       (every 30 min)
            ├── daily_collector.py    (daily 6 PM)
            └── batch_predict.py      (daily 6:30 PM)

config/
    ├── settings.py            ← API keys, weights, BURSA_INDUSTRIES
    ├── stock_universe.py      ← S&P 500 + Bursa + indices (589 stocks)
    └── industries.py          ← CANONICAL single source of truth for industry names,
                                  icons, GDELT keywords, migration map

src/data_sources/
    ├── stock_prices.py     ← yfinance + 15 technical indicators
    ├── news_sentiment.py   ← Finnhub + Google News RSS + FinBERT NLP
    ├── news_my.py          ← Malaysia-specific news (Google/Edge/NewsAPI RSS)
    ├── geopolitical.py     ← GDELT stored data (no live API for speed)
    ├── social_media.py     ← Reddit PRAW + figure mention boost
    ├── earnings.py         ← Finnhub EPS surprise, beat rate, upcoming dates
    ├── insider.py          ← Finnhub insider transactions (buy/sell ratio)
    ├── analyst.py          ← Finnhub analyst consensus (recommendation trends)
    └── order_book.py       ← IB Gateway (L2) + yfinance fallback (L1)

src/analysis/
    ├── predictor.py        ← signal combiner (7 signals), fast/full modes, cache-first
    ├── catalyst.py         ← news catalyst detector + stock impact ranker (11 event types)
    ├── industry_classifier.py ← keyword + AI zero-shot + DB classification cache
    └── market_indicators.py   ← Fear & Greed index

src/data/
    ├── collect_historical.py  ← 2yr backfill (589 stocks + macro: yields, DXY, commodities, sector ETFs)
    ├── collect_gdelt_history.py ← 2yr GDELT tone per industry
    ├── collect_earnings.py    ← historical EPS/revenue data from Finnhub
    ├── collect_insider.py     ← insider transaction history from Finnhub
    ├── collect_analyst.py     ← analyst recommendation history from Finnhub
    ├── collect_news_history.py ← historical news sentiment backfill (Finnhub + FinBERT)
    ├── daily_collector.py     ← daily sentiment + macro features
    ├── batch_predict.py       ← batch predictions for all stocks
    ├── train_model.py         ← XGBoost + LightGBM training (~104 features)
    ├── optimize_weights.py    ← AI signal weight optimization
    └── export_training.py     ← CSV export for ML training

models/
    ├── direction_xgb.json     ← XGBoost direction classifier (54.7% accuracy)
    ├── direction_lgbm.txt     ← LightGBM direction classifier
    ├── magnitude_xgb.json     ← XGBoost magnitude regressor
    ├── optimized_weights.json ← AI-optimized signal weights
    ├── feature_importance.csv
    └── metrics.json

tests/
    ├── conftest.py            ← 10 fixtures (tmp DB, mocked APIs)
    ├── test_database.py       ← 46 tests (predictions, news, watchlist, GDELT, training)
    ├── test_predictor.py      ← 15 tests (combine_signals, predict, weights)
    ├── test_web_api.py        ← 45 tests (all API endpoints)
    ├── test_stock_prices.py   ← 6 tests
    ├── test_alerts.py         ← 7 tests
    ├── test_portfolio.py      ← 9 tests
    ├── test_market_indicators.py ← 5 tests
    ├── test_sector_analysis.py   ← 8 tests
    ├── test_news_sentiment.py    ← 11 tests
    ├── test_social_media.py      ← 6 tests
    ├── test_geopolitical.py      ← 5 tests
    ├── test_industry_classifier.py ← 17 tests
    ├── test_order_book.py        ← 4 tests
    ├── test_stock_universe.py    ← 11 tests
    ├── test_earnings.py          ← 12 tests
    ├── test_insider.py           ← 5 tests (insider transactions + signal)
    ├── test_analyst.py           ← 6 tests (analyst consensus + signal)
    ├── test_catalyst.py          ← 15 tests (event detection, ranking, DB, API)
    └── test_industry_alignment.py ← 6 tests (guard against name drift)
```

---

## Frontend Architecture (Modular JS)

```
web/static/js/
    ├── app.js           ← Core: App namespace, state, API wrapper, chart factory,
    │                       toast, cache (TTL), network banner, skeleton helpers
    ├── main.js          ← Tab router, event delegation, keyboard shortcuts, init
    ├── tab-analysis.js  ← Analysis tab: prediction, 15 indicator charts, overlays,
    │                       fundamentals, earnings report, market movers, progress steps,
    │                       weight distribution doughnut chart
    ├── tab-sectors.js   ← Sector heatmap with progress bar
    ├── tab-news.js      ← News hub: industry cards, sentiment pies, AI classification
    ├── tab-trends.js    ← Prediction history, trend charts, sector trends
    ├── tab-report.js    ← Daily report: all stocks ranked, filters, batch trigger
    ├── tab-model.js     ← Model info: accuracy metrics, feature importance chart,
    │                       signal weights, feature categories table, training data stats
    ├── tab-bursa.js     ← Bursa market: industry cards, detail panel, order book,
    │                       stock modal, watchlist, prediction badges,
    │                       auto-refresh toggle, progress steps
    └── tab-catalyst.js  ← Catalyst alerts: event detection, stock picks table,
                            scan trigger, history, 30-min auto-refresh
```

**Key patterns:**
- All inline `onclick` removed → `data-action` + event delegation in `main.js`
- XSS-safe: `App.esc()` + `textContent` instead of `innerHTML` with API data
- Chart factory: `App.chart.create/line/bar/doughnut/priceLine` with auto-injected dark tooltips
- All charts use `maintainAspectRatio: false` + `.chart-wrap` fixed-height containers
- Data caching: `App.cacheSet/cacheGet` with 5-min TTL
- ARIA accessibility: `role="tab/tablist/tabpanel"`, `aria-selected`, `aria-live`
- Mobile responsive: breakpoints at 480px, 768px, 900px, 1100px

---

## Prediction Pipeline

```
User clicks "Analyze AAPL"
    ↓
1. Check SQLite cache (< 30 min old?) → serve in ~150ms
2. Cache miss → compute live:
   a. Always fast prediction first (Technical + ML + Earnings) → ~3-5s
   b. Full mode: then fetches News + Social + Geo + Figures separately
      with live progress steps in the UI
3. Save result to predictions table for next request
```

**Signal weights (7 signals):**
```
US:  Technical 22%, News 18%, ML 18%, Social 12%, Earnings 12%, Momentum 10%, Geo 8%
MY:  Technical 28%, ML 20%, Momentum 15%, Geo 12%, News 10%, Social 10%, Earnings 5%
```
- Loaded from `models/optimized_weights.json` if fresh (< 7 days)
- Falls back to `config/settings.py` defaults
- Dashboard shows weight distribution doughnut chart + "AI-Optimized" or "Default" badge

---

## Industry Categories (Canonical)

**Single source of truth:** `config/industries.py`

15 stock industries + 4 meta-categories for news/GDELT classification.
All modules import from here. Guard test `test_industry_alignment.py` prevents drift.

**Naming was aligned across 5 lists in this session:**
- BURSA_INDUSTRIES (settings.py) — 8 industries
- INDUSTRY_KEYWORDS (industry_classifier.py) — 14 industries
- MY_SECTORS (sector_analysis.py) — 9 industries
- GDELT_KEYWORDS (industries.py) — 14 industries
- INDUSTRY_GDELT_KEYWORDS (stock_universe.py) — re-exports from industries.py

---

## Technical Indicators (15+)

Calculated in `stock_prices.py → get_historical_prices()`:
- Moving Averages: SMA 20/50, EMA 9/12/21/26
- MACD + Signal Line + Histogram
- RSI (14), Stochastic %K/%D, Williams %R, CCI
- Bollinger Bands (upper/lower)
- ADX + DMI (+DI/-DI)
- ATR, OBV, VWAP
- Parabolic SAR, Ichimoku Cloud (Tenkan/Kijun/SpanA/SpanB)
- Fibonacci Retracement levels

**Overlay toggles** on price chart: EMA 9/21, VWAP, SAR, Fibonacci, Ichimoku

---

## ML Model

- **Training data:** 291,581 rows, 587 stocks, 2 years (needs re-collection with new features)
- **Features:** ~104 columns after enhancement (was 82, 8 were dead zeros)
  - 36 base OHLCV + indicators
  - 8 market context (SPY, VIX, treasury 10Y/2Y, yield spread, DXY, sector ETF return)
  - 8 sentiment (news, reddit, figure, GDELT tone, fear & greed) — **now backfilled via GDELT industry mapping**
  - 4 earnings (surprise, days_since, beat_rate, momentum)
  - 2 alternative data (insider_buy_ratio, analyst_score) — **NEW**
  - 3 cross-asset (oil_close, gold_close, copper_close) — **NEW**
  - ~45 engineered (calendar, momentum, 52-week, streaks, regime, lags, correlations, fear_greed_proxy)
- **New features (v3):**
  - Lagged indicators: rsi/macd/volume/daily_return at 1d/5d/20d lags (12 features)
  - Macro: treasury_10y, treasury_2y, yield_spread, dxy_close (4 features)
  - Sector: sector_etf_return (1 feature)
  - Cross-asset: oil_close, gold_close, copper_close + corr_oil_20d, corr_gold_20d (5 features)
  - Alternative: insider_buy_ratio, analyst_score (2 features)
  - Derived: fear_greed_proxy (replaces broken fear_greed) (1 feature)
- **Earnings features:** `earnings_surprise`, `days_since_earnings`, `beat_rate_4q`, `earnings_momentum`
- **Models:** XGBoost + LightGBM ensemble (needs retraining after data re-collection)
- **Target:** 5-day price direction (UP >1%, DOWN <-1%, FLAT)

**Retraining steps (in order):**
```bash
python src/data/collect_historical.py        # re-collect with new macro columns
python src/data/collect_insider.py           # insider transactions (~10 min)
python src/data/collect_analyst.py           # analyst recommendations (~10 min)
python src/data/collect_news_history.py      # news sentiment backfill (hours)
python src/data/train_model.py              # retrain with all new features
python src/data/optimize_weights.py         # re-optimize signal weights
```

---

## Database Tables (SQLite)

| Table | Purpose |
|-------|---------|
| `predictions` | Per-stock predictions (action, confidence, signals_json, reasons_json) |
| `news` | News articles with FinBERT sentiment (deduped by headline+platform) |
| `price_snapshots` | Intraday price snapshots from price_tracker |
| `sector_snapshots` | Sector analysis history |
| `training_data` | 2yr historical OHLCV + 40 indicators for ML training |
| `daily_features` | Daily sentiment/macro features per stock |
| `gdelt_history` | 2yr daily GDELT tone per industry (14 industries) |
| `earnings_history` | Quarterly EPS actual/estimate/surprise per stock (2,010 records) |
| `insider_history` | Insider buy/sell transactions per stock (from Finnhub SEC filings) |
| `analyst_history` | Monthly analyst consensus (strongBuy/buy/hold/sell/strongSell) |
| `classification_cache` | Cached headline → industry mappings (14,000x speedup) |
| `catalyst_alerts` | Detected catalyst events with stock picks per scan |
| `catalyst_outcomes` | 24h outcome tracking for catalyst predictions |
| `watchlist` | User's personal watchlist (symbol, note, price alerts) |
| `news_tracker_state` | Last fetch time per news source |

---

## Flask API Endpoints

| Endpoint | Purpose | Speed |
|----------|---------|-------|
| `GET /api/predict/<sym>` | Prediction (cache-first, then live) | ~150ms cached, ~5s live |
| `GET /api/predict/<sym>?mode=full` | Full analysis with all signals | ~15s |
| `GET /api/history/<sym>` | OHLCV + all indicators for charts | ~2s |
| `GET /api/fundamentals/<sym>` | P/E, P/B, EPS, ROE, etc. | ~1s |
| `GET /api/predictions/latest` | Latest prediction per symbol | instant |
| `POST /api/batch-predict` | Trigger batch prediction (background) | instant |
| `GET /api/market-movers?symbol=X` | Influential figure activity | ~5s |
| `GET /api/signal/news/<sym>` | News sentiment signal only | ~5-15s |
| `GET /api/signal/social/<sym>` | Reddit sentiment signal only | ~3-5s |
| `GET /api/signal/geopolitical` | Geopolitical signal (stored data) | ~0.3s |
| `GET /api/signal/earnings/<sym>` | Earnings signal (EPS surprise, beat rate) | ~1s |
| `GET /api/earnings/history/<sym>` | Stored quarterly earnings history | instant |
| `GET /api/weights` | Current active signal weights | instant |
| `GET /api/watchlist` | User's watchlist with live quotes | ~3s |
| `POST /api/watchlist` | Add stock to watchlist | instant |
| `DELETE /api/watchlist/<sym>` | Remove from watchlist | instant |
| `PUT /api/watchlist/<sym>` | Update note/alerts | instant |
| `GET /api/bursa/industries` | 8 industries with live quotes | ~10s |
| `GET /api/orderbook/<sym>` | Order book (IB L2 or yfinance L1) | ~1s |
| `GET /api/news/industry-analysis` | AI-classified news by industry | ~0.01s (cached) |
| `GET /api/catalyst/alerts` | Current catalyst alerts + stock picks | instant |
| `POST /api/catalyst/scan` | Trigger manual catalyst scan | ~15s |
| `GET /api/catalyst/history` | Past catalyst alerts with outcomes | instant |

---

## Scheduled Background Workers

| Script | Schedule | What It Does |
|--------|----------|-------------|
| `price_tracker.py` | Every 5 min (market hours) | Price snapshots for tracked stocks |
| `news_tracker.py` | Every 30 min | News articles from Finnhub + RSS + NewsAPI |
| `catalyst_scanner.py` | Every 30 min | Scans news for catalysts, predicts next rising/falling stocks |
| `daily_collector.py` | Daily 6:00 PM | Sentiment features + GDELT daily update |
| `batch_predict.py` | Daily 6:30 PM | Pre-compute predictions for all Bursa stocks |

**Windows Task Scheduler names:**
| Task Name | Status |
|-----------|--------|
| `StockPred-PriceTracker` | Registered |
| `StockPred-NewsTracker` | Registered |
| `StockPred-CatalystScan` | Registered (every 30 min) |
| `StockPred-DailyCollector` | Not yet registered (run `setup_daily_collector.bat`) |
| `StockPred-BatchPredict` | Not yet registered (run `setup_daily_collector.bat`) |

Setup: Run `setup_daily_collector.bat` once to register all Windows Task Scheduler jobs.

---

## Data Collection Pipeline

| Script | Purpose | Data Size |
|--------|---------|----------|
| `collect_historical.py` | 2yr OHLCV + indicators + macro (yields, DXY, commodities, sector ETFs) | 291K rows |
| `collect_gdelt_history.py` | 2yr daily GDELT tone for 14 industries | 14.5K records |
| `collect_earnings.py` | Historical EPS data for 506 US stocks | 2,010 records |
| `collect_insider.py` | Insider transactions from Finnhub (US stocks) | ~10 min |
| `collect_analyst.py` | Analyst recommendations from Finnhub (US stocks) | ~10 min |
| `collect_news_history.py` | Historical news + FinBERT sentiment backfill | hours |
| `daily_collector.py` | Daily sentiment/macro features | grows daily |
| `export_training.py` | Export SQLite → CSV for ML training | ~16MB combined |

Stock universe: `config/stock_universe.py` — 81 Bursa + 503 S&P 500 + 5 indices = 589 stocks.

---

## Key Features

- **Catalyst Alerts:** Every 30 min, scans news for 11 catalyst types (supply chain, tariff, rate decision, commodity, regulation, earnings, tech, geopolitical, pandemic, disaster, M&A), maps to affected industries, ranks stocks by predicted 24h impact with momentum + volume + exposure scoring
- **My Watchlist:** Star stocks from Bursa tab, add notes, set price alerts, one-click analyze
- **Daily Report tab:** All stocks ranked by prediction score, filterable by action/industry/confidence
- **Prediction badges:** BUY/SELL/HOLD badges on each Bursa stock row
- **Market Movers:** Influential figure (Musk, Trump, Buffett, etc.) activity per stock
- **AI News Classification:** Hybrid keyword + zero-shot with persistent DB cache (14,000x speedup on repeat loads)
- **Earnings Reports:** Quarterly EPS actual vs estimate table, surprise %, beat rate, upcoming dates
- **Weight Distribution:** Doughnut chart showing signal weight allocation
- **15 indicator charts** with 5 overlay toggles on price chart
- **Fundamentals card:** P/E, P/B, EPS, ROE, D/E, FCF, etc.
- **Skeleton loading** + progress steps for analysis and Bursa tab
- **Auto-refresh toggle** on Bursa tab (30s interval when market open)
- **Model Info tab:** Transparency dashboard — 82 features listed by category, accuracy metrics, feature importance chart, signal weights with optimization stats, training data stats
- **Network error banner** with retry button
- **Mobile responsive** (480px, 768px, 900px breakpoints)

---

## Common Operations

```bash
# Start the dashboard
python web/app.py

# Run batch predictions (all Bursa stocks)
python src/data/batch_predict.py
python src/data/batch_predict.py --quick   # fast mode (technical + ML only)

# Collect historical data
python src/data/collect_historical.py              # all 589 stocks
python src/data/collect_historical.py --my-only    # Bursa only
python src/data/collect_historical.py AAPL TSLA    # specific stocks

# Collect earnings history
python src/data/collect_earnings.py                # all US stocks (~10 min)
python src/data/collect_earnings.py --symbol AAPL  # specific stock

# Collect insider trading history
python src/data/collect_insider.py                 # all US stocks (~10 min)
python src/data/collect_insider.py --symbol AAPL   # specific stock

# Collect analyst recommendations
python src/data/collect_analyst.py                 # all US stocks (~10 min)
python src/data/collect_analyst.py --symbol AAPL   # specific stock

# Backfill news sentiment history
python src/data/collect_news_history.py              # core stocks, 12 months
python src/data/collect_news_history.py --months 6   # 6 months only
python src/data/collect_news_history.py --symbol AAPL --skip-finbert  # fast (no NLP)

# Train/retrain ML model
python src/data/train_model.py
python src/data/optimize_weights.py

# Export training data to CSV
python src/data/export_training.py

# Daily collection (normally scheduled)
python src/data/daily_collector.py
python src/data/daily_collector.py --full   # full universe (589 stocks)

# GDELT backfill
python src/data/collect_gdelt_history.py --months 24

# Run catalyst scanner (detect news events, predict stocks)
python catalyst_scanner.py              # single scan
python catalyst_scanner.py --loop       # every 30 min
python catalyst_scanner.py --hours 12   # scan last 12h of news

# Run tests
python -m pytest tests/ -v
```

---

## Testing

**243 tests** across 20 test files. All run offline with mocked APIs (~8s).

```bash
python -m pytest tests/ -v --tb=short
```

CI: GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main`, `master`, `claude/*` branches.

---

## Known Gotchas

- **UTC vs local time:** DB stores UTC via `datetime('now')`. Compare with UTC, not local time.
- **FinBERT first load:** ~30s to load model. Pre-loaded at Flask startup via background thread.
- **GDELT rate limits:** Free API throttles aggressively. Use stored data (`gdelt_history` table) instead of live calls.
- **NaN in JSON:** `_sanitize_for_json()` handles numpy NaN/Inf in prediction responses.
- **yfinance called 3x per prediction:** technical + ML + history. Could optimize by caching.
- **Bursa tickers are numeric:** "1155" must become "1155.KL" — auto-resolved in analysis tab.
- **S&P 500 list cached locally:** `data/sp500_tickers.csv`, refreshed weekly from GitHub.
- **Earnings data US-only:** Finnhub doesn't cover Bursa Malaysia. MY stocks get neutral fallback.
- **News classification first load:** Zero-shot model downloads on first use (~30s). After that, DB cache makes it instant.
- **Chart height on mobile:** All charts use `maintainAspectRatio: false` + `.chart-wrap` containers for consistent height.
- **Full mode analysis:** Frontend always sends fast prediction first, then fetches slow signals separately with progress steps. Never sends `mode=full` to backend (was causing hangs).
- **Insider/Analyst data US-only:** Finnhub SEC filings and analyst data only cover US stocks. MY stocks get neutral fallback.
- **DXY ticker flaky:** `DX-Y.NYB` sometimes returns empty on yfinance. Falls back to `UUP` ETF as proxy.
- **News backfill is slow:** `collect_news_history.py` takes hours for all stocks (Finnhub rate limit + FinBERT inference). Use `--skip-finbert` for fast mode.
- **Must re-collect historical data:** After adding new macro columns, run `collect_historical.py` to populate treasury_10y, dxy_close, oil/gold/copper, sector_etf_return columns. Existing rows will have NULLs for new columns until re-collected.

---

## Repository

GitHub: `https://github.com/henrychong123/stock-prediction`
Branch: `master`
`.gitignore` includes: `venv/`, `.env`, `__pycache__/`, `*.pyc`, `stock_data.db`, `data/training/`, `models/`
