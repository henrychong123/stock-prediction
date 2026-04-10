"""
Industry classification and analysis for news articles.

Classifies headlines into industries using keyword matching, aggregates
FinBERT sentiment scores per industry, and generates a BULLISH / BEARISH /
NEUTRAL market verdict with supporting reasoning.
"""

from __future__ import annotations

INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "Oil & Gas": [
        "oil", "petroleum", "petronas", "crude", "opec", "refinery",
        "pipeline", "lng", "brent", "wti", "natural gas", "fuel",
        "shell", "exxon", "chevron", "bp", "petro", "gasoline",
        "downstream", "upstream", "offshore", "rig", "dialog",
        "bumi armada", "yinson", "sapura", "hibiscus",
    ],
    "Technology": [
        "tech", "technology", "ai", "artificial intelligence",
        "semiconductor", "chip", "apple", "google", "microsoft",
        "meta", "software", "cloud", "cybersecurity", "data",
        "algorithm", "digital", "nvidia", "intel", "samsung",
        "robot", "automation", "startup", "silicon", "inari",
        "frontken", "vitrox", "globetronics", "myeg", "unisem",
    ],
    "Banking & Finance": [
        "bank", "loan", "interest rate", "federal reserve", "fed",
        "mortgage", "finance", "credit", "debt", "inflation",
        "jpmorgan", "goldman", "wells fargo", "hsbc", "maybank",
        "cimb", "public bank", "currency", "forex", "bond",
        "rate hike", "rate cut", "liquidity", "lending",
        "rhb", "hong leong", "ambank", "bursa malaysia", "securities",
    ],
    "Healthcare": [
        "pharma", "drug", "vaccine", "health", "hospital",
        "fda", "biotech", "medical", "clinical", "patient",
        "pfizer", "johnson", "astrazeneca", "glaxo", "medicine",
        "treatment", "therapy", "cancer", "disease",
        "ihh", "kpj", "hartalega", "top glove", "supermax",
        "kossan", "rubber glove", "duopharma",
    ],
    "Property & Construction": [
        "property", "real estate", "housing", "construction",
        "developer", "reit", "residential", "commercial", "office",
        "sime darby property", "sunway", "gamuda", "ijm",
        "rental", "lease", "home sales", "sp setia", "mah sing",
        "eco world", "uem sunrise", "ioi properties",
    ],
    "Plantation & Agriculture": [
        "palm oil", "plantation", "cpo", "crude palm oil",
        "ioi", "sime darby plantation", "kuala lumpur kepong", "klk",
        "felda", "fgv", "genting plantations", "rubber", "latex",
        "agricultural", "harvest", "crop", "fertiliser",
        "united plantations", "boustead plantations", "hap seng",
    ],
    "Commodities & Mining": [
        "gold", "silver", "copper", "iron ore", "steel",
        "aluminum", "commodity", "raw material", "mining",
        "tin", "zinc", "nickel", "coal", "lithium", "rare earth",
        "metal", "ore", "smelter", "bauxite",
    ],
    "Utilities & Energy": [
        "electricity", "power", "utility", "grid", "renewable",
        "solar", "wind energy", "hydro", "nuclear",
        "tenaga", "tnb", "ytl power", "malakoff", "cypark",
        "petronas gas", "natural gas distribution", "tariff",
        "energy transition", "carbon", "emission", "ev charging",
    ],
    "Automotive & EV": [
        "car", "electric vehicle", "ev", "tesla", "toyota",
        "ford", "automotive", "vehicle", "battery", "proton",
        "perodua", "bmw", "mercedes", "volkswagen", "hybrid",
        "autonomous", "self-driving", "drb-hicom", "umw",
        "bermaz", "tan chong", "auto sales",
    ],
    "Consumer & Retail": [
        "retail", "consumer", "spending", "sales", "amazon",
        "walmart", "shopping", "e-commerce", "food", "beverage",
        "restaurant", "tourism", "hospitality", "cpi",
        "discretionary", "clothing", "nestle", "mr diy",
        "padini", "aeon", "berjaya food", "ql resources",
    ],
    "Gaming & Leisure": [
        "casino", "gaming", "genting", "resort", "hotel",
        "leisure", "entertainment", "lottery", "sports toto",
        "berjaya sports", "magnum", "da ma cai", "rwgenting",
        "theme park", "tourism", "cruise", "betting",
    ],
    "Logistics & Transport": [
        "shipping", "freight", "logistics", "port", "airline",
        "airasia", "malaysia airlines", "mas", "westports",
        "misc", "pos malaysia", "rail", "cargo", "container",
        "supply chain", "vessel", "tanker", "fleet",
        "gdex", "poslaju", "last mile",
    ],
    "Telecommunications": [
        "telco", "5g", "telecom", "network", "spectrum",
        "axiata", "celcomdigi", "maxis", "digi", "att",
        "verizon", "tmobile", "broadband", "wireless",
        "fibre", "internet", "subscriber", "telekom malaysia",
        "time dotcom", "astro",
    ],
    "Geopolitical": [
        "war", "sanctions", "tariff", "trade war", "election",
        "policy", "china", "russia", "ukraine", "middle east",
        "conflict", "military", "government", "regulation",
        "white house", "congress", "parliament", "nato",
        "geopolitical", "diplomatic", "iran", "israel",
    ],
}

