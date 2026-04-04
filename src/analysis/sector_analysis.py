"""
Industry sector analysis and prediction.

Defines 11 GICS sectors with representative stocks, then runs predictions
at the sector level by aggregating individual stock signals.
"""

from dataclasses import dataclass, field

from config.settings import SIGNAL_WEIGHTS


# 11 GICS Sectors with representative high-cap stocks
SECTORS = {
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


@dataclass
class SectorResult:
    name: str
    description: str
    etf: str
    action: str
    confidence: float
    avg_score: float
    stock_results: list[dict] = field(default_factory=list)
    top_reasons: list[str] = field(default_factory=list)
    signal_breakdown: dict = field(default_factory=dict)


def analyze_sector_etf(sector_name: str) -> SectorResult:
    """Analyze a sector using its ETF for a quick high-level view.

    Uses the sector ETF (e.g., XLK for Technology) for technical analysis,
    which is much faster than analyzing every individual stock.
    """
    from src.data_sources.stock_prices import get_technical_signal, get_realtime_quote
    from src.data_sources.news_sentiment import analyze_sentiment, fetch_market_news
    from src.analysis.predictor import combine_signals

    sector = SECTORS.get(sector_name)
    if not sector:
        return SectorResult(
            name=sector_name, description="Unknown", etf="",
            action="HOLD", confidence=0, avg_score=0,
        )

    etf = sector["etf"]

    # Technical signal from sector ETF
    technical = get_technical_signal(etf)

    # Sector-specific news sentiment (keyword search from market news)
    news_signal = {"signal": "neutral", "strength": 0.5, "reasons": []}
    try:
        market_news = fetch_market_news()
        if market_news and "error" not in market_news[0]:
            sector_keywords = sector_name.lower().split() + [
                s.lower() for s in sector["symbols"]
            ]
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

    action, confidence = combine_signals(signals)

    # Compute a directional score for sorting
    score = 0
    for name, sig in signals.items():
        w = SIGNAL_WEIGHTS.get(name, 0)
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
        top_reasons=all_reasons,
        signal_breakdown=signal_breakdown,
    )


def analyze_all_sectors() -> list[SectorResult]:
    """Run analysis on all 11 GICS sectors. Returns sorted by score."""
    results = []
    for name in SECTORS:
        result = analyze_sector_etf(name)
        results.append(result)

    results.sort(key=lambda r: r.avg_score, reverse=True)
    return results


def get_sector_for_symbol(symbol: str) -> str | None:
    """Find which sector a stock belongs to."""
    for sector_name, info in SECTORS.items():
        if symbol in info["symbols"]:
            return sector_name
    return None
