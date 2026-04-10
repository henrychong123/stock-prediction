# StockSight — System Architecture

> Auto-updated by Claude Code. Last updated: 2026-04-10

---

## 1. Full System Overview

```mermaid
graph TB
    subgraph External Data Sources
        YF[Yahoo Finance<br/>yfinance - FREE]
        FH[Finnhub API<br/>60 req/min - FREE]
        RD[Reddit API<br/>PRAW - FREE]
        GD[GDELT<br/>Geopolitical - FREE]
        RSS[RSS Feeds<br/>6 feeds - FREE]
        YFRSS[Yahoo Finance<br/>News API - FREE]
        YT[YouTube API<br/>10K/day - FREE]
    end

    subgraph Data Collection Layer
        CH[collect_historical.py<br/>10yr OHLCV + macro]
        CE[collect_earnings.py<br/>EPS history]
        CI[collect_insider.py<br/>SEC filings]
        CA[collect_analyst.py<br/>Recommendations]
        CNH[collect_news_history.py<br/>Headline backfill]
        DC[daily_collector.py<br/>Daily sentiment]
        SC[social_collector.py<br/>Multi-source news]
        NT[news_tracker.py<br/>Live news poll]
        PT[price_tracker.py<br/>Price snapshots]
    end

    subgraph SQLite Database
        TD[(training_data<br/>1.4M rows, 587 stocks)]
        NW[(news<br/>547 articles, 11 platforms)]
        DF[(daily_features<br/>1,282 rows)]
        EH[(earnings_history<br/>2,010 records)]
        IH[(insider_history<br/>90,396 transactions)]
        AH[(analyst_history<br/>2,012 records)]
        GH[(gdelt_history<br/>14,552 records)]
        PR[(predictions<br/>cached results)]
        CAT[(catalyst_alerts<br/>event + stock picks)]
    end

    subgraph ML Models
        XGB[XGBoost<br/>Direction Classifier]
        LGBM[LightGBM<br/>Direction Classifier]
        XGBR[XGBoost<br/>Magnitude Regressor]
        CXGB[Catalyst XGBoost<br/>24h Reaction Model]
    end

    subgraph NLP Models
        FB[FinBERT<br/>Sentiment Analysis]
        OL[Ollama Phi-3 Mini<br/>Headline Analysis]
    end

    subgraph Analysis Engine
        PRED[predictor.py<br/>7-Signal Combiner]
        CATA[catalyst.py<br/>Event Detection +<br/>Stock Ranking]
        EE[entity_extractor.py<br/>583 tickers, 694 names,<br/>140+ aliases]
        LLM[llm_analyzer.py<br/>Ollama wrapper]
    end

    subgraph Flask Dashboard - 8 Tabs
        T1[Analysis Tab<br/>15 indicators, ML prediction]
        T2[Sectors Tab<br/>11 GICS heatmap]
        T3[News Tab<br/>AI classification]
        T4[Trends Tab<br/>Prediction history]
        T5[Report Tab<br/>Daily rankings]
        T6[Model Tab<br/>107 features, accuracy]
        T7[Bursa Tab<br/>80 stocks, watchlist]
        T8[Catalyst Tab<br/>US + Bursa picks]
    end

    YF --> CH & PT
    FH --> CE & CI & CA & NT & CNH
    RD --> DC
    GD --> DC
    RSS --> SC
    YFRSS --> SC
    YT --> SC

    CH --> TD
    CE --> EH
    CI --> IH
    CA --> AH
    CNH --> DF
    DC --> DF & GH
    SC --> NW
    NT --> NW
    PT --> PR

    TD & DF & EH & IH & AH & GH --> XGB & LGBM & XGBR
    NW & TD --> CXGB

    FB --> NW
    OL --> LLM

    XGB & LGBM --> PRED
    CXGB --> CATA
    EE --> CATA
    LLM --> CATA

    PRED --> T1 & T5 & T7
    CATA --> T8
    NW --> T3
    PR --> T4
    TD --> T6
```

---

## 2. Data Flow: How the AI Gets Training Data