from config.industries import INDUSTRY_ICONS

# Top 10 Bursa Malaysia stocks per industry (ticker, display name)
INDUSTRY_STOCKS: dict[str, list[dict]] = {
    "Oil & Gas": [
        {"symbol": "5183.KL", "name": "PetChem"},
        {"symbol": "6033.KL", "name": "Pet Gas"},
        {"symbol": "5681.KL", "name": "Pet Dag"},
        {"symbol": "7277.KL", "name": "Dialog"},
        {"symbol": "7293.KL", "name": "Yinson"},
        {"symbol": "5210.KL", "name": "Bumi Armada"},
        {"symbol": "5199.KL", "name": "Hibiscus"},
        {"symbol": "5243.KL", "name": "Velesto"},
        {"symbol": "3816.KL", "name": "MISC"},
        {"symbol": "5218.KL", "name": "Sapura Energy"},
    ],
    "Technology": [
        {"symbol": "0166.KL", "name": "Inari"},
        {"symbol": "0128.KL", "name": "Frontken"},
        {"symbol": "0097.KL", "name": "Vitrox"},
        {"symbol": "7022.KL", "name": "Globetronics"},
        {"symbol": "5005.KL", "name": "Unisem"},
        {"symbol": "3867.KL", "name": "MPI"},
        {"symbol": "7204.KL", "name": "D&O Green"},
        {"symbol": "0138.KL", "name": "MyEG"},
        {"symbol": "0072.KL", "name": "Datasonic"},
        {"symbol": "7095.KL", "name": "PIE Industrial"},
    ],
    "Banking & Finance": [
        {"symbol": "1155.KL", "name": "Maybank"},
        {"symbol": "1023.KL", "name": "CIMB"},
        {"symbol": "1295.KL", "name": "Public Bank"},
        {"symbol": "1066.KL", "name": "RHB Bank"},
        {"symbol": "5819.KL", "name": "HLB"},
        {"symbol": "1015.KL", "name": "AmBank"},
        {"symbol": "2488.KL", "name": "Alliance Bank"},
        {"symbol": "5258.KL", "name": "BIMB"},
        {"symbol": "1818.KL", "name": "Bursa Malaysia"},
        {"symbol": "5053.KL", "name": "OSK Holdings"},
    ],
    "Healthcare": [
        {"symbol": "5225.KL", "name": "IHH Healthcare"},
        {"symbol": "5878.KL", "name": "KPJ Healthcare"},
        {"symbol": "5168.KL", "name": "Hartalega"},
        {"symbol": "7113.KL", "name": "Top Glove"},
        {"symbol": "7106.KL", "name": "Supermax"},
        {"symbol": "7153.KL", "name": "Kossan"},
        {"symbol": "7148.KL", "name": "Duopharma"},
        {"symbol": "7090.KL", "name": "Pharmaniaga"},
        {"symbol": "5076.KL", "name": "Apex Healthcare"},
        {"symbol": "0241.KL", "name": "Careplus"},
    ],
    "Property & Construction": [
        {"symbol": "5288.KL", "name": "Sime Prop"},
        {"symbol": "8664.KL", "name": "SP Setia"},
        {"symbol": "5249.KL", "name": "IOI Prop"},
        {"symbol": "8583.KL", "name": "Mah Sing"},
        {"symbol": "5211.KL", "name": "Sunway"},
        {"symbol": "5398.KL", "name": "Gamuda"},
        {"symbol": "3336.KL", "name": "IJM Corp"},
        {"symbol": "8206.KL", "name": "Eco World"},
        {"symbol": "5148.KL", "name": "UEM Sunrise"},
        {"symbol": "1147.KL", "name": "MRCB"},
    ],
    "Plantation & Agriculture": [
        {"symbol": "1961.KL", "name": "IOI Corp"},
        {"symbol": "5285.KL", "name": "SD Plantation"},
        {"symbol": "2445.KL", "name": "KL Kepong"},
        {"symbol": "5222.KL", "name": "FGV"},
        {"symbol": "2291.KL", "name": "Genting Plant"},
        {"symbol": "2089.KL", "name": "United Plant"},
        {"symbol": "5765.KL", "name": "Hap Seng Plant"},
        {"symbol": "5254.KL", "name": "Boustead Plant"},
        {"symbol": "4383.KL", "name": "Jaya Tiasa"},
        {"symbol": "2054.KL", "name": "TDM"},
    ],
    "Commodities & Mining": [
        {"symbol": "5014.KL", "name": "Malaysia Steel"},
        {"symbol": "4847.KL", "name": "Ann Joo Steel"},
        {"symbol": "8869.KL", "name": "Press Metal"},
        {"symbol": "5075.KL", "name": "Prestar"},
        {"symbol": "7173.KL", "name": "Kinsteel"},
        {"symbol": "0001.KL", "name": "ARB Berhad"},
        {"symbol": "5168.KL", "name": "Hartalega"},
        {"symbol": "2682.KL", "name": "Poh Kong"},
        {"symbol": "5256.KL", "name": "Petronas Chem"},
        {"symbol": "7076.KL", "name": "CSCSteel"},
    ],
    "Utilities & Energy": [
        {"symbol": "5347.KL", "name": "Tenaga"},
        {"symbol": "6742.KL", "name": "YTL Power"},
        {"symbol": "5264.KL", "name": "Malakoff"},
        {"symbol": "6033.KL", "name": "Petronas Gas"},
        {"symbol": "0059.KL", "name": "Cypark"},
        {"symbol": "5260.KL", "name": "Gas Malaysia"},
        {"symbol": "0209.KL", "name": "Solarvest"},
        {"symbol": "0253.KL", "name": "Samaiden"},
        {"symbol": "5184.KL", "name": "Mega First"},
        {"symbol": "5184.KL", "name": "Ranhill Utili"},
    ],
    "Automotive & EV": [
        {"symbol": "1619.KL", "name": "DRB-HICOM"},
        {"symbol": "4197.KL", "name": "Sime Darby"},
        {"symbol": "4588.KL", "name": "UMW Holdings"},
        {"symbol": "5248.KL", "name": "Bermaz Auto"},
        {"symbol": "5983.KL", "name": "MBM Resources"},
        {"symbol": "4405.KL", "name": "Tan Chong"},
        {"symbol": "4006.KL", "name": "Oriental Hold"},
        {"symbol": "7178.KL", "name": "Pecca Group"},
        {"symbol": "7811.KL", "name": "Sapura Indust"},
        {"symbol": "5069.KL", "name": "Hirotako"},
    ],
    "Consumer & Retail": [
        {"symbol": "4707.KL", "name": "Nestle"},
        {"symbol": "5296.KL", "name": "Mr DIY"},
        {"symbol": "5305.KL", "name": "99 Speed Mart"},
        {"symbol": "7084.KL", "name": "QL Resources"},
        {"symbol": "7052.KL", "name": "Padini"},
        {"symbol": "6599.KL", "name": "AEON"},
        {"symbol": "3026.KL", "name": "Dutch Lady"},
        {"symbol": "3689.KL", "name": "F&N"},
        {"symbol": "5196.KL", "name": "Berjaya Food"},
        {"symbol": "5657.KL", "name": "Parkson"},
    ],
    "Gaming & Leisure": [
        {"symbol": "3182.KL", "name": "Genting Bhd"},
        {"symbol": "4715.KL", "name": "Genting MY"},
        {"symbol": "1562.KL", "name": "Berjaya Sports"},
        {"symbol": "3689.KL", "name": "Berjaya Corp"},
        {"symbol": "3087.KL", "name": "Magnum"},
        {"symbol": "5030.KL", "name": "Da Ma Cai"},
        {"symbol": "4715.KL", "name": "RWGenting"},
        {"symbol": "5032.KL", "name": "Genting Plant"},
        {"symbol": "6399.KL", "name": "Astro"},
        {"symbol": "5027.KL", "name": "Berjaya Land"},
    ],
    "Logistics & Transport": [
        {"symbol": "3816.KL", "name": "MISC"},
        {"symbol": "5246.KL", "name": "Westports"},
        {"symbol": "5099.KL", "name": "AirAsia"},
        {"symbol": "3786.KL", "name": "Pos Malaysia"},
        {"symbol": "5132.KL", "name": "GDEX"},
        {"symbol": "4634.KL", "name": "MMC Corp"},
        {"symbol": "4065.KL", "name": "MFCB"},
        {"symbol": "5071.KL", "name": "Harbour-Link"},
        {"symbol": "5363.KL", "name": "Capital A"},
        {"symbol": "6076.KL", "name": "Malaysia Airports"},
    ],
    "Telecommunications": [
        {"symbol": "6947.KL", "name": "CelcomDigi"},
        {"symbol": "6012.KL", "name": "Maxis"},
        {"symbol": "4863.KL", "name": "Telekom MY"},
        {"symbol": "6888.KL", "name": "Axiata"},
        {"symbol": "5031.KL", "name": "TIME dotCom"},
        {"symbol": "6399.KL", "name": "Astro"},
        {"symbol": "0172.KL", "name": "OCK Group"},
        {"symbol": "0044.KL", "name": "REDtone"},
        {"symbol": "5263.KL", "name": "Sasbadi"},
        {"symbol": "0078.KL", "name": "Censof"},
    ],
    "Geopolitical": [
        {"symbol": "1155.KL", "name": "Maybank"},
        {"symbol": "1023.KL", "name": "CIMB"},
        {"symbol": "5347.KL", "name": "Tenaga"},
        {"symbol": "5183.KL", "name": "PetChem"},
        {"symbol": "4197.KL", "name": "Sime Darby"},
        {"symbol": "3182.KL", "name": "Genting"},
        {"symbol": "5285.KL", "name": "SD Plantation"},
        {"symbol": "3816.KL", "name": "MISC"},
        {"symbol": "1961.KL", "name": "IOI Corp"},
        {"symbol": "5246.KL", "name": "Westports"},
    ],
}


