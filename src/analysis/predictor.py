"""
Prediction engine that combines all data signals into a final stock prediction.

Combines:
1. Technical analysis (price trends, RSI, MACD, Bollinger Bands)
2. News sentiment (company news + market news via FinBERT)
3. Social media sentiment (Reddit discussions)
4. Geopolitical impact (GDELT events: wars, sanctions, policy)
5. Influential figure monitoring (Musk, Trump, etc. via news coverage)

Each signal is weighted according to config/settings.py SIGNAL_WEIGHTS.
"""

from dataclasses import dataclass
from config.settings import SIGNAL_WEIGHTS


@dataclass
class PredictionResult:
    symbol: str
    action: str  # "STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"
    confidence: float  # 0-1
    price_current: float
    signals: dict
    reasons: list[str]

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  PREDICTION: {self.symbol} → {self.action}",
            f"  Confidence: {self.confidence*100:.1f}%",
            f"  Current Price: ${self.price_current:.2f}",
            f"{'='*60}",
            "",
            "  Signal Breakdown:",
        ]

        for name, signal in self.signals.items():
            direction = signal.get("signal", "neutral")
            strength = signal.get("strength", 0.5)
            weight = SIGNAL_WEIGHTS.get(name, 0)
            icon = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "●"
            lines.append(
                f"    {icon} {name:20s} {direction:8s} "
                f"(strength: {strength:.2f}, weight: {weight:.0%})"
            )

        lines.append("")
        lines.append("  Key Reasons:")
        for i, reason in enumerate(self.reasons[:8], 1):
            lines.append(f"    {i}. {reason}")

        lines.append(f"{'='*60}")
        return "\n".join(lines)


def combine_signals(signals: dict, weights: dict | None = None) -> tuple[str, float]:
    """Combine weighted signals into a final prediction.

    Args:
        signals: Dict mapping signal name to signal dict (with 'signal' and 'strength')
        weights: Optional custom weights dict. Defaults to SIGNAL_WEIGHTS.

    Returns:
        Tuple of (action, confidence)
    """
    if weights is None:
        weights = SIGNAL_WEIGHTS

    weighted_score = 0
    total_weight = 0

    for name, signal_data in signals.items():
        weight = weights.get(name, 0)
        if weight == 0:
            continue

        strength = signal_data.get("strength", 0.5)
        # Convert strength (0-1) to directional score (-1 to +1)
        directional = (strength - 0.5) * 2
        weighted_score += directional * weight
        total_weight += weight

    if total_weight > 0:
        final_score = weighted_score / total_weight
    else:
        final_score = 0

    # Map score to action
    if final_score > 0.4:
        action = "STRONG BUY"
    elif final_score > 0.15:
        action = "BUY"
    elif final_score > -0.15:
        action = "HOLD"
    elif final_score > -0.4:
        action = "SELL"
    else:
        action = "STRONG SELL"

    # Confidence is based on how far from neutral and signal agreement
    confidence = min(abs(final_score) * 1.5, 1.0)

    return action, round(confidence, 3)