```mermaid
flowchart LR
    subgraph "Step 1: Collect Raw Data"
        A1[yfinance<br/>OHLCV prices] -->|10 years| DB1[(training_data<br/>1.4M rows)]
        A2[yfinance<br/>SPY, VIX, ^TNX] -->|Market context| DB1
        A3[yfinance<br/>Oil, Gold, Copper] -->|Cross-asset| DB1
        A4[yfinance<br/>Sector ETFs x11] -->|Sector returns| DB1
    end

    subgraph "Step 2: Collect Supplementary Data"
        B1[Finnhub<br/>EPS actuals] --> DB2[(earnings_history<br/>2,010 records)]
        B2[Finnhub<br/>SEC filings] --> DB3[(insider_history<br/>90K transactions)]
        B3[Finnhub<br/>Analyst recs] --> DB4[(analyst_history<br/>2,012 records)]
        B4[GDELT API<br/>Media tone] --> DB5[(gdelt_history<br/>14.5K records)]
        B5[Finnhub + FinBERT<br/>News sentiment] --> DB6[(daily_features<br/>1,282 rows)]
    end

    subgraph "Step 3: Train Model"
        DB1 --> JOIN{JOIN on<br/>symbol + date}
        DB2 --> JOIN
        DB3 --> JOIN
        DB4 --> JOIN
        DB5 --> JOIN
        DB6 --> JOIN
        JOIN --> FE[Feature Engineering<br/>107 features total]
        FE --> SPLIT[Time-Series Split<br/>80% train / 20% test]
        SPLIT --> XGB[XGBoost<br/>500 trees, depth 6]
        SPLIT --> LGBM[LightGBM<br/>500 trees, depth 6]
        XGB --> ENS[Ensemble<br/>Average probabilities]
        LGBM --> ENS
        ENS --> ACC[Direction: 56.3%<br/>Magnitude MAE: 2.81%<br/>R2: 0.224]
    end
```

---

## 3. Feature Breakdown: What the AI Learns From (107 Features)

```mermaid
pie title "107 ML Features by Category"
    "Technical Indicators (36)" : 36
    "Engineered Features (45)" : 45
    "Market Context (8)" : 8
    "Sentiment (8)" : 8
    "Earnings (4)" : 4
    "Cross-Asset (3)" : 3
    "Alternative Data (2)" : 2
    "Calendar (5)" : 5
```

### Feature Details

| Category | Count | Source | Examples |
|----------|-------|--------|----------|
| **Base OHLCV + Indicators** | 36 | yfinance | RSI, MACD, Bollinger, Ichimoku, ADX, ATR, OBV, VWAP, CCI, PSAR |
| **Engineered** | 45 | Computed | Lagged RSI/MACD/volume (x3 lags), momentum 5d/20d, 52-week position, streaks, EMA convergence, BB width, relative strength, Fear & Greed proxy, cross-asset correlations |
| **Market Context** | 8 | yfinance | SPY close, VIX, Treasury 10Y/2Y, yield spread, DXY, sector ETF return |
| **Sentiment** | 8 | Finnhub + FinBERT + GDELT | News sentiment, Reddit sentiment, figure sentiment, GDELT tone, Fear & Greed |
| **Earnings** | 4 | Finnhub | EPS surprise %, days since earnings, beat rate (4Q), earnings momentum |
| **Cross-Asset** | 3 | yfinance | Oil (CL=F), Gold (GC=F), Copper (HG=F) close prices |
| **Alternative** | 2 | Finnhub | Insider buy ratio (90-day), analyst consensus score |

---

## 4. Signal Weights: How Prediction Score is Calculated

```mermaid
flowchart LR
    subgraph "7 Signals"
        S1[Technical<br/>RSI, MACD, Bollinger]
        S2[News Sentiment<br/>FinBERT NLP]
        S3[ML Model<br/>XGB + LightGBM]
        S4[Social Media<br/>Reddit + Figures]
        S5[Earnings<br/>EPS surprise]
        S6[Momentum<br/>Price trends]
        S7[Geopolitical<br/>GDELT tone]
    end

    subgraph "US Weights"
        S1 -->|22%| SCORE_US[Combined Score]
        S2 -->|18%| SCORE_US
        S3 -->|18%| SCORE_US
        S4 -->|12%| SCORE_US
        S5 -->|12%| SCORE_US
        S6 -->|10%| SCORE_US
        S7 -->|8%| SCORE_US
    end

    subgraph "Malaysia Weights"
        S1 -->|28%| SCORE_MY[Combined Score]
        S3 -->|20%| SCORE_MY
        S6 -->|15%| SCORE_MY
        S7 -->|12%| SCORE_MY
        S2 -->|10%| SCORE_MY
        S4 -->|10%| SCORE_MY
        S5 -->|5%| SCORE_MY
    end

    SCORE_US --> ACTION_US{Score > 0.6: BUY<br/>Score < 0.4: SELL<br/>Else: HOLD}
    SCORE_MY --> ACTION_MY{Score > 0.6: BUY<br/>Score < 0.4: SELL<br/>Else: HOLD}

    OPT[optimize_weights.py<br/>Scipy differential evolution<br/>Trained on 1.4M rows] -.->|Updates| SCORE_US
    OPT -.->|Updates| SCORE_MY
```

