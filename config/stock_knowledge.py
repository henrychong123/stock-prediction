"""
Bursa Malaysia Stock Knowledge Graph — researched relationships between
80 Bursa-listed companies.

Sources: Annual reports, Bursa filings, institutional disclosures.
Last updated: 2026-04-10

This is the SINGLE SOURCE OF TRUTH for stock relationships.
Used by the catalyst system to expand stock picks to related companies.
"""

# ── Petronas Group (unlisted parent) ─────────────────────────────────────────
PETRONAS_SUBSIDIARIES = ["5183.KL", "6033.KL", "5681.KL", "3816.KL"]

# ── Parent-Subsidiary Relationships ──────────────────────────────────────────
PARENT_CHILD = {
    # Parent → [children]
    "1163.KL": ["5819.KL"],                  # Hong Leong Financial → Hong Leong Bank (~62%)
    "6888.KL": ["6947.KL"],                  # Axiata → CelcomDigi (~33%, co-control with Telenor)
}

# Siblings (same unlisted parent)
SIBLINGS = {
    "5183.KL": ["6033.KL", "5681.KL", "3816.KL"],   # Petronas siblings
    "6033.KL": ["5183.KL", "5681.KL", "3816.KL"],
    "5681.KL": ["5183.KL", "6033.KL", "3816.KL"],
    "3816.KL": ["5183.KL", "6033.KL", "5681.KL"],
    "5819.KL": ["1163.KL"],                           # HLB ↔ HLFG
    "1163.KL": ["5819.KL"],
}

# ── Supplier-Customer Relationships ──────────────────────────────────────────
SUPPLIERS = {
    # stock → [its suppliers]
    "5347.KL": ["6033.KL", "6742.KL"],       # TNB buys gas from PetGas, power from YTL Power
    "8869.KL": ["5347.KL"],                  # Press Metal buys electricity from TNB
    "4707.KL": ["5285.KL", "2445.KL", "1961.KL"],  # Nestle buys palm oil from plantations
    "6947.KL": ["4863.KL"],                  # CelcomDigi uses TM wholesale broadband
    "6012.KL": ["4863.KL"],                  # Maxis uses TM wholesale broadband
    "5183.KL": ["5218.KL", "7277.KL", "7293.KL", "5210.KL", "3816.KL"],  # Petronas uses O&G contractors
    "6033.KL": ["3816.KL"],                  # Petronas Gas uses MISC shipping
}

CUSTOMERS = {
    # stock → [its customers]
    "6033.KL": ["5347.KL"],                  # PetGas supplies gas to TNB
    "5347.KL": ["8869.KL"],                  # TNB supplies electricity to Press Metal
    "4863.KL": ["6947.KL", "6012.KL"],       # TM provides infra to telcos
    "6742.KL": ["5347.KL"],                  # YTL Power sells to TNB grid
    "5285.KL": ["4707.KL"],                  # Sime Darby Palm → Nestle
    "2445.KL": ["4707.KL"],                  # KLK → Nestle
    "1961.KL": ["4707.KL"],                  # IOI → Nestle/food manufacturers
    "5218.KL": ["5183.KL", "6033.KL"],       # Sapura services Petronas group
    "7277.KL": ["5183.KL"],                  # Dialog services Petronas
    "7293.KL": ["5183.KL"],                  # Yinson FPSO for Petronas
    "5210.KL": ["5183.KL"],                  # Bumi Armada services Petronas
    "3816.KL": ["5183.KL", "6033.KL"],       # MISC ships for Petronas group
}

# ── Competitors (same industry, highly correlated) ───────────────────────────
COMPETITORS = {
    "5168.KL": ["7113.KL"],                  # Hartalega ↔ Top Glove (gloves)
    "7113.KL": ["5168.KL"],
    "7293.KL": ["5210.KL"],                  # Yinson ↔ Bumi Armada (FPSO)
    "5210.KL": ["7293.KL"],
    "5218.KL": ["7277.KL"],                  # Sapura ↔ Dialog (O&G services)
    "7277.KL": ["5218.KL"],
    "6947.KL": ["6012.KL"],                  # CelcomDigi ↔ Maxis (mobile)
    "6012.KL": ["6947.KL"],
    "5285.KL": ["2445.KL", "1961.KL"],       # Plantation peers
    "2445.KL": ["5285.KL", "1961.KL"],
    "1961.KL": ["5285.KL", "2445.KL"],
    "1155.KL": ["1295.KL", "1023.KL", "5819.KL", "1066.KL", "1015.KL"],  # Banking peers
    "1295.KL": ["1155.KL", "1023.KL", "5819.KL", "1066.KL", "1015.KL"],
    "1023.KL": ["1155.KL", "1295.KL", "5819.KL", "1066.KL", "1015.KL"],
    "5819.KL": ["1155.KL", "1295.KL", "1023.KL", "1066.KL", "1015.KL"],
    "1066.KL": ["1155.KL", "1295.KL", "1023.KL", "5819.KL", "1015.KL"],
    "1015.KL": ["1155.KL", "1295.KL", "1023.KL", "5819.KL", "1066.KL"],
}

