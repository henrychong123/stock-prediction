# StockSight — Project Context for Claude

This file gives Claude full context so sessions on any device start with a complete picture.

**Important:** Keep this file updated at the end of every Claude Code session before committing.

---

## Last Updated

**2026-05-03** — Session: Added ngrok tunneling for ad-hoc remote access to the dashboard. Four new files at repo root: `ngrok.yml` (tunnel config with reserved domain `succedaneous-nonmuscularly-jeannetta.ngrok-free.dev`, gitignored), `start-tunnel.bat` (manual launcher), `run_tunnel_hidden.vbs` (silent wrapper), `setup_ngrok_task.bat` (registers `StockPred-NgrokTunnel` ONLOGON task — optional, not run yet). `.gitignore` updated with `ngrok.yml` and `logs/`. Flask + ngrok are NOT registered as scheduled tasks — they run manually on demand (the user's choice; the 35 background data tasks already keep the DB fresh independently). To bring the dashboard up: `python web/app.py` then `start-tunnel.bat`. `.env` already had `TRUST_PROXY=1` set so ProxyFix builds the OAuth redirect URI as https. Google OAuth client must list `https://succedaneous-nonmuscularly-jeannetta.ngrok-free.dev/login/google/authorized` as an authorized redirect URI (already done — login verified working). Also fixed a small doc drift below: the actual SQLite DB is `data/predictions.db` (1.26 GB), not `stock_data.db`.

**2026-04-17** — Session: Four major additions.
1. **Self-learning loop for AI Analyst**: new `run_failure_analysis.py` (per-pick Claude post-mortem) writes structured `failure_analysis` JSON to `analyst_outcomes` and boosts sample weights in `data/analyst_sample_weights.json`. New `run_batch_reflection.py` (weekly) digests failures into structured `analyst_signal_rules.json` that `prepare_briefing.py` injects as constraints. `train_model.py` applies the sample weights to XGBoost + LightGBM fits. Scorecard UI now has expandable rows showing original reasoning + bull/bear/risks + "Why wrong?" analysis.
2. **Paper Trading engine** (new `src/paper_trading/` module): 5 virtual strategies (relaxed, baseline, top3, high_conviction, bull_and_bear) each with RM50,000 starting capital, Bursa/US fee models (IB commission + SST + stamp duty), position sizing rules, stop-loss/take-profit monitoring. New DB tables: `virtual_strategies`, `virtual_portfolios`, `virtual_positions`, `virtual_trades`, `virtual_equity_snapshots`. New Flask endpoint `/api/paper/dashboard` (single combined endpoint). New "Paper Trading" dashboard tab with equity curve chart + strategy cards + positions/trades tables. Scheduler entries: `StockPred-PaperTrade-Morning/Midday/Evening` + `StockPred-PaperMonitor` (every 30 min).
3. **Bursa universe expansion** from 80 curated to ~400 discovered stocks: new `src/data/discover_bursa_stocks.py` scans 0001-9999.KL weekly, writes `data/bursa_all_stocks.json` with liquidity flags. Curated `BURSA_INDUSTRIES` kept unchanged for dashboard. `MY_STOCK_NAMES`, entity extractor, and ML training all auto-extend from JSON. Liquid-only filter (RM500M+ cap OR 100K+ volume) applied to ML training, batch predictions, short-term reasoner, paper trading. `/api/bursa/all-stocks` endpoint.
4. **Scheduled Tasks visibility panel** (Settings tab): `/api/scheduled-tasks` endpoint queries Windows Task Scheduler via `schtasks /query`, groups `StockPred-*` tasks by category. New `tab-tasks.js`. Analyst pick generation moved from Claude Code cron (session-only, 7-day expiry) to Windows Task Scheduler (permanent): `StockPred-AnalystPicks-Morning/Midday/Evening`. Plus `StockPred-FailureAnalysis` (daily 19:00), `StockPred-BatchReflection` (weekly Sun 20:00), `StockPred-DiscoverBursa` (weekly Sun 01:00).

**2026-04-12** — Session: Added short-term (24h–7d) news-driven Bursa subsystem under `src/shortterm/`. New pipeline: filter → full-body Playwright scrape (`news_fulltext` table) → full-text entity extraction → Claude Code CLI reasoner (with `AGENT.md`/`SKILL.md`/`MEMORY.md` injected into prompt) → per-horizon picks (`shortterm_picks`) → 24h/3d/7d outcome evaluation → auto-rewritten `MEMORY.md`. Siloed from long-term ML (import + SQL whitelists enforced by `test_silo`). Cleanup: removed the dead `article-scraper` Claude Code scheduled task (function existed but was never invoked; new `StockPred-ShorttermScrape` replaces it). New scheduler entries: `StockPred-ShorttermScrape`, `StockPred-ShorttermReason-Morning/Midday/Close/Eve`, `StockPred-ShorttermEval`. New Flask routes under `/api/shortterm/*` + "Short-term" tab in dashboard.

**2026-04-11** — Session: Multi-agent architecture with Claude as the reasoning brain (originally wired as Claude Code scheduled tasks, later migrated to Windows Task Scheduler — see the 2026-04-17 entry). Claude replaces Ollama as primary analyst (Ollama still available as fallback via `src/analysis/llm_analyzer.py`). New helper scripts: `prepare_briefing.py` (formats DB data → JSON for Claude), `save_analyst_report.py` (writes Claude output → DB), `prepare_evaluation.py` + `save_evaluation.py` (evaluation pipeline). Self-learning via `analyst_reflections.json` — Claude reads past mistakes to improve.

---

## What This Project Does

Multi-signal stock prediction dashboard that:
1. Gathers signals from technical analysis (15+ indicators), news sentiment (FinBERT), social media (Reddit), geopolitical events (GDELT), influential figure monitoring, **earnings surprises** (Finnhub), **insider trading**, and **analyst consensus**
2. Combines them with **AI-optimized weights** (via scipy differential evolution)
3. Runs **XGBoost + LightGBM ensemble** ML model as a 7th signal (~107 features)
4. **Catalyst Alerts**: scans news every 30 min, detects market-moving events, predicts next rising/falling stocks with knowledge graph cascade
5. **AI Analyst** (Claude Code): self-learning multi-agent system — Claude reads news briefings, reasons about stocks, generates top 10 picks 3x daily, self-evaluates accuracy with per-pick failure analysis + weekly batch reflection → structured signal rules injected into next briefing + sample weight boost in ML retrain
6. **Paper Trading engine**: 5 virtual strategies trade analyst picks with realistic Bursa fees (commission + SST + stamp duty); tracks equity curves, win rate, realized P&L
7. Serves a Flask web dashboard with 8 tabs: Home, Stocks, Catalyst, Short-term, AI Analyst, Paper Trading, News, Settings
8. Supports US (S&P 500) + Bursa Malaysia markets (~400 Bursa stocks discovered, 325 flagged liquid)
9. Pre-computes predictions via batch jobs, serves from cache (~150ms)

---

## Architecture Overview

```
Flask web app (web/app.py)
    ├── 12 JS modules (app.js, main.js, tab-*.js)
    ├── 6 tabs: Home, Stocks, AI Analyst, Catalyst, News, Settings
    ├── Pre-computed predictions served from SQLite cache
    └── Background workers (scheduled):
            ├── price_tracker.py      (every 5 min)
            ├── news_tracker.py       (every 30 min)
            ├── catalyst_scanner.py   (every 30 min)
            ├── social_collector.py   (every 2 hours)
            ├── daily_collector.py    (daily 6 PM)
            └── batch_predict.py      (daily 6:30 PM)

config/
    ├── settings.py            ← API keys, weights, BURSA_INDUSTRIES
    ├── stock_universe.py      ← S&P 500 + Bursa + indices (589 stocks)
    ├── industries.py          ← CANONICAL single source of truth for industry names
    └── stock_knowledge.py     ← Bursa stock relationship graph (researched)

src/data_sources/
    ├── stock_prices.py     ← yfinance + 15 technical indicators
    ├── news_sentiment.py   ← Finnhub + Google News RSS + FinBERT NLP
    ├── news_my.py          ← Malaysia-specific news (Google/Edge/NewsAPI RSS)
    ├── geopolitical.py     ← GDELT stored data (no live API for speed)
    ├── social_media.py     ← Reddit PRAW + figure mention boost
    ├── earnings.py         ← Finnhub EPS surprise, beat rate, upcoming dates
    ├── insider.py          ← Finnhub insider transactions (buy/sell ratio)
    ├── analyst.py          ← Finnhub analyst consensus (recommendation trends)
    ├── yahoo_news.py       ← Yahoo Finance News API (stock-specific, free)
    ├── market_news_rss.py  ← Benzinga, MarketWatch, CNBC, FMT, Malay Mail RSS
    ├── bursa_news.py       ← i3investor + KLSE Screener (Bursa-specific)
    ├── youtube_sentiment.py ← YouTube Data API (optional, needs key)
    └── order_book.py       ← IB Gateway (L2) + yfinance fallback (L1)

src/analysis/
    ├── predictor.py        ← signal combiner (7 signals), fast/full modes, cache-first
    ├── ai_analyst.py       ← self-learning AI analyst (LLM reasoning + scoring + self-evaluation)
    ├── catalyst.py         ← news catalyst detector + stock impact ranker (11 event types) + knowledge graph cascade
    ├── entity_extractor.py ← stock mention detection (583 tickers, 694 names, 219 aliases)
    ├── llm_analyzer.py     ← Ollama Phi-3 Mini wrapper for headline analysis
    ├── industry_classifier.py ← keyword + AI zero-shot + DB classification cache
    └── market_indicators.py   ← Fear & Greed index

src/data/
    ├── collect_historical.py  ← 2yr backfill (589 stocks + macro: yields, DXY, commodities, sector ETFs)
    ├── collect_gdelt_history.py ← 2yr GDELT tone per industry
    ├── collect_earnings.py    ← historical EPS/revenue data from Finnhub
    ├── collect_insider.py     ← insider transaction history from Finnhub
    ├── collect_analyst.py     ← analyst recommendation history from Finnhub
    ├── collect_news_history.py ← historical US news sentiment backfill (Finnhub + FinBERT)
    ├── collect_bursa_news_history.py ← 24-month Bursa news backfill (Google News + FinBERT)
    ├── social_collector.py    ← multi-source news aggregator (13 platforms, every 2h)
    ├── build_stock_knowledge.py ← Ollama-based stock relationship builder
    ├── train_catalyst_model.py ← 24h news reaction model training
    ├── daily_analysis.py      ← AI analyst scheduled runner (legacy Ollama, replaced by Claude task)
    ├── prepare_briefing.py    ← formats DB data → JSON briefing for Claude analyst task
    ├── save_analyst_report.py ← writes Claude analyst output → analyst_reports DB table
    ├── prepare_evaluation.py  ← loads unevaluated picks + prices → JSON for Claude eval task
    ├── save_evaluation.py     ← writes evaluation results → analyst_outcomes + reflections
    ├── daily_collector.py     ← daily sentiment + macro features
    ├── batch_predict.py       ← batch predictions for all stocks
    ├── train_model.py         ← XGBoost + LightGBM training (~104 features, sample weight boost from analyst outcomes)
    ├── optimize_weights.py    ← AI signal weight optimization
    ├── export_training.py     ← CSV export for ML training
    ├── discover_bursa_stocks.py ← weekly scan of 0001-9999.KL → bursa_all_stocks.json
    ├── run_evaluation.py      ← rule-based eval (no LLM); 3x daily at 09:20/13:20/18:20
    ├── run_failure_analysis.py ← per-pick Claude post-mortem; writes analyst_outcomes.failure_analysis
    └── run_batch_reflection.py ← weekly pattern extraction → data/analyst_signal_rules.json

src/paper_trading/
    ├── costs.py               ← Bursa + US fee models (IB commission + SST + stamp duty)
    ├── broker.py              ← VirtualBroker: buy, sell, mark_to_market, check_stops
    ├── strategies.py          ← 5 Strategy dataclasses with entry rules + sizing
    ├── runner.py              ← Trades analyst picks into virtual portfolios
    └── monitor.py             ← Every 30min: stop/TP/time-stop + MTM + equity snapshot

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
    ├── test_entity_extractor.py  ← 16 tests (stock mention detection, aliases)
    ├── test_social_crawlers.py   ← 12 tests (Yahoo News, RSS, YouTube, LLM, collector)
    ├── test_ai_analyst.py        ← 27 tests (analysis engine, scoring, DB, API, knowledge graph)
    └── test_industry_alignment.py ← 6 tests (guard against name drift)
```

---

## Frontend Architecture (Modular JS)

```
web/static/js/
    ├── app.js            ← Core: App namespace, state, API wrapper, chart factory
    ├── main.js           ← 5-tab router, content reparenting, event delegation
    ├── tab-home.js       ← Home tab: overview dashboard, sub-tabs (sectors/report/trends)
    ├── tab-stocks.js     ← Stocks tab: wraps analysis + bursa, view toggle
    ├── tab-analysis.js   ← Analysis: 15 indicator charts, ML prediction, earnings
    ├── tab-bursa.js      ← Bursa market: industry cards, watchlist, order book
    ├── tab-analyst.js    ← AI Analyst: picks with LLM reasoning, scorecard, accuracy chart
    ├── tab-catalyst.js   ← Catalyst: US + Bursa picks, events, knowledge graph cascade
    ├── tab-news.js       ← News hub: AI classification, sentiment pies
    ├── tab-settings.js   ← Settings: wraps model info
    ├── tab-model.js      ← Model info: 107 features, accuracy, weights
    ├── tab-sectors.js    ← Sector heatmap (used by Home tab)
    ├── tab-report.js     ← Daily report (used by Home tab)
    ├── tab-trends.js     ← Prediction trends (used by Home tab)
    ├── tab-shortterm.js  ← Short-term reasoner picks (24h/3d/7d)
    ├── tab-paper.js      ← Paper Trading: 5 strategies, equity curve, positions, trades
    └── tab-tasks.js      ← Scheduled Tasks panel (Settings tab)
```

**8 User-Facing Tabs:**
- **Home** — landing page with overview + sub-tabs: Sectors, Report, Trends
- **Stocks** — unified stock analysis with view toggle: Search & Analyse / Bursa Market
- **Catalyst** — news-driven 24h stock picks (US + Bursa split)
- **Short-term** — Claude-reasoned 24h/3d/7d Bursa picks with cascade explanations
- **AI Analyst** — self-learning LLM picks with reasoning, scorecard with failure analysis
- **Paper Trading** — 5 virtual strategies with equity curves, positions, realized P&L
- **News** — news intelligence hub with AI classification
- **Settings** — model info, signal weights, training stats, scheduled tasks panel

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
| `analyst_reports` | AI analyst daily reports with picks (3x daily) |
| `analyst_outcomes` | 24h accuracy tracking + `failure_analysis` JSON (structured Claude post-mortem on wrong picks) |
| `catalyst_alerts` | Detected catalyst events with stock picks per scan |
| `catalyst_outcomes` | 24h outcome tracking for catalyst predictions |
| `stock_knowledge` | Bursa stock relationships (business, parent/child, suppliers, competitors) |
| `watchlist` | User's personal watchlist (symbol, note, price alerts) |
| `news_tracker_state` | Last fetch time per news source |
| `virtual_strategies` | Paper trading strategy definitions (5 strategies with entry/exit rules) |
| `virtual_portfolios` | Per-strategy cash balance + equity |
| `virtual_positions` | Open paper positions (symbol, entry price, stop/target, unrealized P&L) |
| `virtual_trades` | Every paper trade (buys + exits with realized P&L, reason: entry/stop_loss/take_profit/time_stop) |
| `virtual_equity_snapshots` | Per-strategy equity time series for the curve chart |

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
| `GET /api/analyst/latest` | Latest AI analyst report + picks | instant |
| `GET /api/analyst/history` | Past analyst reports (default 7 days) | instant |
| `GET /api/analyst/accuracy` | Rolling accuracy stats (30 day) | instant |
| `POST /api/analyst/run` | Trigger manual AI analysis | ~30s |
| `GET /api/catalyst/alerts` | Current catalyst alerts + stock picks (deduped by event_type+headline) | instant |
| `POST /api/catalyst/scan` | Trigger manual catalyst scan | ~15s |
| `GET /api/catalyst/history` | Past catalyst alerts with outcomes | instant |
| `GET /api/analyst/last-evaluated` | Most recent evaluated report + outcomes (for scorecard) | instant |
| `GET /api/analyst/evaluated-reports` | List of evaluated reports (date chips) | instant |
| `GET /api/analyst/report/<report_id>` | Specific report + outcomes with `failure_analysis` parsed | instant |
| `POST /api/analyst/run-eval` | Trigger `run_evaluation.py` (rule-based, no LLM) | ~10s |
| `GET /api/paper/dashboard` | Combined: portfolios + positions + trades + equity + stats | ~300ms |
| `GET /api/paper/portfolios` | Strategies with equity + return % | instant |
| `GET /api/paper/positions` | All open paper positions | instant |
| `GET /api/paper/trades` | Recent paper trades | instant |
| `GET /api/paper/equity-history` | Equity curve time series per strategy | instant |
| `GET /api/paper/stats` | Win rate, avg win/loss, trade count per strategy | instant |
| `GET /api/bursa/all-stocks` | Full Bursa universe (~400 stocks) with liquidity flags | instant |
| `GET /api/scheduled-tasks` | All StockPred-* Windows tasks with status | ~500ms |
| `GET /api/shortterm/latest` | Latest short-term briefing + picks | instant |
| `GET /api/shortterm/history` | Past short-term picks with 24h/3d/7d outcomes | instant |
| `GET /api/shortterm/accuracy` | Rolling accuracy by horizon | instant |

---

## Scheduled Background Workers

| Script | Schedule | What It Does |
|--------|----------|-------------|
| `price_tracker.py` | Every 5 min (market hours) | Price snapshots for tracked stocks |
| `news_tracker.py` | Every 30 min | News articles from Finnhub + RSS + NewsAPI |
| `catalyst_scanner.py` | Every 30 min | Scans news for catalysts, predicts next rising/falling stocks |
| `daily_collector.py` | Daily 6:00 PM | Sentiment features + GDELT daily update |
| `batch_predict.py` | Daily 6:30 PM | Pre-compute predictions for all Bursa stocks |

**Multi-agent analyst pipeline (all scheduled via Windows Task Scheduler, not Claude Code):**

The original 2026-04-11 plan used Claude Code scheduled tasks (`claude-analyst`, `daily-evaluation`, `weekly-retrain`) but those were migrated to permanent Windows Task Scheduler entries on 2026-04-17 because Claude Code schedules are session-scoped (7-day expiry). The actual analyst pipeline now runs as:

- `StockPred-AnalystPicks-Morning/Midday/Evening` (09:15 / 13:15 / 18:15) → `src/data/daily_analysis.py`
- `StockPred-AnalystEval-Morning/Midday/Evening` (09:20 / 13:20 / 18:20) → `src/data/run_evaluation.py`
- `StockPred-FailureAnalysis` (daily 19:00) → `src/data/run_failure_analysis.py` (per-pick Claude post-mortem)
- `StockPred-BatchReflection` (weekly Sun 20:00) → `src/data/run_batch_reflection.py`
- Weekly ML retrain is run manually via `python src/data/train_model.py` when needed; no scheduled task exists for it yet.

(The legacy `article-scraper` Claude Code scheduled task documented in earlier versions of this file was never actually registered — `src/data/scrape_articles.py` is a manual script only. Full-body scraping lives in the short-term subsystem as `StockPred-ShorttermScrape` with its own `news_fulltext` table, independent of `news.summary`.)

**Windows Task Scheduler names (25 total, all `schtasks`-based):**

| Task Name | Schedule |
|-----------|----------|
| `StockPred-PriceTracker` | Every 5 min (market hours) |
| `StockPred-NewsTracker` | Every 30 min |
| `StockPred-CatalystScan` | Every 30 min |
| `StockPred-SocialCollector` | Every 2 hours |
| `StockPred-DailyCollector` | Daily 18:00 |
| `StockPred-BatchPredict` | Daily 18:30 |
| `StockPred-AnalystPicks-Morning/Midday/Evening` | Daily 09:15 / 13:15 / 18:15 (runs `daily_analysis.py`) |
| `StockPred-AnalystEval-Morning/Midday/Evening` | Daily 09:20 / 13:20 / 18:20 (runs `run_evaluation.py`) |
| `StockPred-FailureAnalysis` | Daily 19:00 (Claude post-mortem on wrong picks) |
| `StockPred-BatchReflection` | Weekly Sun 20:00 (compiles signal rules JSON) |
| `StockPred-DiscoverBursa` | Weekly Sun 01:00 (refreshes `bursa_all_stocks.json`) |
| `StockPred-PaperTrade-Morning/Midday/Evening` | Daily 09:25 / 13:25 / 18:25 |
| `StockPred-PaperMonitor` | Every 30 min (stops, MTM, equity snapshots) |
| `StockPred-ShorttermScrape` | Every 30 min at :35 |
| `StockPred-ShorttermReason-Morning/Midday/Close/Eve` | Daily 08:30 / 12:30 / 16:30 / 20:30 |
| `StockPred-ShorttermEval` | Daily 06:30 |

Visibility: Dashboard → **Settings** tab → "Scheduled Tasks" panel pulls this list live via `/api/scheduled-tasks` (groups by category, shows next run + last result).

Setup: Run `setup_daily_collector.bat` once to register all tasks.

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

- **AI Analyst (long-term):** Scheduled via Windows Task Scheduler — `StockPred-AnalystPicks-*` (3x daily picks with Claude reasoning), `StockPred-AnalystEval-*` (24h accuracy check), `StockPred-FailureAnalysis` (daily Claude post-mortem), `StockPred-BatchReflection` (weekly pattern extraction). Self-learning feeds `data/analyst_signal_rules.json` + `data/analyst_sample_weights.json`.
- **Short-term News Reasoner (Claude Code, 24h–7d):** Siloed pipeline under `src/shortterm/`. Scrapes full article bodies (not just headlines), reasons with `AGENT.md`/`SKILL.md`/`MEMORY.md` injected into the prompt, emits per-horizon picks with cascade explanations. Evaluator auto-rewrites `MEMORY.md` daily. Bursa-only.
- **Catalyst Alerts:** Every 30 min, scans 13 news sources for 11 catalyst types, detects direct stock mentions (219 aliases), expands to related stocks via knowledge graph (parent/subsidiary, supplier/customer, competitors, GLC peers), predicts 24h moves with 75% accuracy ML model
- **Stock Knowledge Graph:** Researched Bursa relationships — Petronas siblings, banking peers, plantation competitors, supplier/customer chains, GLC cross-holdings (Khazanah, PNB, EPF)
- **Ollama LLM:** Local Phi-3 Mini for deep headline analysis — event classification, stock extraction, sentiment reasoning
- **Social Crawlers:** 13 news sources — Yahoo Finance, Benzinga, MarketWatch, CNBC, Investing.com, Google News MY/KLSE, FMT, Malay Mail, i3investor, KLSE Screener, Finnhub, Reddit
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

# AI Analyst — Claude Code multi-agent system
# (runs automatically via scheduled tasks, or manually:)
python src/data/prepare_briefing.py                # prepare data briefing for Claude
python src/data/prepare_briefing.py --market US    # US market briefing
python src/data/save_analyst_report.py --report-file data/analyst_report_latest.json  # save Claude output
python src/data/prepare_evaluation.py              # prepare evaluation data
python src/data/save_evaluation.py --results-file data/evaluation_results.json  # save eval results

# Legacy AI analyst (Ollama-based, still works but replaced by Claude tasks)
python src/data/daily_analysis.py                  # single run (auto-detect time)
python src/data/daily_analysis.py --market US      # analyze US stocks
python src/data/daily_analysis.py --evaluate-only  # only evaluate past picks

# Run catalyst scanner (detect news events, predict stocks)
python catalyst_scanner.py              # single scan
python catalyst_scanner.py --loop       # every 30 min
python catalyst_scanner.py --hours 12   # scan last 12h of news

# Self-learning loop
python -m src.data.run_failure_analysis            # explain wrong picks (per-pick)
python -m src.data.run_failure_analysis --limit 5  # cap at 5 per run
python -m src.data.run_batch_reflection            # compile signal rules (weekly)
python -m src.data.run_batch_reflection --days 60  # wider window

# Paper Trading
python src/paper_trading/runner.py --init-only     # create strategies (first time)
python src/paper_trading/runner.py                 # trade against latest analyst report
python src/paper_trading/monitor.py                # check stops + MTM + equity snapshot

# Bursa universe discovery
python src/data/discover_bursa_stocks.py           # incremental scan of 0001-9999.KL
python src/data/discover_bursa_stocks.py --force    # full rescan

# Run tests
python -m pytest tests/ -v
```

---

## Testing

**298 tests** across 22 test files. All run offline with mocked APIs (~50s).

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

## Short-term News-Driven Subsystem

Lives under `src/shortterm/`. Siloed from the long-term ML pipeline: cannot import from `src/analysis/predictor`, `src/analysis/ai_analyst`, `src/data/train_*`, etc. — enforced by `tests/shortterm/test_silo.py`. Reads only from a whitelist of SQLite tables (`news`, `news_fulltext`, `news_fulltext_mentions`, `price_snapshots`, `shortterm_*`) — enforced by `src/shortterm/db._validate_sql`.

### Repo-root .md files loaded into every reasoner call

| File | Role | Who writes it |
|---|---|---|
| `AGENT.md` | Reasoner role/persona + output contract | Hand-authored, stable |
| `SKILL.md` | Reasoning heuristics (source credibility, cascade magnitudes, calibration guidance) | Hand-authored, evolves slowly |
| `MEMORY.md` | Rolling accuracy stats + recent hits/misses + patterns | Auto-rewritten by `run_evaluate.py` |

`claude_runner.build_prompt()` concatenates AGENT + SKILL + MEMORY + briefing JSON before invoking `claude -p`. The top-level `CLAUDE.md` (this file) is NOT loaded into reasoner prompts — `cwd=$HOME` suppresses it, same trick as `ai_analyst._analyze_stocks_batch_claude()`.

### Pipeline

```
news_tracker (every 30m) → news table
        ↓
filter.candidate_articles     (MY tickers OR high-impact catalyst keyword)
        ↓
scraper_worker.scrape_pending → news_fulltext + news_fulltext_mentions
        ↓                        (Playwright + trafilatura; existing article_scraper.py)
briefing.build_briefing       → JSON (articles + bodies + cascade + 7d prices)
        ↓
claude_runner.call_claude     → list[pick] (strict JSON array; stdin subprocess)
        ↓
save_picks.persist            → shortterm_picks (strict validation)
        ↓ (24h/3d/7d later)
evaluator.measure_due_outcomes → shortterm_outcomes
        ↓
evaluator.rewrite_memory_md   → MEMORY.md  (feeds next reasoner run)
```

### Tables (see `src/shortterm/schema.py`)

- `news_fulltext` — full article body keyed by `news.id` (parallel to `news`)
- `news_fulltext_mentions` — Bursa stock mentions detected in the body
- `shortterm_briefings` — archived input JSON per run
- `shortterm_picks` — one row per (symbol, horizon) pick
- `shortterm_outcomes` — 24h/3d/7d resolved outcomes with direction_correct

### Scheduler entries (Windows Task Scheduler, added by `setup_daily_collector.bat`)

| Task | Cadence |
|---|---|
| `StockPred-ShorttermScrape` | Every 30 min at :35 (offset +5 from NewsTracker) |
| `StockPred-ShorttermReason-Morning` | Daily 08:30 MYT |
| `StockPred-ShorttermReason-Midday` | Daily 12:30 MYT |
| `StockPred-ShorttermReason-Close` | Daily 16:30 MYT |
| `StockPred-ShorttermReason-Eve` | Daily 20:30 MYT |
| `StockPred-ShorttermEval` | Daily 06:30 MYT (rewrites MEMORY.md) |

Plus catalyst-trigger reasoning: `run_scrape.py` spawns `run_reason.py` if a newly-scraped article matches a high-impact catalyst keyword and ≥60 min have elapsed since the last run (gated by `data/shortterm/last_run.txt`).

### Manual commands

```bash
python -m src.shortterm.runners.run_scrape                    # fetch full bodies for candidates
python -m src.shortterm.runners.run_reason --dry-run          # build briefing only
python -m src.shortterm.runners.run_reason --print-prompt     # inspect full Claude prompt
python -m src.shortterm.runners.run_reason                    # full pipeline (default ensemble N=3, min_agreement=2)
python -m src.shortterm.runners.run_reason --n-runs 1         # legacy single-call mode
python -m src.shortterm.runners.run_reason --n-runs 5 --min-agreement 3   # stricter consensus
python -m src.shortterm.runners.run_evaluate                  # measure outcomes + rewrite MEMORY.md
pytest tests/shortterm/ -v                                    # silo + unit tests
```

**Ensemble consensus** (default for run_reason since 2026-04-20): each reasoning cycle
calls Claude N=3 times on the same briefing; only picks that appear in ≥2 runs survive
into `shortterm_picks`. Confidence/predicted_move are median-aggregated across agreeing
runs; `source_news_ids` are unioned; `ensemble_agreement` + `ensemble_n_runs` columns
record the vote count for visibility (badge shows "consensus 3/3" in the UI). Cost: 3×
Claude CLI calls per cycle (~90-180s total). Empirically filters LLM noise hard — the
biggest single-lever win-rate improvement before ML retraining.

---

## Self-Learning Loop (AI Analyst)

Three components that turn wrong picks into measurable model improvements:

### 1. Per-pick failure analysis — `src/data/run_failure_analysis.py` (daily 19:00)

For each wrong pick without a `failure_analysis`, calls Claude CLI with the original reasoning + signal context + actual outcome. Returns structured JSON:

```json
{
  "primary_reason": "signal_conflict | overconfidence | macro_ignored | news_misread | timing | momentum_reversal | low_liquidity",
  "overweighted_signal": "technical | sentiment | momentum | macro | news | fundamentals",
  "underweighted_signal": "...",
  "lesson": "one concrete rule, max 20 words",
  "market_condition": "trending | ranging | volatile | gap_day"
}
```

Stored in `analyst_outcomes.failure_analysis`. Shown in the scorecard UI ("Why wrong?" column).

Also writes `data/analyst_sample_weights.json` — `{"SYMBOL_DATE": weight}` with wrong picks weight=3.0, correct weight=1.5.

### 2. Batch pattern reflection — `src/data/run_batch_reflection.py` (weekly Sun 20:00)

Digests all analyzed failures from the last 30 days. Groups by `primary_reason` and `overweighted_signal`. Asks Claude for up to 5 structured signal rules:

```json
{
  "rules": [
    {
      "id": "rule_1",
      "condition": "RSI > 72 AND avg_sentiment < -0.1",
      "bias": "bullish overconfidence",
      "action": "skip | reduce_confidence | flip_direction | require_confirmation",
      "confidence": "high | medium | low",
      "supported_by_n_failures": 8
    }
  ]
}
```

Saved to `data/analyst_signal_rules.json`. `prepare_briefing.py` injects these rules as hard constraints into every future briefing under the `signal_rules` key.

### 3. ML training sample weight boost — `src/data/train_model.py`

`_load_analyst_sample_weights()` reads the JSON weights file and builds a pandas Series aligned with `df["symbol"]_df["date"]`. Both XGBoost and LightGBM `.fit()` calls receive `sample_weight=sw_train`. Wrong-pick training rows get 3× weight, correct picks 1.5×, unmarked rows 1×. This makes the weekly retrain emphasize exactly the stocks/dates Claude misjudged.

This is **real ML learning** (as opposed to just prompt-engineering reflections) — the XGBoost/LightGBM model weights actually change based on Claude's pick outcomes.

---

## Paper Trading Engine

Lives under `src/paper_trading/`. Simulates order execution against 5 virtual strategies with realistic Bursa/US fee models, stop-loss/take-profit monitoring, and equity curve tracking. No real money, no IB dependency — pure in-app simulation.

### Module layout

```
src/paper_trading/
├── costs.py       ← Bursa (0.08% + SST + stamp duty, min RM10) + US fee model
├── broker.py      ← VirtualBroker class: buy, sell, close_position, mark_to_market, check_stops
├── strategies.py  ← 5 Strategy dataclasses with entry filters + position sizing
├── runner.py      ← Fires after analyst picks: filters → sizes → opens positions
└── monitor.py     ← Every 30 min: checks stops/TP, time-stop 24h, MTM, writes equity snapshot
```

### Strategies (5, each with its own RM50,000)

| ID | Min Conf | Min Move | Max Pos | Notes |
|----|----------|----------|---------|-------|
| `relaxed` | 0.55 | 0.8% | 5% | Trades most picks, no cost filter — for data collection |
| `baseline` | 0.60 | 2.0% | 15% | Strict cost-aware filter |
| `top3` | 0.60 | 2.0% | 15% | Only top 3 picks by confidence per report |
| `high_conviction` | 0.70 | 3.0% | 15% | Only high-probability big movers |
| `bull_and_bear` | 0.60 | 2.0% | 15% | Accepts both bullish + bearish picks |

### Operational loop

```
09:25 / 13:25 / 18:25  PaperTrade-*     → runner.py (opens positions on new picks)
every :00 / :30        PaperMonitor     → monitor.py (closes SL/TP/time_stop + MTM + equity snapshot)
```

### Dashboard

"Paper Trading" tab (`web/static/js/tab-paper.js`) with 4 sections:
- **Strategy cards** — equity, total return %, open/closed count, win rate
- **Equity curve chart** — 5 series overlay, 30-day window
- **Open positions table** — with filter-by-strategy dropdown
- **Recent trades log** — last 50 trades with realized P&L

All fed by a single `/api/paper/dashboard?days=30&trades_limit=50` endpoint (combined query ~300ms vs 5 separate calls through ngrok).

### Manual commands

```bash
python src/paper_trading/runner.py --init-only        # create/reset strategies
python src/paper_trading/runner.py                    # trade against latest analyst report
python src/paper_trading/runner.py --report-id <id>   # specific report
python src/paper_trading/monitor.py                   # force stops-check + MTM now
python src/paper_trading/monitor.py --time-stop-hours 48   # override 24h default
```

---

## Bursa Universe (Expanded)

`data/bursa_all_stocks.json` — weekly-discovered list of ~400 Bursa Main Market stocks. Each entry:

```json
{
  "symbol": "5398.KL",
  "name": "Gamuda Berhad",
  "short_name": "Gamuda",
  "sector": "Industrial & Manufacturing",
  "market_cap": 25700000000,
  "avg_volume_30d": 17490000,
  "liquid": true,
  "curated": false,
  "discovered_at": "2026-04-17T07:40:00"
}
```

Liquidity = `market_cap >= RM500M OR avg_volume_30d >= 100K`. ~325 of 404 discovered stocks are liquid.

### What uses what

| System | Stock set | Count |
|---|---|---|
| Dashboard Bursa tab (8-industry cards) | `BURSA_INDUSTRIES` (curated) | 80 (unchanged) |
| Entity extractor (news matching) | All discovered | 404 |
| `MY_STOCK_NAMES` | All discovered | 404 |
| ML training | Liquid only | 325 |
| Batch predictions | Liquid only | 325 |
| Short-term reasoner (`BURSA_UNIVERSE`) | Liquid only | 325 |
| Historical data collection | All | 404 |

Fallback: if `bursa_all_stocks.json` is missing, everything reverts to the curated 80.

### Discovery script

```bash
python src/data/discover_bursa_stocks.py           # incremental scan
python src/data/discover_bursa_stocks.py --force    # full rescan
```

---

## Repository

GitHub: `https://github.com/henrychong123/stock-prediction`
Branch: `master`
`.gitignore` includes: `venv/`, `.env`, `ngrok.yml`, `logs/`, `__pycache__/`, `*.pyc`, `data/*.db` (the active DB is `data/predictions.db`, ~1.26 GB), `data/training/`, `models/`
