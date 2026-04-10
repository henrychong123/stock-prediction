"""
Industry sector analysis and prediction.

Supports multiple markets (US, Malaysia). Defines sectors with representative
stocks, then runs predictions at the sector level by aggregating signals.
"""

from dataclasses import dataclass, field

from config.settings import SIGNAL_WEIGHTS, MY_SIGNAL_WEIGHTS


# ===== US SECTORS (11 GICS) =====
US_SECTORS = {
    "Technology": {
        "description": "Software, hardware, semiconductors, IT services",
        "symbols": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM"],
        "etf": "XLK",
    },
    "Healthcare": {
        "description": "Pharma, biotech, medical devices, health insurance",
        "symbols": ["UNH", "JNJ", "LLY", "PFE", "ABBV"],
        "etf": "XLV",
    },
    "Financials": {
        "description": "Banks, insurance, asset management, fintech",
        "symbols": ["JPM", "BAC", "GS", "V", "MA"],
        "etf": "XLF",
    },
    "Consumer Discretionary": {
        "description": "Retail, autos, luxury goods, entertainment",
        "symbols": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
        "etf": "XLY",
    },
    "Communication Services": {
        "description": "Social media, telecom, streaming, advertising",
        "symbols": ["META", "GOOGL", "NFLX", "DIS", "T"],
        "etf": "XLC",
    },
    "Industrials": {
        "description": "Aerospace, defense, logistics, machinery",
        "symbols": ["CAT", "BA", "UPS", "HON", "GE"],
        "etf": "XLI",
    },
    "Consumer Staples": {
        "description": "Food, beverages, household products, tobacco",
        "symbols": ["PG", "KO", "PEP", "COST", "WMT"],
        "etf": "XLP",
    },
    "Energy": {
        "description": "Oil & gas, exploration, refining, renewables",
        "symbols": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "etf": "XLE",
    },
    "Utilities": {
        "description": "Electric, gas, water utilities, renewable energy",
        "symbols": ["NEE", "DUK", "SO", "D", "AEP"],
        "etf": "XLU",
    },
    "Real Estate": {
        "description": "REITs, property management, real estate services",
        "symbols": ["PLD", "AMT", "EQIX", "SPG", "O"],
        "etf": "XLRE",
    },
    "Materials": {
        "description": "Chemicals, mining, metals, packaging, construction",
        "symbols": ["LIN", "APD", "SHW", "FCX", "NEM"],
        "etf": "XLB",
    },
}

# ===== MALAYSIA SECTORS =====
# Malaysia doesn't have sector ETFs, so we use top stocks per sector.
# The "etf" field uses the sector leader as proxy for analysis.
MY_SECTORS = {
    "Banking & Finance": {
        "description": "Banks, insurance, capital markets",
        "symbols": ["1155.KL", "1295.KL", "1023.KL", "5819.KL", "1066.KL"],
        "etf": "1155.KL",  # Maybank as proxy (largest bank)
    },
    "Oil & Gas": {
        "description": "Petronas-linked, upstream, downstream, services",
        "symbols": ["5183.KL", "5235.KL", "6033.KL", "5218.KL", "5681.KL"],
        "etf": "5183.KL",  # Petronas Chemicals as proxy
    },
    "Telecommunications": {
        "description": "Mobile, broadband, digital services",
        "symbols": ["6947.KL", "6888.KL", "6012.KL", "4863.KL"],
        "etf": "6947.KL",  # CelcomDigi as proxy
    },
    "Plantation & Agriculture": {
        "description": "Palm oil, rubber, timber, agriculture",
        "symbols": ["5285.KL", "2445.KL", "1961.KL"],
        "etf": "5285.KL",  # Sime Darby Plantation as proxy
    },
    "Healthcare": {
        "description": "Hospitals, gloves, pharma, medical devices",
        "symbols": ["5225.KL", "5168.KL", "7113.KL"],
        "etf": "5225.KL",  # IHH Healthcare as proxy
    },
    "Utilities & Energy": {
        "description": "Electricity, gas, water, renewable energy",
        "symbols": ["5347.KL", "6742.KL"],
        "etf": "5347.KL",  # Tenaga Nasional as proxy
    },
    "Consumer & Retail": {
        "description": "F&B, retail, consumer goods",
        "symbols": ["4707.KL", "7084.KL"],
        "etf": "4707.KL",  # Nestle Malaysia as proxy
    },
    "Industrial & Manufacturing": {
        "description": "Metals, manufacturing, construction, shipping",
        "symbols": ["8869.KL", "3816.KL"],
        "etf": "8869.KL",  # Press Metal as proxy
    },
    "Gaming & Leisure": {
        "description": "Casinos, resorts, entertainment",
        "symbols": ["3182.KL", "4715.KL"],
        "etf": "3182.KL",  # Genting Bhd as proxy
    },
}

