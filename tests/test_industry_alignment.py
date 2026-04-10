"""Guard test: ensures all industry lists across the codebase use canonical names.

If this test fails, it means a module introduced an industry name that doesn't
match the canonical list in config/industries.py. Fix it there, not here.
"""

from config.industries import CANONICAL_INDUSTRIES, ALL_NEWS_CATEGORIES, GDELT_KEYWORDS


class TestIndustryAlignment:
    def test_bursa_industries_use_canonical_names(self):
        from config.settings import BURSA_INDUSTRIES
        for name in BURSA_INDUSTRIES:
            assert name in CANONICAL_INDUSTRIES, (
                f"BURSA_INDUSTRIES key '{name}' is not a canonical industry name"
            )

    def test_my_sectors_use_canonical_names(self):
        from src.analysis.sector_analysis import MY_SECTORS
        for name in MY_SECTORS:
            assert name in CANONICAL_INDUSTRIES, (
                f"MY_SECTORS key '{name}' is not a canonical industry name"
            )

    def test_classifier_keywords_use_canonical_names(self):
        from src.analysis.industry_classifier import INDUSTRY_KEYWORDS
        for name in INDUSTRY_KEYWORDS:
            assert name in ALL_NEWS_CATEGORIES, (
                f"Classifier INDUSTRY_KEYWORDS key '{name}' is not a canonical category"
            )

    def test_gdelt_keywords_use_canonical_names(self):
        for name in GDELT_KEYWORDS:
            assert name in ALL_NEWS_CATEGORIES, (
                f"GDELT_KEYWORDS key '{name}' is not a canonical category"
            )

    def test_classifier_stocks_use_canonical_names(self):
        from src.analysis.industry_classifier import INDUSTRY_STOCKS
        for name in INDUSTRY_STOCKS:
            assert name in ALL_NEWS_CATEGORIES, (
                f"INDUSTRY_STOCKS key '{name}' is not a canonical category"
            )

    def test_all_canonical_have_icons(self):
        from config.industries import INDUSTRY_ICONS
        for name in ALL_NEWS_CATEGORIES:
            assert name in INDUSTRY_ICONS, (
                f"Category '{name}' is missing an icon in INDUSTRY_ICONS"
            )
