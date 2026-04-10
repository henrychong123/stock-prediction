"""
News Catalyst Predictor — detects market-moving events from headlines and
predicts which stocks will rise/fall in the next 24 hours.

Pipeline (runs every 30 min):
1. Scan recent news headlines
2. Classify catalyst event type (supply chain, tariff, rate decision, etc.)
3. Map events to affected industries + direction (bullish/bearish)
4. Rank specific stocks by predicted 24h impact
5. Output top picks with reasoning

Uses: FinBERT sentiment, keyword rules, stock-to-industry mapping, technical momentum.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)

# ── Catalyst ML Model Cache ──────────────────────────────────────────────────
_catalyst_model = None


def _load_catalyst_model():
    """Lazy-load the trained 24h catalyst model."""
    global _catalyst_model
    if _catalyst_model is not None:
        return _catalyst_model

    model_dir = Path("models")
    clf_path = model_dir / "catalyst_clf.json"
    reg_path = model_dir / "catalyst_reg.json"
    le_path = model_dir / "catalyst_le.joblib"
    feat_path = model_dir / "catalyst_features.joblib"

    if not all(p.exists() for p in [clf_path, le_path, feat_path]):
        _catalyst_model = False
        return False

    try:
        import xgboost as xgb
        import joblib

        clf = xgb.XGBClassifier()
        clf.load_model(str(clf_path))

        reg = None
        if reg_path.exists():
            reg = xgb.XGBRegressor()
            reg.load_model(str(reg_path))

        le = joblib.load(le_path)
        features = joblib.load(feat_path)

        _catalyst_model = {
            "clf": clf, "reg": reg, "le": le, "features": features,
        }
        log.info("Catalyst ML model loaded")
        return _catalyst_model
    except Exception as e:
        log.warning(f"Could not load catalyst model: {e}")
        _catalyst_model = False
        return False


def _predict_with_model(features_dict: dict) -> dict | None:
    """Run the catalyst ML model on a single feature dict.

    Returns {direction, confidence, predicted_return} or None.
    """
    model = _load_catalyst_model()
    if not model:
        return None

    try:
        import pandas as pd
        import numpy as np

        feat_names = model["features"]
        row = {f: features_dict.get(f, 0) for f in feat_names}
        X = pd.DataFrame([row], columns=feat_names)
        X = X.fillna(0).replace([np.inf, -np.inf], 0)

        # Direction prediction
        le = model["le"]
        proba = model["clf"].predict_proba(X)[0]
        pred_idx = proba.argmax()
        pred_label = le.classes_[pred_idx]
        pred_conf = float(proba[pred_idx])

        # Magnitude prediction
        pred_return = 0.0
        if model["reg"]:
            pred_return = float(model["reg"].predict(X)[0])

        return {
            "direction": pred_label,  # UP, DOWN, FLAT
            "confidence": pred_conf,
            "predicted_return": round(pred_return, 2),
            "probabilities": {le.classes_[i]: round(float(p), 3) for i, p in enumerate(proba)},
        }
    except Exception:
        return None

# ── Catalyst Event Types ─────────────────────────────────────────────────────

CATALYST_TYPES = {
    "supply_chain": {
        "label": "Supply Chain Disruption",
        "keywords": [
            "supply chain", "shortage", "supply disruption", "chip shortage",
            "semiconductor shortage", "raw material", "port congestion",
            "shipping delay", "logistics disruption", "supply crunch",
            "stockpile", "inventory shortage", "production halt",
        ],
        "impacts": {
            "bullish": ["Commodities & Mining", "Logistics & Transport"],
            "bearish": ["Industrial & Manufacturing", "Consumer & Retail", "Automotive & EV", "Technology"],
        },
    },
    "tariff_trade": {
        "label": "Tariff / Trade War",
        "keywords": [
            "tariff", "trade war", "trade ban", "import duty", "export ban",
            "sanctions", "trade restriction", "trade deal", "trade agreement",
            "customs duty", "import tax", "trade deficit", "trade surplus",
            "retaliatory tariff", "trade tension", "trade policy",
        ],
        "impacts": {
            "bullish": ["Industrial & Manufacturing"],  # domestic producers benefit
            "bearish": ["Technology", "Consumer & Retail", "Automotive & EV"],
        },
    },
    "rate_decision": {
        "label": "Interest Rate Decision",
        "keywords": [
            "interest rate", "rate hike", "rate cut", "fed rate", "federal reserve",
            "monetary policy", "rate decision", "basis points", "hawkish", "dovish",
            "quantitative easing", "quantitative tightening", "bank negara rate",
            "rate pause", "rate hold", "central bank",
        ],
        "impacts": {
            "bullish_on_cut": ["Property & Construction", "Technology", "Consumer & Retail"],
            "bearish_on_cut": ["Banking & Finance"],
            "bullish_on_hike": ["Banking & Finance"],
            "bearish_on_hike": ["Property & Construction", "Technology", "Utilities & Energy"],
        },
    },
    "commodity_spike": {
        "label": "Commodity Price Surge",
        "keywords": [
            "oil price surge", "oil price spike", "gold price", "gold rally",
            "commodity rally", "palm oil price", "metal prices", "copper price",
            "commodity boom", "crude oil surge", "natural gas price",
            "commodity supercycle", "oil shock",
        ],
        "impacts": {
            "bullish": ["Oil & Gas", "Commodities & Mining", "Plantation & Agriculture"],
            "bearish": ["Consumer & Retail", "Logistics & Transport", "Utilities & Energy"],
        },
    },
    "regulation": {
        "label": "Regulatory Change",
        "keywords": [
            "regulation", "regulatory", "FDA approval", "drug approval",
            "antitrust", "monopoly", "deregulation", "compliance",
            "data privacy", "environmental regulation", "carbon tax",
            "government ban", "policy change", "new law", "legislation",
        ],
        "impacts": {
            "bullish": ["Healthcare"],  # FDA approvals
            "bearish": ["Technology"],  # antitrust, privacy
        },
    },
    "earnings_catalyst": {
        "label": "Major Earnings Surprise",
        "keywords": [
            "earnings beat", "earnings miss", "revenue surprise", "profit warning",
            "guidance raise", "guidance cut", "blowout earnings", "record revenue",
            "profit surge", "revenue miss", "earnings shock", "quarterly results",
        ],
        "impacts": {
            "bullish": [],  # depends on specific stock
            "bearish": [],
        },
    },
    "tech_breakthrough": {
        "label": "Technology Breakthrough",
        "keywords": [
            "AI breakthrough", "artificial intelligence", "quantum computing",
            "new technology", "patent", "innovation", "breakthrough",
            "autonomous driving", "electric vehicle", "battery technology",
            "chip technology", "5G rollout", "6G", "space launch",
        ],
        "impacts": {
            "bullish": ["Technology", "Automotive & EV", "Telecommunications"],
            "bearish": [],
        },
    },
    "geopolitical": {
        "label": "Geopolitical Crisis",
        "keywords": [
            "war", "military", "conflict", "invasion", "missile",
            "nuclear", "terrorism", "coup", "political crisis",
            "election", "political instability", "border tension",
            "ceasefire", "peace deal", "diplomatic",
        ],
        "impacts": {
            "bullish": ["Oil & Gas", "Commodities & Mining"],  # safe havens, defense
            "bearish": ["Consumer & Retail", "Technology", "Banking & Finance"],
        },
    },
    "pandemic_health": {
        "label": "Health / Pandemic Event",
        "keywords": [
            "pandemic", "outbreak", "virus", "vaccine", "lockdown",
            "quarantine", "WHO", "health emergency", "epidemic",
            "new variant", "COVID", "infection surge",
        ],
        "impacts": {
            "bullish": ["Healthcare", "Technology"],  # remote work, pharma
            "bearish": ["Gaming & Leisure", "Logistics & Transport", "Consumer & Retail"],
        },
    },
    "natural_disaster": {
        "label": "Natural Disaster",
        "keywords": [
            "earthquake", "hurricane", "typhoon", "flood", "wildfire",
            "tsunami", "drought", "natural disaster", "climate event",
            "storm damage", "infrastructure damage",
        ],
        "impacts": {
            "bullish": ["Property & Construction"],  # rebuilding
            "bearish": ["Utilities & Energy", "Plantation & Agriculture"],
        },
    },
    "merger_acquisition": {
        "label": "M&A / Restructuring",
        "keywords": [
            "acquisition", "merger", "takeover", "buyout", "IPO",
            "spin-off", "restructuring", "divestiture", "hostile bid",
            "deal", "joint venture", "partnership",
        ],
        "impacts": {
            "bullish": [],
            "bearish": [],
        },
    },
}


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class CatalystEvent:
    """A detected market-moving event."""
    event_type: str           # key from CATALYST_TYPES
    label: str                # human-readable label
    headline: str             # triggering headline
    sentiment: float          # FinBERT sentiment (-1 to +1)
    confidence: float         # 0-1 how sure we are this is a real catalyst
    affected_industries: dict # {industry: "bullish"/"bearish"}
    detected_at: str          # ISO timestamp
    source: str = ""          # news source


@dataclass
class StockPick:
    """A ranked stock pick from a catalyst event."""
    symbol: str
    name: str
    industry: str
    direction: str            # "bullish" or "bearish"
    score: float              # 0-100 composite score
    predicted_move_pct: float # estimated 24h move %
    reasons: list = field(default_factory=list)
    catalyst_type: str = ""
    catalyst_headline: str = ""
    current_price: float = 0
    momentum_score: float = 0 # recent technical momentum
    sector_exposure: float = 0 # how pure-play is this stock


# ── Event Detection ──────────────────────────────────────────────────────────

def detect_catalyst_events(headlines: list[dict]) -> list[CatalystEvent]:
    """Classify news headlines into catalyst events.

    Args:
        headlines: list of {headline, sentiment_score, source_platform, fetched_at, ...}

    Returns:
        list of CatalystEvent objects (deduplicated by type)
    """
    events = []
    seen_types = set()

    for article in headlines:
        headline = article.get("headline", "")
        if not headline:
            continue

        headline_lower = headline.lower()
        sentiment = article.get("sentiment_score", 0) or 0

        for event_type, config in CATALYST_TYPES.items():
            if event_type in seen_types:
                continue

            # Count keyword matches
            matches = sum(1 for kw in config["keywords"] if kw.lower() in headline_lower)
            if matches == 0:
                continue

            # Confidence based on number of keyword matches + sentiment strength
            confidence = min(matches * 0.3 + abs(sentiment) * 0.4, 1.0)
            if confidence < 0.2:
                continue

            # Build affected industries with direction
            affected = {}
            impacts = config["impacts"]

            # Handle rate decisions specially (direction depends on sentiment)
            if event_type == "rate_decision":
                is_hike = any(kw in headline_lower for kw in ["hike", "raise", "hawkish", "tighten"])
                is_cut = any(kw in headline_lower for kw in ["cut", "lower", "dovish", "ease"])
                if is_hike:
                    for ind in impacts.get("bullish_on_hike", []):
                        affected[ind] = "bullish"
                    for ind in impacts.get("bearish_on_hike", []):
                        affected[ind] = "bearish"
                elif is_cut:
                    for ind in impacts.get("bullish_on_cut", []):
                        affected[ind] = "bullish"
                    for ind in impacts.get("bearish_on_cut", []):
                        affected[ind] = "bearish"
            else:
                for ind in impacts.get("bullish", []):
                    affected[ind] = "bullish"
                for ind in impacts.get("bearish", []):
                    affected[ind] = "bearish"

            # If sentiment contradicts the expected direction, flip it
            # (e.g., "supply chain crisis RESOLVED" → positive sentiment)
            if sentiment > 0.5 and affected:
                affected = {k: ("bullish" if v == "bearish" else "bearish") for k, v in affected.items()}

            if not affected:
                # Generic events (earnings, M&A) — use sentiment direction
                if sentiment > 0.2:
                    affected = {"General": "bullish"}
                elif sentiment < -0.2:
                    affected = {"General": "bearish"}
                else:
                    continue

            event = CatalystEvent(
                event_type=event_type,
                label=config["label"],
                headline=headline,
                sentiment=sentiment,
                confidence=round(confidence, 3),
                affected_industries=affected,
                detected_at=article.get("fetched_at", datetime.now().isoformat()),
                source=article.get("source_platform", ""),
            )
            events.append(event)
            seen_types.add(event_type)

    # Sort by confidence
    events.sort(key=lambda e: e.confidence, reverse=True)
    return events


# ── Stock Ranking ────────────────────────────────────────────────────────────

def _get_stock_momentum(symbol: str) -> dict:
    """Get recent technical momentum for a stock (lightweight)."""
    import math

    def _safe(v, default=0):
        try:
            f = float(v)
            return default if (math.isnan(f) or math.isinf(f)) else round(f, 2)
        except (TypeError, ValueError):
            return default

    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist.empty or len(hist) < 2:
            return {"momentum": 0, "price": 0, "volume_ratio": 1}

        close = hist["Close"]
        price = _safe(close.iloc[-1])
        ret_1d = _safe((close.iloc[-1] / close.iloc[-2] - 1) * 100)

        vol = hist["Volume"]
        vol_mean = vol.mean()
        vol_ratio = _safe(vol.iloc[-1] / vol_mean if vol_mean > 0 else 1, 1)

        return {
            "momentum": ret_1d,
            "price": price,
            "volume_ratio": vol_ratio,
        }
    except Exception:
        return {"momentum": 0, "price": 0, "volume_ratio": 1}


def _get_stocks_for_industry(industry: str) -> list[dict]:
    """Get stocks belonging to an industry with metadata."""
    stocks = []

    # Bursa stocks from BURSA_INDUSTRIES
    try:
        from config.settings import BURSA_INDUSTRIES
        if industry in BURSA_INDUSTRIES:
            for s in BURSA_INDUSTRIES[industry]["stocks"]:
                stocks.append({
                    "symbol": s["symbol"],
                    "name": s["name"],
                    "market": "MY",
                    "sector_exposure": 0.9,  # Bursa stocks are usually pure-play
                })
    except Exception:
        pass

    # US stocks from S&P 500 via GICS mapping
    try:
        from config.stock_universe import get_sp500
        # GICS → canonical industry
        GICS_MAP = {
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
        REVERSE_MAP = {}
        for gics, canonical in GICS_MAP.items():
            REVERSE_MAP.setdefault(canonical, []).append(gics)

        target_gics = REVERSE_MAP.get(industry, [])
        if target_gics:
            for s in get_sp500():
                if s.get("sector") in target_gics:
                    stocks.append({
                        "symbol": s["symbol"],
                        "name": s["name"],
                        "market": "US",
                        "sector_exposure": 0.8,
                    })
    except Exception:
        pass

    return stocks


def rank_stocks_for_event(event: CatalystEvent, max_picks: int = 10) -> list[StockPick]:
    """Rank stocks by predicted 24h impact from a catalyst event.

    Scoring formula:
    - Sector exposure (pure-play stocks score higher)
    - Recent momentum (stocks already moving in the predicted direction)
    - Volume surge (unusual volume = more attention)
    - Event confidence
    """
    all_picks = []

    for industry, direction in event.affected_industries.items():
        if industry == "General":
            continue

        stocks = _get_stocks_for_industry(industry)
        if not stocks:
            continue

        # Limit per industry to avoid too many yfinance calls
        stocks = stocks[:8]

        for stock in stocks:
            momentum_data = _get_stock_momentum(stock["symbol"])

            # Score components
            exposure_score = stock.get("sector_exposure", 0.5) * 30
            confidence_score = event.confidence * 25

            # Momentum alignment: if stock is already moving in the predicted direction, bonus
            mom = momentum_data["momentum"]
            if direction == "bullish" and mom > 0:
                momentum_score = min(mom * 5, 20)
            elif direction == "bearish" and mom < 0:
                momentum_score = min(abs(mom) * 5, 20)
            else:
                momentum_score = 0

            # Volume surge bonus
            vol_ratio = momentum_data["volume_ratio"]
            volume_score = min((vol_ratio - 1) * 10, 15) if vol_ratio > 1 else 0

            # Sentiment alignment
            sentiment_score = abs(event.sentiment) * 10

            total_score = exposure_score + confidence_score + momentum_score + volume_score + sentiment_score

            # Estimated 24h move (rough)
            base_move = event.confidence * 2  # 0-2% base
            momentum_bonus = mom * 0.3 if (direction == "bullish" and mom > 0) or (direction == "bearish" and mom < 0) else 0
            predicted_move = round(base_move + momentum_bonus, 2)
            if direction == "bearish":
                predicted_move = -abs(predicted_move)

            reasons = [
                f"Catalyst: {event.label}",
                f"Industry: {industry} ({direction})",
            ]
            if vol_ratio > 1.5:
                reasons.append(f"Volume surge: {vol_ratio:.1f}x average")
            if abs(mom) > 1:
                reasons.append(f"Momentum: {mom:+.1f}% today")

            pick = StockPick(
                symbol=stock["symbol"],
                name=stock["name"],
                industry=industry,
                direction=direction,
                score=round(total_score, 1),
                predicted_move_pct=predicted_move,
                reasons=reasons,
                catalyst_type=event.event_type,
                catalyst_headline=event.headline,
                current_price=momentum_data["price"],
                momentum_score=round(momentum_score, 1),
                sector_exposure=stock.get("sector_exposure", 0.5),
            )
            all_picks.append(pick)

    # Sort by absolute score (best picks first)
    all_picks.sort(key=lambda p: p.score, reverse=True)

    # Return top picks, ensuring mix of bullish and bearish
    bullish = [p for p in all_picks if p.direction == "bullish"]
    bearish = [p for p in all_picks if p.direction == "bearish"]

    result = []
    bi, si = 0, 0
    while len(result) < max_picks and (bi < len(bullish) or si < len(bearish)):
        if bi < len(bullish):
            result.append(bullish[bi])
            bi += 1
        if si < len(bearish) and len(result) < max_picks:
            result.append(bearish[si])
            si += 1

    return result


# ── Direct Stock Detection ───────────────────────────────────────────────────

def detect_direct_stock_mentions(headlines: list[dict]) -> list[StockPick]:
    """Detect headlines that mention specific stocks by name/ticker.

    These are higher-confidence picks than industry-level mapping because
    the news is directly about the stock.
    """
    from src.analysis.entity_extractor import extract_stocks
    from src.data.train_catalyst_model import EVENT_TYPE_MAP

    picks = []
    seen_symbols = set()

    for article in headlines:
        headline = article.get("headline", "")
        sentiment = article.get("sentiment_score", 0) or 0
        if not headline or abs(sentiment) < 0.1:
            continue  # skip neutral headlines

        matches = extract_stocks(headline)
        if not matches:
            continue

        # Detect event type for this headline
        headline_lower = headline.lower()
        event_type = "none"
        for etype, config in CATALYST_TYPES.items():
            if any(kw.lower() in headline_lower for kw in config["keywords"]):
                event_type = etype
                break

        for match in matches[:2]:  # max 2 stocks per headline
            symbol = match["symbol"]
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)

            # Get live momentum
            momentum_data = {"momentum": 0, "price": 0, "volume_ratio": 1}
            try:
                momentum_data = _get_stock_momentum(symbol)
            except Exception:
                pass

            # ── Try ML model first ──
            ml_result = _predict_with_model({
                "sentiment": sentiment,
                "sentiment_abs": abs(sentiment),
                "sentiment_positive": 1 if sentiment > 0 else 0,
                "event_type_id": EVENT_TYPE_MAP.get(event_type, 0),
                "has_event": 1 if event_type != "none" else 0,
                "match_confidence": match.get("confidence", 0.5),
                "is_alias_match": 1 if match.get("match_type") == "alias" else 0,
                "is_direct_mention": 1 if match.get("match_type") in ("alias", "name") else 0,
                "momentum_5d": momentum_data["momentum"],
                "volume_ratio": momentum_data["volume_ratio"],
                "rsi": 50,  # not available in real-time context
                "volatility": 0,
                "atr": 0,
                "vix": 20,
                "market_close": 0,
                "is_bursa": 1 if symbol.endswith(".KL") else 0,
            })

            if ml_result and ml_result["direction"] != "FLAT":
                # Use ML model predictions
                direction = "bullish" if ml_result["direction"] == "UP" else "bearish"
                predicted_move = ml_result["predicted_return"]
                ml_conf = ml_result["confidence"]

                # Score: ML confidence * 100, boosted by sentiment alignment
                total_score = ml_conf * 80
                total_score += abs(sentiment) * 15
                total_score += match["confidence"] * 10
                if momentum_data["volume_ratio"] > 1.5:
                    total_score += 8

                reasons = [
                    f"Direct mention: \"{headline[:80]}\"",
                    f"ML prediction: {ml_result['direction']} ({ml_conf:.0%} conf)",
                    f"Predicted move: {predicted_move:+.1f}%",
                    f"Sentiment: {sentiment:+.2f}",
                ]
                source_label = "ml"
            else:
                # Fallback: rule-based scoring
                direction = "bullish" if sentiment > 0 else "bearish"
                predicted_move = round(abs(sentiment) * 3 * (1 if direction == "bullish" else -1), 2)

                base_score = 60
                total_score = base_score + abs(sentiment) * 25 + match["confidence"] * 15
                mom = momentum_data["momentum"]
                if (direction == "bullish" and mom > 0) or (direction == "bearish" and mom < 0):
                    total_score += min(abs(mom) * 3, 15)
                if momentum_data["volume_ratio"] > 1.5:
                    total_score += 10

                reasons = [
                    f"Direct mention: \"{headline[:80]}\"",
                    f"Sentiment: {sentiment:+.2f} ({direction})",
                    f"Match: {match['match_type']} \"{match['matched_text']}\"",
                ]
                source_label = "rule"

            if momentum_data["volume_ratio"] > 1.5:
                reasons.append(f"Volume surge: {momentum_data['volume_ratio']:.1f}x average")

            pick = StockPick(
                symbol=symbol,
                name=match["name"],
                industry=match.get("sector", ""),
                direction=direction,
                score=round(total_score, 1),
                predicted_move_pct=predicted_move,
                reasons=reasons,
                catalyst_type="direct_mention",
                catalyst_headline=headline,
                current_price=momentum_data["price"],
                momentum_score=round(momentum_data["momentum"], 2),
                sector_exposure=1.0,
            )
            picks.append(pick)

    picks.sort(key=lambda p: p.score, reverse=True)
    return picks


# ── Knowledge Graph Expansion ────────────────────────────────────────────────

def expand_picks_with_knowledge(picks: list[StockPick]) -> list[StockPick]:
    """Expand stock picks to include related stocks from the knowledge graph.

    When news mentions Petronas Chemicals (5183.KL), auto-add:
    - Siblings: Petronas Dagangan (85%), Petronas Gas (85%), MISC (85%)
    - Suppliers: Sapura Energy (65%), Dialog (65%), Yinson (65%)
    - Competitors: Dialog ↔ Sapura (50%)
    - Same GLC: other Khazanah/PNB stocks (30%)

    Uses hardcoded researched relationships from config/stock_knowledge.py.
    """
    from config.stock_knowledge import get_all_related

    # Build stock name lookup
    stock_names = {}
    try:
        from config.settings import BURSA_INDUSTRIES
        for ind, data in BURSA_INDUSTRIES.items():
            for s in data["stocks"]:
                stock_names[s["symbol"]] = s["name"]
    except Exception:
        pass

    expanded = []
    seen_symbols = {p.symbol for p in picks}

    for pick in picks:
        # Only expand Bursa stocks (knowledge graph is Bursa-only)
        if not pick.symbol.endswith(".KL"):
            continue

        relations = get_all_related(pick.symbol)
        if not relations:
            continue

        for sym, rel_type, discount in relations:
            if sym in seen_symbols:
                continue
            seen_symbols.add(sym)

            rel_name = stock_names.get(sym, sym)
            cascade_score = pick.score * discount
            cascade_move = pick.predicted_move_pct * discount

            cascade_pick = StockPick(
                symbol=sym,
                name=rel_name,
                industry=pick.industry,
                direction=pick.direction,
                score=round(cascade_score, 1),
                predicted_move_pct=round(cascade_move, 2),
                reasons=[
                    f"Cascade from {pick.symbol} ({pick.name})",
                    f"Relationship: {rel_type}",
                    f"Original: {pick.catalyst_headline[:60]}",
                ],
                catalyst_type="cascade",
                catalyst_headline=pick.catalyst_headline,
                current_price=0,
                momentum_score=0,
                sector_exposure=discount,
            )
            expanded.append(cascade_pick)

    return expanded


# ── Full Scan Pipeline ───────────────────────────────────────────────────────

def scan_catalysts(hours_back: int = 6, max_picks: int = 10) -> dict:
    """Full catalyst scan: fetch news → detect events + direct mentions → rank stocks.

    Two-layer detection:
    1. Direct stock mentions (highest confidence) — headline names a specific stock
    2. Industry-level catalyst events — headline describes a market-moving event

    Args:
        hours_back: how many hours of news to scan
        max_picks: max stock picks total

    Returns:
        {events: [...], picks: [...], direct_picks: [...], scanned_at: "..."}
    """
    from src.database import get_all_news

    # Fetch recent headlines
    headlines = get_all_news(limit=200, hours_back=hours_back)
    if not headlines:
        return {
            "events": [],
            "picks": [],
            "direct_picks": [],
            "scanned_at": datetime.now().isoformat(),
            "headlines_scanned": 0,
        }

    log.info(f"Scanning {len(headlines)} headlines from last {hours_back}h...")

    # Layer 1: Direct stock mentions (higher priority)
    direct_picks = detect_direct_stock_mentions(headlines)
    log.info(f"Direct stock mentions: {len(direct_picks)} picks")

    # Layer 2: Industry-level catalyst events
    events = detect_catalyst_events(headlines)
    log.info(f"Catalyst events: {len(events)} events")

    # Rank stocks for each industry event
    industry_picks = []
    for event in events[:5]:
        picks = rank_stocks_for_event(event, max_picks=max_picks)
        industry_picks.extend(picks)
        log.info(f"  {event.label}: {len(picks)} stock picks")

    # Layer 3: Knowledge graph expansion (cascade to related stocks)
    cascade_picks = expand_picks_with_knowledge(direct_picks)
    if cascade_picks:
        log.info(f"Knowledge graph cascade: {len(cascade_picks)} additional picks")

    # Merge: direct picks > cascade > industry picks
    all_picks = list(direct_picks)
    seen = {p.symbol for p in all_picks}

    for pick in cascade_picks:
        if pick.symbol not in seen:
            all_picks.append(pick)
            seen.add(pick.symbol)

    for pick in industry_picks:
        if pick.symbol not in seen:
            all_picks.append(pick)
            seen.add(pick.symbol)

    # Sort by score and limit
    all_picks.sort(key=lambda p: p.score, reverse=True)
    final_picks = all_picks[:max_picks]

    return {
        "events": [asdict(e) for e in events],
        "picks": [asdict(p) for p in final_picks],
        "direct_picks": [asdict(p) for p in direct_picks[:max_picks]],
        "cascade_picks": [asdict(p) for p in cascade_picks[:max_picks]],
        "scanned_at": datetime.now().isoformat(),
        "headlines_scanned": len(headlines),
    }