def predict(symbol: str) -> PredictionResult:
    """Run full prediction pipeline for a stock.

    Automatically detects market (US vs MY) and uses appropriate data sources.
    """
    from src.data_sources.stock_prices import get_realtime_quote, get_technical_signal
    from src.data_sources.news_sentiment import get_news_signal, fetch_influential_figure_news
    from src.data_sources.geopolitical import get_geopolitical_signal
    from src.data_sources.social_media import get_social_signal

    # Detect market
    is_my = symbol.endswith(".KL") or symbol.startswith("^KL")
    if is_my:
        from config.settings import MY_SIGNAL_WEIGHTS, MY_GEOPOLITICAL_KEYWORDS
        weights = MY_SIGNAL_WEIGHTS
    else:
        weights = SIGNAL_WEIGHTS

    # [1/5] Technical indicators (works for both markets via yfinance)
    print(f"  [1/5] Analyzing technical indicators for {symbol}...")
    technical = get_technical_signal(symbol)

    # [2/5] News sentiment (different sources per market)
    print(f"  [2/5] Analyzing news sentiment for {symbol}...")
    if is_my:
        from src.data_sources.news_my import get_my_news_signal
        news = get_my_news_signal(symbol)
    else:
        news = get_news_signal(symbol)

    # [3/5] Social media
    print(f"  [3/5] Scanning social media for {symbol}...")
    social = get_social_signal(symbol)

    # [4/5] Geopolitical events
    print(f"  [4/5] Checking geopolitical events...")
    if is_my:
        geopolitical = get_geopolitical_signal()
        # Also check MY-specific geopolitical keywords
        try:
            from src.data_sources.geopolitical import fetch_geopolitical_events
            my_events = fetch_geopolitical_events(keywords=MY_GEOPOLITICAL_KEYWORDS, max_records=20)
            if my_events and "error" not in my_events[0]:
                tones = [e.get("tone", 0) for e in my_events if isinstance(e.get("tone"), (int, float))]
                if tones:
                    avg_tone = sum(tones) / len(tones)
                    # Blend MY geopolitical with global
                    geo_strength = geopolitical.get("strength", 0.5)
                    my_strength = (max(min(avg_tone / 10, 1), -1) + 1) / 2
                    geopolitical["strength"] = round((geo_strength * 0.4) + (my_strength * 0.6), 3)
                    geopolitical["reasons"] = geopolitical.get("reasons", []) + [
                        f"[MY] {e.get('title', 'N/A')}" for e in my_events[:3] if "error" not in e
                    ]
        except Exception:
            pass
    else:
        geopolitical = get_geopolitical_signal()

    # [5/5] Influential figures
    print(f"  [5/5] Monitoring influential figures...")
    if is_my:
        from src.data_sources.news_my import fetch_my_influential_news
        figure_news = fetch_my_influential_news()
    else:
        figure_news = fetch_influential_figure_news()

    # Incorporate influential figure news into social signal
    if figure_news and "error" not in figure_news[0]:
        figure_scores = [n["sentiment"]["score"] for n in figure_news]
        if figure_scores:
            avg_figure = sum(figure_scores) / len(figure_scores)
            current_social_strength = social.get("strength", 0.5)
            blended = (current_social_strength * 0.6) + (((avg_figure + 1) / 2) * 0.4)
            social["strength"] = round(blended, 3)
            social["reasons"] = social.get("reasons", []) + [
                f"[{n['figure']}] {n['headline']}" for n in figure_news[:3]
            ]

    # Market momentum signal (derived from technical data)
    momentum = {
        "signal": technical.get("signal", "neutral"),
        "strength": technical.get("strength", 0.5),
    }

    signals = {
        "technical": technical,
        "news_sentiment": news,
        "social_sentiment": social,
        "geopolitical": geopolitical,
        "market_momentum": momentum,
    }

    # Get current price
    quote = get_realtime_quote(symbol)
    current_price = quote.get("current_price", 0)

    # Combine signals (with market-appropriate weights)
    action, confidence = combine_signals(signals, weights)

    # Compute directional score for DB storage
    score = 0
    for name, sig in signals.items():
        w = weights.get(name, 0)
        s = sig.get("strength", 0.5)
        score += ((s - 0.5) * 2) * w

    # Collect all reasons
    all_reasons = []
    for name, sig in signals.items():
        for reason in sig.get("reasons", [])[:2]:
            all_reasons.append(f"[{name}] {reason}")

    # Save to database
    try:
        from src.database import save_prediction
        save_prediction(symbol, action, confidence, current_price, score, signals, all_reasons)
    except Exception:
        pass

    return PredictionResult(
        symbol=symbol,
        action=action,
        confidence=confidence,
        price_current=current_price,
        signals=signals,
        reasons=all_reasons,
    )