---

## 5. Catalyst System: News → Stock Prediction Pipeline

```mermaid
flowchart TB
    subgraph "News Collection (every 30 min - 2 hrs)"
        N1[Finnhub API]
        N2[Google News MY]
        N3[Yahoo Finance News]
        N4[Benzinga RSS]
        N5[MarketWatch RSS]
        N6[CNBC RSS]
        N7[FMT Malaysia]
        N8[Malay Mail]
        N9[Investing.com]
        N10[Reddit PRAW]
        N11[YouTube API]
    end

    N1 & N2 & N3 & N4 & N5 & N6 & N7 & N8 & N9 & N10 & N11 --> DB[(news table<br/>547+ articles)]
    DB --> FB[FinBERT<br/>Sentiment -1 to +1]

    FB --> SCAN[catalyst_scanner.py<br/>Every 30 min]

    SCAN --> L1[Layer 1: Direct Stock Detection]
    SCAN --> L2[Layer 2: Industry Event Detection]

    subgraph "Layer 1: Direct Mentions (high confidence)"
        L1 --> EE[Entity Extractor<br/>583 tickers + 140 aliases]
        EE --> ML1[Catalyst ML Model<br/>83% accuracy, 70K samples]
        ML1 --> PICKS1[Stock Picks<br/>symbol, direction, score,<br/>predicted 24h move]
    end

    subgraph "Layer 2: Industry Events (broader)"
        L2 --> KW[11 Event Types<br/>Supply chain, tariff,<br/>rate, commodity, etc.]
        KW --> IND[Industry Impact Map<br/>bullish/bearish per sector]
        IND --> RANK[Stock Ranker<br/>momentum + volume + exposure]
        RANK --> PICKS2[Industry Picks]
    end

    subgraph "Optional: LLM Enhancement"
        EE --> OL[Ollama Phi-3 Mini<br/>~10s per headline]
        OL --> |enriched analysis| PICKS1
    end

    PICKS1 --> MERGE[Merge + Deduplicate<br/>Direct picks priority]
    PICKS2 --> MERGE

    MERGE --> SPLIT{Split by Market}
    SPLIT --> US[US Stock Mentions<br/>AAPL, TSLA, META...]
    SPLIT --> MY[Bursa Stock Mentions<br/>Maybank, Petronas, Sime Darby...]
    US & MY --> DASH[Catalyst Dashboard Tab]
```

---

## 6. Stock Universe Coverage

```mermaid
flowchart LR
    subgraph "US Market (503 stocks)"
        SP[S&P 500<br/>503 stocks]
        SP --> SEC1[Technology - XLK]
        SP --> SEC2[Healthcare - XLV]
        SP --> SEC3[Financials - XLF]
        SP --> SEC4[Consumer Disc - XLY]
        SP --> SEC5[Communication - XLC]
        SP --> SEC6[Industrials - XLI]
        SP --> SEC7[Consumer Staples - XLP]
        SP --> SEC8[Energy - XLE]
        SP --> SEC9[Utilities - XLU]
        SP --> SEC10[Real Estate - XLRE]
        SP --> SEC11[Materials - XLB]
    end

    subgraph "Bursa Malaysia (81 stocks)"
        MY[KLSE/Bursa<br/>81 stocks]
        MY --> IND1[Banking & Finance<br/>Maybank, CIMB, PBBank...]
        MY --> IND2[Oil & Gas<br/>PChem, Petronas Dag...]
        MY --> IND3[Telecoms<br/>CelcomDigi, Maxis...]
        MY --> IND4[Plantation<br/>Sime Darby, IOI, KLK...]
        MY --> IND5[Healthcare<br/>IHH, Hartalega...]
        MY --> IND6[Utilities<br/>Tenaga, YTL Power...]
        MY --> IND7[Consumer<br/>Nestle, QL Resources...]
        MY --> IND8[Industrial<br/>Press Metal, MISC...]
    end

    subgraph "Indices (5)"
        IDX[Market Indices]
        IDX --> I1[SPY]
        IDX --> I2[QQQ]
        IDX --> I3[DIA]
        IDX --> I4[^GSPC]
        IDX --> I5[^KLSE]
    end
```

