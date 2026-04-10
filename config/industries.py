"""
Canonical industry definitions for the stock-prediction project.

This is the SINGLE SOURCE OF TRUTH for industry names, icons, and GDELT keywords.
All modules should import industry names from here to prevent drift.
"""

# Core stock-market industries (used for sector analysis, stock grouping, GDELT, classification)
CANONICAL_INDUSTRIES: list[str] = [
    "Banking & Finance",
    "Technology",
    "Oil & Gas",
    "Utilities & Energy",
    "Healthcare",
    "Plantation & Agriculture",
    "Consumer & Retail",
    "Gaming & Leisure",
    "Telecommunications",
    "Property & Construction",
    "Commodities & Mining",
    "Automotive & EV",
    "Logistics & Transport",
    "Industrial & Manufacturing",
]

# Meta-categories: used for news/GDELT classification but NOT stock sectors
NEWS_META_CATEGORIES: list[str] = [
    "Geopolitical",
    "Malaysia Economy",
    "Global Markets",
    "General Market",
]

# All classifiable categories (industries + meta)
ALL_NEWS_CATEGORIES: list[str] = CANONICAL_INDUSTRIES + NEWS_META_CATEGORIES

# Icons for each industry/category
INDUSTRY_ICONS: dict[str, str] = {
    "Banking & Finance":         "🏦",
    "Technology":                "💻",
    "Oil & Gas":                 "🛢️",
    "Utilities & Energy":        "⚡",
    "Healthcare":                "⚕️",
    "Plantation & Agriculture":  "🌿",
    "Consumer & Retail":         "🛍️",
    "Gaming & Leisure":          "🎰",
    "Telecommunications":        "📡",
    "Property & Construction":   "🏗️",
    "Commodities & Mining":      "⛏️",
    "Automotive & EV":           "🚗",
    "Logistics & Transport":     "🚢",
    "Industrial & Manufacturing": "🏭",
    "Geopolitical":              "🌍",
    "Malaysia Economy":          "🇲🇾",
    "Global Markets":            "📊",
    "General Market":            "📊",
}

# GDELT search keywords per industry (for historical tone backfill)
GDELT_KEYWORDS: dict[str, list[str]] = {
    "Oil & Gas":                ["oil price", "crude oil", "OPEC", "petroleum"],
    "Technology":               ["technology stocks", "semiconductor", "AI artificial intelligence"],
    "Banking & Finance":        ["banking sector", "interest rate", "federal reserve", "financial markets"],
    "Healthcare":               ["healthcare stocks", "pharmaceutical", "biotech"],
    "Property & Construction":  ["real estate market", "property prices", "construction"],
    "Plantation & Agriculture": ["palm oil price", "plantation", "agriculture commodities"],
    "Commodities & Mining":     ["gold price", "mining stocks", "commodities market"],
    "Utilities & Energy":       ["energy stocks", "renewable energy", "electricity"],
    "Automotive & EV":          ["electric vehicle", "automotive industry", "tesla"],
    "Consumer & Retail":        ["consumer spending", "retail sales", "consumer sentiment"],
    "Gaming & Leisure":         ["gaming industry", "casino", "leisure stocks"],
    "Telecommunications":       ["telecom industry", "5G", "telecommunications"],
    "Malaysia Economy":         ["Malaysia economy", "ringgit", "Bank Negara"],
    "Global Markets":           ["stock market", "global economy", "trade war"],
}

# Old name -> canonical name (for DB migration and backward compat)
INDUSTRY_NAME_MIGRATION: dict[str, str] = {
    "Energy & Utilities": "Utilities & Energy",
    "Utilities & Power":  "Utilities & Energy",
    "Plantation":         "Plantation & Agriculture",
    "Retail & Consumer":  "Consumer & Retail",
}