# ── Commodity Exposure ───────────────────────────────────────────────────────
COMMODITY_EXPOSURE = {
    "CPO": ["5285.KL", "2445.KL", "1961.KL"],                  # crude palm oil
    "BRENT": ["5183.KL", "6033.KL", "5681.KL", "5218.KL",      # Brent crude
              "7277.KL", "7293.KL", "5210.KL", "3816.KL"],
    "ALUMINUM": ["8869.KL"],                                      # LME aluminum
    "NITRILE_LATEX": ["5168.KL", "7113.KL"],                     # rubber/nitrile
    "NATURAL_GAS": ["6033.KL", "5347.KL"],                       # gas prices
    "USD_MYR": ["5168.KL", "7113.KL", "8869.KL", "5183.KL"],   # USD earners
}

# ── Institutional Cross-Holdings (GLC links) ─────────────────────────────────
GLC_HOLDINGS = {
    "KHAZANAH": ["1023.KL", "4863.KL", "6888.KL", "5225.KL", "5347.KL", "5185.KL"],
    "PNB": ["1155.KL", "1023.KL", "5285.KL", "5347.KL"],
    "EPF": ["1155.KL", "1295.KL", "1023.KL", "1066.KL", "1015.KL", "5347.KL",
            "5225.KL", "6947.KL", "5183.KL", "5285.KL"],
    "PETRONAS": PETRONAS_SUBSIDIARIES,
}


# ── API: Get all related stocks for a symbol ─────────────────────────────────

def get_related_stocks(symbol: str) -> dict[str, list[str]]:
    """Get all related stocks grouped by relationship type.

    Returns:
        {
            "siblings": ["5681.KL", ...],
            "suppliers": ["5218.KL", ...],
            "customers": ["5347.KL", ...],
            "competitors": ["7113.KL", ...],
            "same_glc": ["1023.KL", ...],
        }
    """
    result = {
        "siblings": SIBLINGS.get(symbol, []),
        "suppliers": SUPPLIERS.get(symbol, []),
        "customers": CUSTOMERS.get(symbol, []),
        "competitors": COMPETITORS.get(symbol, []),
        "same_glc": [],
    }

    # Find GLC siblings (same institutional owner)
    for glc, holdings in GLC_HOLDINGS.items():
        if symbol in holdings:
            for s in holdings:
                if s != symbol and s not in result["same_glc"]:
                    result["same_glc"].append(s)

    return result


def get_all_related(symbol: str) -> list[tuple[str, str, float]]:
    """Get all related stocks as a flat list with relationship type and weight.

    Returns: [(symbol, relationship, discount_factor), ...]
    """
    relations = get_related_stocks(symbol)
    result = []
    seen = set()

    # Siblings (highest correlation — same parent)
    for s in relations["siblings"]:
        if s not in seen:
            result.append((s, "sibling", 0.85))
            seen.add(s)

    # Suppliers (direct business dependency)
    for s in relations["suppliers"]:
        if s not in seen:
            result.append((s, "supplier", 0.65))
            seen.add(s)

    # Customers (direct business dependency)
    for s in relations["customers"]:
        if s not in seen:
            result.append((s, "customer", 0.65))
            seen.add(s)

    # Competitors (same industry, correlated)
    for s in relations["competitors"]:
        if s not in seen:
            result.append((s, "competitor", 0.50))
            seen.add(s)

    # Same GLC owner (weakest but still correlated)
    for s in relations["same_glc"]:
        if s not in seen:
            result.append((s, "same_glc", 0.30))
            seen.add(s)

    return result


def get_commodity_stocks(commodity: str) -> list[str]:
    """Get stocks exposed to a commodity."""
    return COMMODITY_EXPOSURE.get(commodity.upper(), [])