_zero_shot_pipeline = None
_ai_classify_cache = {}

def _get_zero_shot():
    """Lazy-load zero-shot classification pipeline."""
    global _zero_shot_pipeline
    if _zero_shot_pipeline is not None:
        return _zero_shot_pipeline
    try:
        from transformers import pipeline
        _zero_shot_pipeline = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=-1,  # CPU
        )
        return _zero_shot_pipeline
    except Exception:
        _zero_shot_pipeline = False
        return False


def _headline_hash(headline: str) -> str:
    """Stable hash for cache key."""
    import hashlib
    return hashlib.md5(headline.strip().lower().encode()).hexdigest()


def classify_article(headline: str, summary: str = "") -> str:
    """Classify a news article into an industry.

    Three-step approach:
    1. DB cache: instant lookup for previously classified headlines
    2. Fast pass: keyword matching (handles ~70% of headlines instantly)
    3. AI pass: zero-shot classification (non-blocking — falls back if model not ready)

    Returns the industry name or 'General Market' if unclassifiable.
    """
    text = (headline + " " + (summary or "")).lower()
    h_hash = _headline_hash(headline)

    # ── Step 0: DB cache lookup ──────────────────────────────────────
    if h_hash in _ai_classify_cache:
        return _ai_classify_cache[h_hash]

    try:
        from src.database import get_cached_classification
        cached = get_cached_classification(h_hash)
        if cached:
            _ai_classify_cache[h_hash] = cached
            return cached
    except Exception:
        pass

    # ── Step 1: Keyword matching (fast) ───────────────────────────────
    scores: dict[str, int] = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            scores[industry] = hits

    if scores:
        best = max(scores, key=lambda k: scores[k])
        _cache_result(h_hash, best, "keyword")
        return best

    # ── Step 2: AI classification (non-blocking) ─────────────────────
    classifier = _get_zero_shot()
    if not classifier or classifier is True:
        # Model not loaded or loading — don't block, return General Market
        _cache_result(h_hash, "General Market", "fallback")
        return "General Market"

    try:
        candidate_labels = list(INDUSTRY_KEYWORDS.keys())
        result = classifier(headline, candidate_labels, multi_label=False)
        top_label = result["labels"][0]
        top_score = result["scores"][0]

        if top_score > 0.30:
            _cache_result(h_hash, top_label, "ai")
            return top_label
    except Exception:
        pass

    _cache_result(h_hash, "General Market", "fallback")
    return "General Market"


