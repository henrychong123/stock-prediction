"""
Stock Entity Extractor — detects specific stock mentions in news headlines.

Matches company names, tickers, and common aliases against the 589-stock universe.
Returns matched stocks with confidence scores.

Used by the catalyst system to generate direct stock picks from news,
instead of only mapping to industries.
"""

import re
import csv
import io
import logging
from pathlib import Path
from functools import lru_cache

log = logging.getLogger(__name__)

# Words too short/common to match as tickers (would cause false positives)
TICKER_BLACKLIST = {
    "A", "AN", "ALL", "ARE", "AT", "AS", "BE", "BY", "CEO", "CFO",
    "DD", "DO", "FOR", "GO", "HAS", "HE", "HIS", "IF", "IN", "IPO",
    "IS", "IT", "LOW", "MAN", "MAY", "MET", "NEW", "NOW", "OF", "ON",
    "OR", "OUT", "OWN", "PM", "RE", "RUN", "SAY", "SO", "THE", "TO",
    "TOO", "UP", "US", "USA", "UK", "GDP", "FED", "SEC", "FDA", "WHO",
    "CPI", "ETF", "AI", "EV", "IT", "PT", "BUY", "BID", "RAN", "KEY",
    "BIG", "OLD", "TOP", "NET", "TAX", "OIL", "GAS",
}

