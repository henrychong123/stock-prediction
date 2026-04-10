"""
Local LLM Analyzer — uses Ollama for deep headline analysis.

Wraps the Ollama API (localhost:11434) to provide:
1. Richer event classification than keyword matching
2. Indirect stock mention detection ("iPhone sales surge" → Apple → AAPL)
3. Reasoning about WHY a headline is bullish/bearish
4. Urgency scoring (breaking news vs routine update)

Falls back gracefully to keyword matching if Ollama is not running.

Usage:
    from src.analysis.llm_analyzer import analyze_headline, is_ollama_available

    if is_ollama_available():
        result = analyze_headline("Apple beats Q4 earnings by 20%")
        # {event_type, affected_stocks, sentiment, confidence, reasoning, urgency}
"""

import os
import json
import logging
import requests
from functools import lru_cache

log = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
OLLAMA_TIMEOUT = 120  # seconds per request (first call loads model, can be slow)


def is_ollama_available() -> bool:
    """Check if Ollama is running and has the configured model."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        # Check if our model (or any variant) is available
        return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False


def _call_ollama(prompt: str, temperature: float = 0.1) -> str:
    """Call Ollama generate API. Returns the response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 300,
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
        return ""
    except Exception as e:
        log.warning(f"Ollama call failed: {e}")
        return ""


def analyze_headline(headline: str) -> dict | None:
    """Analyze a single headline using local LLM.

    Returns:
        {event_type, affected_stocks, sentiment, confidence, reasoning, urgency}
        or None if Ollama is unavailable.
    """
    if not is_ollama_available():
        return None

    prompt = f"""Return ONLY valid JSON, nothing else. No explanation.

Headline: "{headline}"

{{"event_type":"<supply_chain|tariff|rate_decision|commodity|regulation|earnings|tech|geopolitical|pandemic|disaster|merger|none>","affected_stocks":["<TICKER>"],"sentiment":"<bullish|bearish|neutral>","confidence":<0.0-1.0>,"reasoning":"<one sentence>"}}

JSON:"""

    response = _call_ollama(prompt)
    if not response:
        return None

    return _parse_llm_response(response)


def analyze_headlines_batch(headlines: list[str]) -> list[dict]:
    """Analyze multiple headlines in a single LLM call (more efficient).

    Returns list of analysis dicts, one per headline.
    """
    if not headlines or not is_ollama_available():
        return [None] * len(headlines)

    # Batch up to 5 headlines per call
    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:5]))

    prompt = f"""Analyze these financial news headlines. For EACH headline, return a JSON object on its own line with:
- "event_type": one of [supply_chain, tariff, rate_decision, commodity, regulation, earnings, tech, geopolitical, pandemic, disaster, merger, none]
- "affected_stocks": list of ticker symbols mentioned or implied
- "sentiment": "bullish" or "bearish" or "neutral"
- "confidence": 0.0 to 1.0
- "reasoning": one sentence why

Headlines:
{numbered}

Return one JSON per line, numbered to match:"""

    response = _call_ollama(prompt)
    if not response:
        return [None] * len(headlines)

    # Parse each line as JSON
    results = []
    for line in response.strip().split("\n"):
        parsed = _parse_llm_response(line)
        results.append(parsed)

    # Pad if LLM returned fewer results than headlines
    while len(results) < len(headlines):
        results.append(None)

    return results[:len(headlines)]


def _parse_llm_response(text: str) -> dict | None:
    """Extract structured data from LLM response. Handles messy/partial output."""
    import re

    if not text:
        return None

    text = text.strip()

    # Try direct JSON parse first
    try:
        return _normalize_result(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Try finding valid JSON block
    start = text.find("{")
    if start >= 0:
        # Try every closing brace from the end
        for i in range(len(text) - 1, start, -1):
            if text[i] == "}":
                try:
                    return _normalize_result(json.loads(text[start:i+1]))
                except json.JSONDecodeError:
                    continue

    # Fallback: extract fields individually via regex
    result = {}

    # event_type
    m = re.search(r'"event_type"\s*:\s*"([^"]+)"', text)
    if m:
        result["event_type"] = m.group(1)

    # affected_stocks
    m = re.search(r'"affected_stocks"\s*:\s*\[([^\]]*)\]', text)
    if m:
        stocks = re.findall(r'"([A-Z0-9.]+)"', m.group(1))
        result["affected_stocks"] = stocks

    # sentiment
    m = re.search(r'"sentiment"\s*:\s*"([^"]+)"', text)
    if m:
        result["sentiment"] = m.group(1)

    # confidence
    m = re.search(r'"confidence"\s*:\s*([0-9.]+|"[^"]+")', text)
    if m:
        result["confidence"] = m.group(1).strip('"')

    # reasoning
    m = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text)
    if m:
        result["reasoning"] = m.group(1)

    if result:
        return _normalize_result(result)

    return None


def _normalize_result(data: dict) -> dict:
    """Normalize LLM output values to expected format."""
    if not isinstance(data, dict):
        return data

    # Normalize sentiment
    sent = str(data.get("sentiment", "")).lower()
    if sent in ("positive", "bullish", "buy"):
        data["sentiment"] = "bullish"
    elif sent in ("negative", "bearish", "sell"):
        data["sentiment"] = "bearish"
    else:
        data["sentiment"] = "neutral"

    # Normalize confidence to float
    conf = data.get("confidence", 0.5)
    if isinstance(conf, str):
        conf_map = {"high": 0.85, "medium": 0.6, "low": 0.3}
        conf = conf_map.get(conf.lower(), 0.5)
    data["confidence"] = min(max(float(conf), 0), 1)

    # Normalize event_type
    etype = str(data.get("event_type", "none")).lower().replace(" ", "_")
    valid_types = {"supply_chain", "tariff", "rate_decision", "commodity", "regulation",
                   "earnings", "tech", "geopolitical", "pandemic", "disaster", "merger", "none"}
    # Map common LLM variations
    etype_map = {"earnings_report": "earnings", "trade_war": "tariff", "technology": "tech",
                 "interest_rate": "rate_decision", "natural_disaster": "disaster",
                 "merger_acquisition": "merger", "m&a": "merger"}
    etype = etype_map.get(etype, etype)
    if etype not in valid_types:
        etype = "none"
    data["event_type"] = etype

    return data


def enrich_catalyst_with_llm(headline: str, keyword_result: dict) -> dict:
    """Use LLM to enrich/validate keyword-based catalyst detection.

    Takes the keyword-based result and either confirms or overrides it
    with LLM analysis. Falls back to keyword result if LLM unavailable.
    """
    llm_result = analyze_headline(headline)
    if not llm_result:
        return keyword_result  # fallback

    # Merge: LLM provides richer data, keyword provides structure
    enriched = dict(keyword_result)

    # Override event type if LLM is confident
    if llm_result.get("confidence", 0) > 0.6:
        if llm_result.get("event_type") and llm_result["event_type"] != "none":
            enriched["event_type"] = llm_result["event_type"]

    # Add LLM-detected stocks (entity extraction supplement)
    llm_stocks = llm_result.get("affected_stocks", [])
    if llm_stocks:
        enriched["llm_stocks"] = llm_stocks

    # Add reasoning
    if llm_result.get("reasoning"):
        enriched["llm_reasoning"] = llm_result["reasoning"]

    # Add urgency
    if llm_result.get("urgency"):
        enriched["urgency"] = llm_result["urgency"]

    return enriched