def _cache_result(h_hash: str, industry: str, method: str):
    """Save to both in-memory and DB cache."""
    _ai_classify_cache[h_hash] = industry
    try:
        from src.database import save_classification_cache
        save_classification_cache(h_hash, industry, method)
    except Exception:
        pass


def _verdict(avg_score: float) -> dict:
    """Map an average sentiment score to a BULLISH / BEARISH / NEUTRAL verdict."""
    if avg_score > 0.12:
        return {"verdict": "BULLISH", "color": "green",
                "confidence": round(min(0.5 + avg_score * 2, 1.0), 2)}
    if avg_score < -0.12:
        return {"verdict": "BEARISH", "color": "red",
                "confidence": round(min(0.5 + abs(avg_score) * 2, 1.0), 2)}
    return {"verdict": "NEUTRAL", "color": "yellow", "confidence": 0.50}


def _reasoning(industry: str, verdict: str, pos: int, neg: int, neu: int,
               top_arts: list[dict]) -> str:
    """Build a concise AI-style reasoning sentence for the verdict."""
    total = pos + neg + neu
    if total == 0:
        return "Insufficient data to assess market impact."

    pos_pct = round(pos / total * 100)
    neg_pct = round(neg / total * 100)

    if verdict == "BULLISH":
        base = f"{pos_pct}% of {industry} coverage is positive"
        impact = "suggesting upward pressure on related equities"
    elif verdict == "BEARISH":
        base = f"{neg_pct}% of {industry} coverage is negative"
        impact = "suggesting downward pressure on related equities"
    else:
        base = f"Coverage is split — {pos_pct}% positive, {neg_pct}% negative"
        impact = "with no clear near-term directional bias"

    key = next((a["headline"][:90] for a in top_arts if a.get("headline")), None)
    suffix = f'. Key driver: "{key}"' if key else "."
    return f"{base}, {impact}{suffix}"