---

## 7. Dashboard: What Users See (8 Tabs)

```mermaid
graph TB
    subgraph "Tab 1: Analysis"
        A1[Stock Search Bar]
        A2[15 Technical Indicator Charts]
        A3[5 Overlay Toggles<br/>EMA, VWAP, SAR, Fibonacci, Ichimoku]
        A4[ML Prediction Badge<br/>BUY / HOLD / SELL]
        A5[Weight Distribution<br/>Doughnut Chart]
        A6[Earnings Report Table]
        A7[Market Movers<br/>Influential Figures]
        A8[Fundamentals Card<br/>P/E, P/B, EPS, ROE]
    end

    subgraph "Tab 2: Sectors"
        B1[11 GICS Sector Heatmap]
        B2[Ranked Scores]
    end

    subgraph "Tab 3: News"
        C1[News Intelligence Hub]
        C2[FinBERT Sentiment Pies]
        C3[AI Industry Classification]
        C4[11 Platform Sources]
    end

    subgraph "Tab 4: Trends"
        D1[Prediction History per Stock]
        D2[Sector Trends Over Time]
    end

    subgraph "Tab 5: Report"
        E1[All Stocks Ranked by Score]
        E2[Filter: Action / Industry / Confidence]
        E3[Batch Predict Trigger]
    end

    subgraph "Tab 6: Model"
        F1[107 Features by Category]
        F2[Accuracy: 56.3%]
        F3[Feature Importance Chart]
        F4[Signal Weights]
        F5[Training Data Stats]
    end

    subgraph "Tab 7: Bursa"
        G1[80 Stocks x 8 Industries]
        G2[Live Quotes + Prediction Badges]
        G3[Personal Watchlist]
        G4[Order Book]
        G5[Auto-Refresh Toggle]
    end

    subgraph "Tab 8: Catalyst"
        H1[US Stock Mentions<br/>Direct from headlines]
        H2[Bursa Stock Mentions<br/>Direct from headlines]
        H3[Detected Events<br/>11 catalyst types]
        H4[Top Stock Picks<br/>Score + Predicted Move]
        H5[Scan Now Button]
        H6[History]
    end
```

---

## 8. Scheduled Services (6 Workers)

```mermaid
gantt
    title Scheduled Workers Timeline (24h)
    dateFormat HH:mm
    axisFormat %H:%M

    section Every 5 min
    Price Tracker           :crit, 00:00, 5m
    Price Tracker           :crit, 00:05, 5m
    Price Tracker           :crit, 00:10, 5m

    section Every 30 min
    News Tracker            :active, 00:00, 10m
    Catalyst Scanner        :active, 00:15, 5m
    News Tracker            :active, 00:30, 10m
    Catalyst Scanner        :active, 00:45, 5m

    section Every 2 hours
    Social Collector        :00:10, 15m
    Social Collector        :02:10, 15m

    section Daily
    Daily Collector         :milestone, 18:00, 30m
    Batch Predict           :milestone, 18:30, 60m
    DB Backup               :02:00, 5m
```

---

## 9. Model Accuracy Summary

| Model | Purpose | Data | Accuracy | Top Features |
|-------|---------|------|----------|-------------|
| **Main Direction** | 5-day UP/DOWN/FLAT | 1.4M rows, 107 features | **56.3%** | volatility, vix_high, market_index, oil_close |
| **Main Magnitude** | 5-day % change | same | **MAE 2.81%** | same |
| **Catalyst Direction** | 24h reaction to news | 70K samples, 16 features | **83.0%** | sentiment_positive, is_direct_mention, has_event |
| **Catalyst Magnitude** | 24h % move | same | **MAE 2.01%** | same |
| **FinBERT** | Headline sentiment | Pre-trained (ProsusAI) | ~90% | — |
| **Ollama Phi-3** | Deep headline analysis | Pre-trained (Microsoft) | — | — |
