"""
Stock Knowledge Builder — uses Ollama LLM to build a knowledge graph
of Bursa Malaysia stock relationships.

For each stock, queries the LLM about:
1. Business description
2. Parent/subsidiary companies
3. Key suppliers and customers
4. Related Bursa-listed stocks that move together
5. Commodity/sector exposure

Also supplements with yfinance data for accuracy.

Usage:
    python src/data/build_stock_knowledge.py               # all Bursa stocks
    python src/data/build_stock_knowledge.py --symbol 1155  # specific stock
    python src/data/build_stock_knowledge.py --refresh      # rebuild all
"""

import sys
import os
import json
import time
import logging
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_stock_knowledge, get_stock_knowledge
from src.analysis.llm_analyzer import _call_ollama, is_ollama_available
from config.settings import BURSA_INDUSTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# All Bursa symbols with names and sectors
def _get_bursa_stocks() -> list[dict]:
    stocks = []
    for industry, data in BURSA_INDUSTRIES.items():
        for s in data["stocks"]:
            stocks.append({
                "symbol": s["symbol"],
                "name": s["name"],
                "sector": industry,
            })
    return stocks


# All valid Bursa symbols for validation
def _get_valid_symbols() -> set:
    return {s["symbol"] for s in _get_bursa_stocks()}


def _query_llm_about_stock(symbol: str, name: str, sector: str) -> dict:
    """Ask Ollama about a specific Bursa stock."""
    # Build a stock list for the LLM to reference
    all_stocks = _get_bursa_stocks()
    stock_list = ", ".join(f"{s['name']} ({s['symbol']})" for s in all_stocks[:40])

    prompt = f"""You are a Malaysian stock market expert. Answer about this Bursa Malaysia stock.

Stock: {name} ({symbol})
Sector: {sector}

Other Bursa stocks for reference: {stock_list}

Return ONLY valid JSON with these fields:
{{"business_desc": "<what the company does, 1-2 sentences>",
"parent_company": "<parent company name or empty string>",
"subsidiaries": ["<symbol.KL>"],
"related_stocks": ["<symbol.KL of stocks that move when this stock moves>"],
"suppliers": ["<symbol.KL of companies that supply to this company>"],
"customers": ["<symbol.KL of companies that buy from this company>"],
"commodity_exposure": ["<commodities that affect this stock: oil, palm oil, gold, rubber, etc>"]}}

Use ONLY symbols from the reference list. Return JSON only:"""

    response = _call_ollama(prompt)
    if not response:
        return {}

    return _parse_knowledge_response(response)


def _parse_knowledge_response(text: str) -> dict:
    """Parse LLM response into structured knowledge."""
    if not text:
        return {}

    # Try to find JSON
    start = text.find("{")
    if start < 0:
        return {}

    # Find matching closing brace
    for i in range(len(text) - 1, start, -1):
        if text[i] == "}":
            try:
                data = json.loads(text[start:i + 1])
                return data
            except json.JSONDecodeError:
                continue

    # Fallback: extract fields via regex
    data = {}
    m = re.search(r'"business_desc"\s*:\s*"([^"]*)"', text)
    if m:
        data["business_desc"] = m.group(1)

    m = re.search(r'"parent_company"\s*:\s*"([^"]*)"', text)
    if m:
        data["parent_company"] = m.group(1)

    for field in ["subsidiaries", "related_stocks", "suppliers", "customers", "commodity_exposure"]:
        m = re.search(rf'"{field}"\s*:\s*\[([^\]]*)\]', text)
        if m:
            items = re.findall(r'"([^"]+)"', m.group(1))
            data[field] = items

    return data