# Keep backward compatible reference
SECTORS = US_SECTORS


@dataclass
class SectorResult:
    name: str
    description: str
    etf: str
    action: str
    confidence: float
    avg_score: float
    market: str = "US"
    stock_results: list[dict] = field(default_factory=list)
    top_reasons: list[str] = field(default_factory=list)
    signal_breakdown: dict = field(default_factory=dict)


def get_sectors(market: str = "US") -> dict:
    """Get sector definitions for a given market."""
    if market == "MY":
        return MY_SECTORS
    return US_SECTORS


def analyze_sector_etf(sector_name: str, market: str = "US") -> SectorResult:
    """Analyze a sector using its ETF/proxy for a quick high-level view."""
    from src.data_sources.stock_prices import get_technical_signal
    from src.data_sources.news_sentiment import fetch_market_news
    from src.analysis.predictor import combine_signals

    sectors = get_sectors(market)
    weights = MY_SIGNAL_WEIGHTS if market == "MY" else SIGNAL_WEIGHTS

    sector = sectors.get(sector_name)
    if not sector:
        return SectorResult(
            name=sector_name, description="Unknown", etf="",
            action="HOLD", confidence=0, avg_score=0, market=market,
        )

    etf = sector["etf"]

    # Technical signal from sector ETF/proxy
    technical = get_technical_signal(etf)

    # Sector-specific news sentiment
    news_signal = {"signal": "neutral", "strength": 0.5, "reasons": []}
    try:
        market_news = fetch_market_news()
        if market_news and "error" not in market_news[0]:
            sector_keywords = sector_name.lower().split() + [
                s.lower().replace(".kl", "") for s in sector["symbols"]
            ]
            # Add Malaysia-specific keywords
            if market == "MY":
                from config.settings import MY_STOCK_NAMES
                for sym in sector["symbols"]:
                    name = MY_STOCK_NAMES.get(sym, "")
                    if name:
                        sector_keywords.append(name.lower())

            relevant = []
            for article in market_news:
                text = f"{article.get('headline', '')} {article.get('summary', '')}".lower()
                if any(kw in text for kw in sector_keywords):
                    relevant.append(article)

            if relevant:
                scores = [a["sentiment"]["score"] for a in relevant]
                avg = sum(scores) / len(scores)
                news_signal = {
                    "signal": "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral",
                    "strength": round((avg + 1) / 2, 3),
                    "reasons": [a["headline"] for a in relevant[:3]],
                }
    except Exception:
        pass

    # Momentum from ETF
    momentum = {
        "signal": technical.get("signal", "neutral"),
        "strength": technical.get("strength", 0.5),
    }

    signals = {
        "technical": technical,
        "news_sentiment": news_signal,
        "social_sentiment": {"signal": "neutral", "strength": 0.5, "reasons": []},
        "geopolitical": {"signal": "neutral", "strength": 0.5, "reasons": []},
        "market_momentum": momentum,
    }

    action, confidence, *_extra = combine_signals(signals, weights)

    # Compute directional score
    score = 0
    for name, sig in signals.items():
        w = weights.get(name, 0)
        s = sig.get("strength", 0.5)
        score += ((s - 0.5) * 2) * w

    all_reasons = []
    for name, sig in signals.items():
        for r in sig.get("reasons", [])[:2]:
            all_reasons.append(f"[{name}] {r}")

    signal_breakdown = {
        k: {"signal": v.get("signal", "neutral"), "strength": v.get("strength", 0.5)}
        for k, v in signals.items()
    }

    # Save to database
    try:
        from src.database import save_sector_snapshot
        save_sector_snapshot(sector_name, etf, action, confidence, round(score, 3), signal_breakdown)
    except Exception:
        pass

    return SectorResult(
        name=sector_name,
        description=sector["description"],
        etf=etf,
        action=action,
        confidence=confidence,
        avg_score=round(score, 3),
        market=market,
        top_reasons=all_reasons,
        signal_breakdown=signal_breakdown,
    )


def analyze_all_sectors(market: str = "US") -> list[SectorResult]:
    """Run analysis on all sectors for a given market. Returns sorted by score."""
    sectors = get_sectors(market)
    results = []
    for name in sectors:
        result = analyze_sector_etf(name, market=market)
        results.append(result)

    results.sort(key=lambda r: r.avg_score, reverse=True)
    return results


def get_sector_for_symbol(symbol: str) -> str | None:
    """Find which sector a stock belongs to (checks both markets)."""
    for sectors in [US_SECTORS, MY_SECTORS]:
        for sector_name, info in sectors.items():
            if symbol in info["symbols"]:
                return sector_name
    return None