# Common aliases: alias → ticker
# These are well-known names that don't exactly match the CSV
MANUAL_ALIASES = {
    # US mega-caps
    "apple": "AAPL", "iphone": "AAPL", "ipad": "AAPL", "macbook": "AAPL",
    "microsoft": "MSFT", "windows": "MSFT", "azure": "MSFT", "xbox": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "youtube": "GOOGL", "android": "GOOGL",
    "amazon": "AMZN", "aws": "AMZN", "prime video": "AMZN",
    "tesla": "TSLA", "elon musk": "TSLA", "spacex": "TSLA", "cybertruck": "TSLA",
    "nvidia": "NVDA", "geforce": "NVDA", "cuda": "NVDA",
    "meta": "META", "facebook": "META", "instagram": "META", "whatsapp": "META",
    "zuckerberg": "META",
    "netflix": "NFLX",
    "jpmorgan": "JPM", "jp morgan": "JPM", "jamie dimon": "JPM",
    "goldman sachs": "GS", "goldman": "GS",
    "berkshire": "BRK.B", "warren buffett": "BRK.B", "buffett": "BRK.B",
    "disney": "DIS", "walt disney": "DIS",
    "boeing": "BA",
    "coca-cola": "KO", "coca cola": "KO", "coke": "KO",
    "pepsi": "PEP", "pepsico": "PEP",
    "walmart": "WMT", "wal-mart": "WMT",
    "visa": "V",
    "mastercard": "MA",
    "intel": "INTC",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "ibm": "IBM",
    "uber": "UBER",
    "airbnb": "ABNB",
    "palantir": "PLTR",
    "coinbase": "COIN",
    "amd": "AMD",
    "broadcom": "AVGO",
    "qualcomm": "QCOM",
    # Malaysia blue chips
    "maybank": "1155.KL", "malayan banking": "1155.KL",
    "public bank": "1295.KL",
    "cimb": "1023.KL", "cimb group": "1023.KL",
    "hong leong bank": "5819.KL",
    "rhb bank": "1066.KL", "rhb": "1066.KL",
    "tenaga": "5347.KL", "tenaga nasional": "5347.KL", "tnb": "5347.KL",
    "petronas chemicals": "5183.KL", "pchem": "5183.KL",
    "petronas dagangan": "5681.KL",
    "petronas gas": "6033.KL",
    "sapura energy": "5218.KL", "sapura": "5218.KL",
    "sime darby": "4197.KL", "sime darby plantation": "5285.KL",
    "ihh healthcare": "5225.KL", "ihh": "5225.KL",
    "top glove": "7113.KL",
    "hartalega": "5168.KL",
    "genting": "3182.KL", "genting berhad": "3182.KL",
    "genting malaysia": "4715.KL",
    "celcomdigi": "6947.KL", "digi": "6947.KL",
    "maxis": "6012.KL",
    "axiata": "6888.KL",
    "nestle malaysia": "4707.KL", "nestle": "4707.KL",
    "press metal": "8869.KL",
    "misc": "3816.KL", "misc berhad": "3816.KL",
    "dialog": "7277.KL", "dialog group": "7277.KL",
    "ioi": "1961.KL", "ioi corp": "1961.KL",
    "kuala lumpur kepong": "2445.KL", "klk": "2445.KL",
    "bursa malaysia": "5185.KL", "bursa": "5185.KL",
    "yinson": "7293.KL",
    # Malaysia keywords → most relevant stock
    "petronas": "5183.KL", "pchem": "5183.KL",
    "petronas dagangan": "5681.KL",
    "petronas gas": "6033.KL",
    "bank negara": "1155.KL", "bnm": "1155.KL",  # affects banking → Maybank
    "palm oil": "5285.KL",  # Sime Darby Plantation
    "crude palm oil": "5285.KL", "cpo price": "5285.KL",
    "ringgit": "1155.KL",  # currency → banking sector
    "klci": "5185.KL", "fbm klci": "5185.KL",
    "affin bank": "5185.KL",  # smaller bank
    "ambank": "1015.KL", "ammb": "1015.KL",
    "hong leong": "5819.KL",
    "aeon credit": "5258.KL", "aeon": "5258.KL",
    "allianz": "6139.KL", "allianz malaysia": "6139.KL",
    "yinson holdings": "7293.KL",
    "hap seng": "3034.KL",
    "gamuda": "5398.KL",
    "sunway": "5211.KL",
    "sp setia": "8664.KL",
    "uem sunrise": "5148.KL",
    "astro": "6399.KL", "astro malaysia": "6399.KL",
    "airasia": "5099.KL", "capital a": "5099.KL",
    "ql resources": "7084.KL",
    "mr diy": "5296.KL",
    "parkson": "5657.KL",
    "berjaya": "5196.KL",
    "ytl": "4677.KL", "ytl corp": "4677.KL",
    "ytl power": "6742.KL",
    "malakoff": "5264.KL",
    "telekom malaysia": "4863.KL", "tm": "4863.KL",
    "time dotcom": "5031.KL",
    "hartalega": "5168.KL",
    "top glove": "7113.KL", "topglove": "7113.KL",
    "supermax": "7052.KL",
    "pharmaniaga": "0391.KL",
    "ioi corporation": "1961.KL",
    "kuala lumpur kepong": "2445.KL",
    "felda": "5222.KL", "fgv": "5222.KL",
    "ppb group": "4065.KL",
}


