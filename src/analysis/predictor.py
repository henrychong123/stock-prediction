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


def combine_signals(signals: dict) -> tuple[str, float]:
    """Combine weighted signals into a final prediction.

    Args:
        signals: Dict mapping signal name to signal dict (with 'signal' and 'strength')

    Returns:
        Tuple of (action, confidence)
    """
    weighted_score = 0
    total_weight = 0

    for name, signal_data in signals.items():
        weight = SIGNAL_WEIGHTS.get(name, 0)
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

    Fetches data from all sources, analyzes signals, and produces a prediction.
    """
    from src.data_sources.stock_prices import get_realtime_quote, get_technical_signal
    from src.data_sources.news_sentiment import get_news_signal, fetch_influential_figure_news
    from src.data_sources.geopolitical import get_geopolitical_signal
    from src.data_sources.social_media import get_social_signal

    # Gather all signals
    print(f"  [1/5] Analyzing technical indicators for {symbol}...")
    technical = get_technical_signal(symbol)

    print(f"  [2/5] Analyzing news sentiment for {symbol}...")
    news = get_news_signal(symbol)

    print(f"  [3/5] Scanning social media for {symbol}...")
    social = get_social_signal(symbol)

    print(f"  [4/5] Checking geopolitical events...")
    geopolitical = get_geopolitical_signal()

    print(f"  [5/5] Monitoring influential figures...")
    figure_news = fetch_influential_figure_news()

    # Incorporate influential figure news into social signal
    if figure_news and "error" not in figure_news[0]:
        figure_scores = [n["sentiment"]["score"] for n in figure_news]
        if figure_scores:
            avg_figure = sum(figure_scores) / len(figure_scores)
            # Blend figure sentiment into social signal
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

    # Combine signals
    action, confidence = combine_signals(signals)

    # Compute directional score for DB storage
    score = 0
    for name, sig in signals.items():
        w = SIGNAL_WEIGHTS.get(name, 0)
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
        pass  # Don't let DB errors break predictions

    return PredictionResult(
        symbol=symbol,
        action=action,
        confidence=confidence,
        price_current=current_price,
        signals=signals,
        reasons=all_reasons,
    )