def _supplement_with_yfinance(symbol: str, knowledge: dict) -> dict:
    """Add yfinance data to supplement LLM knowledge."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not knowledge.get("business_desc") and info.get("longBusinessSummary"):
            knowledge["business_desc"] = info["longBusinessSummary"][:200]

        # Add sector info
        if info.get("sector"):
            knowledge["yf_sector"] = info["sector"]
        if info.get("industry"):
            knowledge["yf_industry"] = info["industry"]

    except Exception:
        pass

    return knowledge


def _validate_symbols(knowledge: dict, valid_symbols: set) -> dict:
    """Remove invalid stock symbols from knowledge."""
    for field in ["subsidiaries", "related_stocks", "suppliers", "customers"]:
        if field in knowledge and isinstance(knowledge[field], list):
            knowledge[field] = [s for s in knowledge[field]
                                if isinstance(s, str) and s in valid_symbols]
    return knowledge


def build_knowledge(symbol: str, name: str, sector: str, valid_symbols: set) -> dict:
    """Build complete knowledge for one stock."""
    log.info(f"  Querying LLM about {name} ({symbol})...")
    knowledge = _query_llm_about_stock(symbol, name, sector)

    # Supplement with yfinance
    knowledge = _supplement_with_yfinance(symbol, knowledge)

    # Validate symbols
    knowledge = _validate_symbols(knowledge, valid_symbols)

    # Always add sector peers as related stocks
    all_stocks = _get_bursa_stocks()
    sector_peers = [s["symbol"] for s in all_stocks if s["sector"] == sector and s["symbol"] != symbol]
    existing_related = set(knowledge.get("related_stocks", []))
    for peer in sector_peers:
        existing_related.add(peer)
    knowledge["related_stocks"] = list(existing_related)

    return knowledge


def run(symbol: str = None, refresh: bool = False):
    init_db()

    if not is_ollama_available():
        log.error("Ollama is not running. Start Ollama first.")
        return

    stocks = _get_bursa_stocks()
    valid_symbols = _get_valid_symbols()

    if symbol:
        # Find the stock
        stock = next((s for s in stocks if s["symbol"].replace(".KL", "") == symbol
                       or s["symbol"] == symbol), None)
        if not stock:
            log.error(f"Stock {symbol} not found in Bursa list")
            return
        stocks = [stock]

    total = len(stocks)
    log.info(f"Building knowledge graph for {total} Bursa stocks...")

    built = 0
    for i, stock in enumerate(stocks, 1):
        sym = stock["symbol"]
        name = stock["name"]
        sector = stock["sector"]

        # Skip if already exists and not refreshing
        if not refresh:
            existing = get_stock_knowledge(sym)
            if existing and existing.get("business_desc"):
                log.info(f"  [{i}/{total}] {sym} {name} — already has knowledge, skipping")
                continue

        log.info(f"  [{i}/{total}] {sym} {name} ({sector})")

        knowledge = build_knowledge(sym, name, sector, valid_symbols)

        save_stock_knowledge({
            "symbol": sym,
            "name": name,
            "market": "MY",
            "sector": sector,
            "business_desc": knowledge.get("business_desc", ""),
            "parent_company": knowledge.get("parent_company", ""),
            "subsidiaries": knowledge.get("subsidiaries", []),
            "related_stocks": knowledge.get("related_stocks", []),
            "suppliers": knowledge.get("suppliers", []),
            "customers": knowledge.get("customers", []),
            "commodity_exposure": knowledge.get("commodity_exposure", []),
            "raw_knowledge": knowledge,
        })
        built += 1

        # Rate limit (Ollama is local but give it breathing room)
        time.sleep(1)

    log.info(f"\nDone — built knowledge for {built}/{total} Bursa stocks")

    # Print summary
    from src.database import get_all_stock_knowledge
    all_knowledge = get_all_stock_knowledge()
    total_relations = sum(len(k.get("related_stocks", [])) for k in all_knowledge)
    total_suppliers = sum(len(k.get("suppliers", [])) for k in all_knowledge)
    total_customers = sum(len(k.get("customers", [])) for k in all_knowledge)
    log.info(f"Knowledge graph: {len(all_knowledge)} stocks, "
             f"{total_relations} relationships, "
             f"{total_suppliers} supplier links, "
             f"{total_customers} customer links")


if __name__ == "__main__":
    args = sys.argv[1:]
    symbol = None
    refresh = "--refresh" in args

    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            symbol = args[i + 1]

    run(symbol=symbol, refresh=refresh)
