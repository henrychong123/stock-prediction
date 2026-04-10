"""Tests for src/analysis/industry_classifier.py – keyword and AI classification."""

from src.analysis.industry_classifier import (
    classify_article, analyze_industry_news, INDUSTRY_KEYWORDS, INDUSTRY_ICONS,
)


class TestClassifyArticle:
    def test_oil_keyword(self):
        assert classify_article("Crude oil prices surge on OPEC cuts") == "Oil & Gas"

    def test_tech_keyword(self):
        assert classify_article("NVIDIA launches new AI chip") == "Technology"

    def test_banking_keyword(self):
        assert classify_article("Federal Reserve raises interest rate") == "Banking & Finance"

    def test_healthcare_keyword(self):
        assert classify_article("FDA approves new cancer drug treatment") == "Healthcare"

    def test_property_keyword(self):
        assert classify_article("Real estate housing market construction slows") == "Property & Construction"

    def test_plantation_keyword(self):
        assert classify_article("Palm oil prices rise on CPO demand") == "Plantation & Agriculture"

    def test_general_market_fallback(self):
        """Unclassifiable headline falls back to General Market."""
        import src.analysis.industry_classifier as ic
        ic._zero_shot_pipeline = False
        result = classify_article("Zylox buys Qarnov in unspecified deal")
        assert result == "General Market"
        ic._zero_shot_pipeline = None

    def test_summary_used_for_classification(self):
        result = classify_article("Breaking news", summary="crude oil petroleum prices")
        assert result == "Oil & Gas"

    def test_automotive(self):
        assert classify_article("Tesla electric vehicle EV sales up") == "Automotive & EV"

    def test_gaming(self):
        assert classify_article("Genting casino resort gaming revenue") == "Gaming & Leisure"

    def test_telecom(self):
        assert classify_article("5G telco axiata celcomdigi network") == "Telecommunications"


class TestIndustryKeywordsStructure:
    def test_all_industries_have_keywords(self):
        for industry, keywords in INDUSTRY_KEYWORDS.items():
            assert len(keywords) > 0, f"{industry} has no keywords"

    def test_all_industries_have_icons(self):
        for industry in INDUSTRY_KEYWORDS:
            assert industry in INDUSTRY_ICONS, f"{industry} has no icon"


class TestAnalyzeIndustryNews:
    def test_basic_analysis(self):
        articles = [
            {"headline": "Oil prices surge on OPEC", "sentiment_score": 0.5,
             "sentiment_label": "positive", "summary": ""},
            {"headline": "Oil refinery expansion crude", "sentiment_score": 0.3,
             "sentiment_label": "positive", "summary": ""},
            {"headline": "Tech AI chip semiconductor", "sentiment_score": -0.4,
             "sentiment_label": "negative", "summary": ""},
        ]
        result = analyze_industry_news(articles)
        assert isinstance(result, list)
        assert len(result) >= 2

        industries = {r["industry"] for r in result}
        assert "Oil & Gas" in industries
        assert "Technology" in industries

    def test_verdict_structure(self):
        articles = [
            {"headline": "Oil crude petroleum surge", "sentiment_score": 0.6,
             "sentiment_label": "positive", "summary": ""},
        ]
        result = analyze_industry_news(articles)
        entry = result[0]
        assert "verdict" in entry
        assert entry["verdict"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert "confidence" in entry
        assert "reasoning" in entry
        assert "top_headlines" in entry
        assert "related_stocks" in entry

    def test_empty_articles(self):
        result = analyze_industry_news([])
        assert result == []

    def test_sentiment_breakdown(self):
        articles = [
            {"headline": "Bank loan interest rate", "sentiment_score": 0.5,
             "sentiment_label": "positive", "summary": ""},
            {"headline": "Bank mortgage finance credit", "sentiment_score": -0.3,
             "sentiment_label": "negative", "summary": ""},
            {"headline": "Banking sector debt inflation", "sentiment_score": 0.0,
             "sentiment_label": "neutral", "summary": ""},
        ]
        result = analyze_industry_news(articles)
        banking = next(r for r in result if r["industry"] == "Banking & Finance")
        assert banking["positive_count"] == 1
        assert banking["negative_count"] == 1
        assert banking["neutral_count"] == 1
        assert banking["article_count"] == 3