@lru_cache(maxsize=1)
def _build_lookup_table() -> tuple[dict, dict, dict]:
    """Build lookup tables for entity matching.

    Returns:
        (ticker_map, name_map, alias_map)
        - ticker_map: {"AAPL": {"symbol": "AAPL", "name": "Apple Inc.", ...}}
        - name_map: {"apple inc.": "AAPL", "3m": "MMM", ...}
        - alias_map: {"apple": "AAPL", "iphone": "AAPL", ...}
    """
    ticker_map = {}  # symbol → stock info
    name_map = {}    # lowercase name → symbol

    # Load S&P 500 with full names from CSV
    csv_path = Path("data/sp500_tickers.csv")
    if csv_path.exists():
        text = csv_path.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            sym = row.get("Symbol", "").strip()
            name = row.get("Security", "").strip()
            if sym and name:
                ticker_map[sym] = {
                    "symbol": sym,
                    "name": name,
                    "sector": row.get("GICS Sector", ""),
                    "market": "US",
                }
                # Add full name and variants
                name_lower = name.lower()
                name_map[name_lower] = sym

                # Also add without common suffixes
                for suffix in [" inc.", " inc", " corp.", " corp", " co.", " co",
                               " ltd.", " ltd", " plc", " corporation",
                               " company", " holdings", " group", " technologies",
                               " international"]:
                    if name_lower.endswith(suffix):
                        short = name_lower[:-len(suffix)].strip()
                        if len(short) > 2:
                            name_map[short] = sym

    # Load Bursa stocks
    try:
        from config.settings import BURSA_INDUSTRIES
        for industry, data in BURSA_INDUSTRIES.items():
            for s in data["stocks"]:
                sym = s["symbol"]
                name = s["name"]
                ticker_map[sym] = {
                    "symbol": sym,
                    "name": name,
                    "sector": industry,
                    "market": "MY",
                }
                name_map[name.lower()] = sym
    except Exception:
        pass

    # Manual aliases (lowercased)
    alias_map = {k.lower(): v for k, v in MANUAL_ALIASES.items()}

    log.info(f"Entity extractor: {len(ticker_map)} tickers, {len(name_map)} names, {len(alias_map)} aliases")
    return ticker_map, name_map, alias_map


def extract_stocks(headline: str) -> list[dict]:
    """Extract stock mentions from a headline.

    Returns list of matches, each with:
        {symbol, name, market, match_type, matched_text, confidence}

    Match types: "ticker", "name", "alias"
    """
    if not headline:
        return []

    ticker_map, name_map, alias_map = _build_lookup_table()
    headline_lower = headline.lower()
    matches = []
    seen_symbols = set()

    # 1. Check manual aliases first (highest priority, most specific)
    for alias, symbol in alias_map.items():
        if alias in headline_lower and symbol not in seen_symbols:
            info = ticker_map.get(symbol, {})
            matches.append({
                "symbol": symbol,
                "name": info.get("name", symbol),
                "market": info.get("market", "US"),
                "sector": info.get("sector", ""),
                "match_type": "alias",
                "matched_text": alias,
                "confidence": 0.95,
            })
            seen_symbols.add(symbol)

    # 2. Check company names (from CSV)
    for name, symbol in name_map.items():
        if symbol in seen_symbols:
            continue
        if len(name) < 3:
            continue
        # Use word boundary matching for short names to avoid false positives
        if len(name) <= 5:
            pattern = r'\b' + re.escape(name) + r'\b'
            if re.search(pattern, headline_lower):
                info = ticker_map.get(symbol, {})
                matches.append({
                    "symbol": symbol,
                    "name": info.get("name", symbol),
                    "market": info.get("market", "US"),
                    "sector": info.get("sector", ""),
                    "match_type": "name",
                    "matched_text": name,
                    "confidence": 0.85,
                })
                seen_symbols.add(symbol)
        elif name in headline_lower:
            info = ticker_map.get(symbol, {})
            matches.append({
                "symbol": symbol,
                "name": info.get("name", symbol),
                "market": info.get("market", "US"),
                "sector": info.get("sector", ""),
                "match_type": "name",
                "matched_text": name,
                "confidence": 0.9,
            })
            seen_symbols.add(symbol)

    # 3. Check for ticker symbols (uppercase words in the headline)
    # Only for tickers 2+ chars, with word boundaries, not in blacklist
    words = re.findall(r'\b[A-Z]{2,5}\b', headline)
    for word in words:
        if word in seen_symbols or word in TICKER_BLACKLIST:
            continue
        if word in ticker_map:
            info = ticker_map[word]
            matches.append({
                "symbol": word,
                "name": info.get("name", word),
                "market": info.get("market", "US"),
                "sector": info.get("sector", ""),
                "match_type": "ticker",
                "matched_text": word,
                "confidence": 0.8,
            })
            seen_symbols.add(word)

    # Sort by confidence descending
    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches
