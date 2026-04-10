"""Tests for src/analysis/sector_analysis.py – sector definitions and lookups."""

from src.analysis.sector_analysis import (
    US_SECTORS, MY_SECTORS, get_sectors, get_sector_for_symbol,
)


class TestSectorDefinitions:
    def test_us_sectors_count(self):
        assert len(US_SECTORS) == 11  # 11 GICS sectors

    def test_my_sectors_count(self):
        assert len(MY_SECTORS) == 9  # 9 Malaysian sectors

    def test_get_sectors_us(self):
        sectors = get_sectors("US")
        assert "Technology" in sectors
        assert sectors["Technology"]["etf"] == "XLK"

    def test_get_sectors_my(self):
        sectors = get_sectors("MY")
        assert "Banking & Finance" in sectors
        assert sectors["Banking & Finance"]["etf"] == "1155.KL"

    def test_each_sector_has_required_keys(self):
        for name, info in {**US_SECTORS, **MY_SECTORS}.items():
            assert "description" in info, f"{name} missing description"
            assert "symbols" in info, f"{name} missing symbols"
            assert "etf" in info, f"{name} missing etf"
            assert len(info["symbols"]) > 0, f"{name} has no symbols"


class TestSectorLookup:
    def test_find_us_stock(self):
        assert get_sector_for_symbol("AAPL") == "Technology"
        assert get_sector_for_symbol("JPM") == "Financials"
        assert get_sector_for_symbol("XOM") == "Energy"

    def test_find_my_stock(self):
        assert get_sector_for_symbol("1155.KL") == "Banking & Finance"
        assert get_sector_for_symbol("5285.KL") == "Plantation & Agriculture"

    def test_unknown_symbol(self):
        assert get_sector_for_symbol("ZZZZZ") is None