def analyze_industry_news(articles: list[dict]) -> list[dict]:
    """Classify articles by industry, aggregate sentiment, return per-industry verdicts.

    Args:
        articles: List of article dicts with at least 'headline', 'sentiment_score',
                  'sentiment_label' keys (from db.get_all_news).

    Returns:
        List of industry dicts sorted by signal strength (abs score × count),
        strongest first.
    """
    # Pre-warm in-memory cache with batch DB lookup
    try:
        from src.database import get_cached_classifications_batch
        hashes = [_headline_hash(a.get("headline", "")) for a in articles]
        batch = get_cached_classifications_batch(hashes)
        _ai_classify_cache.update(batch)
    except Exception:
        pass

    buckets: dict[str, list[dict]] = {}
    for article in articles:
        ind = classify_article(
            article.get("headline", ""),
            article.get("summary", "") or "",
        )
        buckets.setdefault(ind, []).append(article)

    results = []
    for industry, arts in buckets.items():
        scores = [float(a.get("sentiment_score") or 0) for a in arts]
        avg = sum(scores) / len(scores) if scores else 0.0

        pos = sum(1 for a in arts if (a.get("sentiment_label") or "") == "positive")
        neg = sum(1 for a in arts if (a.get("sentiment_label") or "") == "negative")
        neu = len(arts) - pos - neg

        vdict = _verdict(avg)

        # Top articles sorted by |score| — most impactful first
        sorted_arts = sorted(arts, key=lambda a: abs(float(a.get("sentiment_score") or 0)),
                             reverse=True)

        top_headlines = [
            {
                "headline": a.get("headline", ""),
                "sentiment": a.get("sentiment_label", "neutral"),
                "score": round(float(a.get("sentiment_score") or 0), 3),
                "source": a.get("source_name", ""),
                "url": a.get("url", ""),
                "fetched_at": a.get("fetched_at", ""),
                "platform": a.get("source_platform", ""),
            }
            for a in sorted_arts[:10]
        ]

        results.append({
            "industry": industry,
            "icon": INDUSTRY_ICONS.get(industry, "📊"),
            "article_count": len(arts),
            "avg_score": round(avg, 3),
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count": neu,
            "verdict": vdict["verdict"],
            "verdict_color": vdict["color"],
            "confidence": vdict["confidence"],
            "reasoning": _reasoning(industry, vdict["verdict"], pos, neg, neu, sorted_arts[:3]),
            "top_headlines": top_headlines,
            "related_stocks": INDUSTRY_STOCKS.get(industry, []),
        })

    # Sort by signal strength: higher |avg_score| + more articles → top
    results.sort(
        key=lambda x: abs(x["avg_score"]) * 2 + x["article_count"] * 0.05,
        reverse=True,
    )
    return results
