"""
Historical Data Collector — downloads 2 years of OHLCV + all technical indicators
for all Bursa stocks + top US stocks. Saves to training_data SQLite table.

Usage:
    python src/data/collect_historical.py              # collect all stocks
    python src/data/collect_historical.py AAPL TSLA    # collect specific stocks
    python src/data/collect_historical.py --us-only     # only US stocks
    python src/data/collect_historical.py --my-only     # only Bursa stocks
"""

import sys
import os
import math
import logging
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pandas as pd
import numpy as np
import yfinance as yf

from src.database import init_db, save_training_batch
from src.data_sources.stock_prices import get_historical_prices
from config.settings import BURSA_INDUSTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Stock Lists ───────────────────────────────────────────────────────────────

# Legacy lists (kept for --us-only / --my-only flags)
US_STOCKS = ["TSLA", "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "META", "SPY", "QQQ", "DIA"]

def get_bursa_symbols() -> list[str]:
    symbols = []
    for ind in BURSA_INDUSTRIES.values():
        for s in ind["stocks"]:
            symbols.append(s["symbol"])
    return symbols

def get_full_universe() -> list[tuple[str, str]]:
    """Get the full stock universe (S&P 500 + Bursa + indices).
    Returns list of (symbol, market)."""
    try:
        from config.stock_universe import get_all_stocks
        return [(s["symbol"], s["market"]) for s in get_all_stocks()]
    except ImportError:
        # Fallback to legacy lists
        return ([(s, "MY") for s in get_bursa_symbols()] +
                [(s, "US") for s in US_STOCKS])

# ── Market Index Data (for context columns) ──────────────────────────────────

def _load_index_series(symbol: str, period: str = "10y") -> pd.Series:
    """Load closing prices for a market index, indexed by date string."""
    try:
        df = yf.Ticker(symbol).history(period=period)
        if df.empty:
            return pd.Series(dtype=float)
        s = df["Close"]
        s.index = s.index.strftime("%Y-%m-%d")
        return s
    except Exception:
        return pd.Series(dtype=float)


def _load_return_series(symbol: str, period: str = "10y") -> pd.Series:
    """Load daily returns for an ETF, indexed by date string."""
    try:
        df = yf.Ticker(symbol).history(period=period)
        if df.empty:
            return pd.Series(dtype=float)
        s = df["Close"].pct_change() * 100
        s.index = s.index.strftime("%Y-%m-%d")
        return s
    except Exception:
        return pd.Series(dtype=float)


# GICS Sector → Sector ETF mapping
GICS_SECTOR_ETF = {
    "Information Technology": "XLK",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
}


def _build_symbol_sector_map() -> dict[str, str]:
    """Map stock symbol → GICS Sector from S&P 500 CSV."""
    mapping = {}
    try:
        csv_path = os.path.join("data", "sp500_tickers.csv")
        if os.path.exists(csv_path):
            import csv as csvmod
            with open(csv_path, encoding="utf-8") as f:
                reader = csvmod.DictReader(f)
                for row in reader:
                    sym = row.get("Symbol", "").strip()
                    sector = row.get("GICS Sector", "").strip()
                    if sym and sector:
                        mapping[sym] = sector
    except Exception:
        pass
    return mapping


def _get_sector_etf_return(symbol: str, date_str: str,
                           sector_etf_returns: dict, symbol_sector_map: dict) -> float:
    """Look up the sector ETF daily return for a stock on a given date."""
    if not sector_etf_returns or not symbol_sector_map:
        return None
    gics_sector = symbol_sector_map.get(symbol)
    if not gics_sector:
        return None
    etf = GICS_SECTOR_ETF.get(gics_sector)
    if not etf or etf not in sector_etf_returns:
        return None
    return sector_etf_returns[etf].get(date_str)


# ── Core Collection ──────────────────────────────────────────────────────────

def _safe_float(v):
    """Convert to Python float, handling NaN/numpy types."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 6)
    except (TypeError, ValueError):
        return None

def _safe_int(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


def collect_stock(symbol: str, index_series: pd.Series, vix_series: pd.Series,
                  period: str = "10y",
                  tnx_series: pd.Series = None, irx_series: pd.Series = None,
                  dxy_series: pd.Series = None,
                  oil_series: pd.Series = None, gold_series: pd.Series = None,
                  copper_series: pd.Series = None,
                  sector_etf_returns: dict = None,
                  symbol_sector_map: dict = None) -> int:
    """Collect historical data for one stock. Returns number of rows saved."""
    try:
        df = get_historical_prices(symbol, period=period)
    except Exception as e:
        log.warning(f"  {symbol}: failed to fetch — {e}")
        return 0

    if df.empty or len(df) < 10:
        log.warning(f"  {symbol}: insufficient data ({len(df)} rows)")
        return 0

    # Calculate target labels (future price changes)
    close = df["Close"]
    df["_price_change_1d"] = close.pct_change(periods=1).shift(-1) * 100  # next-day %
    df["_price_change_5d"] = close.pct_change(periods=5).shift(-5) * 100  # 5-day %

    dates = df.index.strftime("%Y-%m-%d").tolist()
    rows = []

    for i, date_str in enumerate(dates):
        row = {
            "symbol": symbol,
            "date": date_str,
            "open":   _safe_float(df["Open"].iloc[i]),
            "high":   _safe_float(df["High"].iloc[i]),
            "low":    _safe_float(df["Low"].iloc[i]),
            "close":  _safe_float(df["Close"].iloc[i]),
            "volume": _safe_int(df["Volume"].iloc[i]),
            # Moving averages
            "sma_20": _safe_float(df["SMA_20"].iloc[i]),
            "sma_50": _safe_float(df["SMA_50"].iloc[i]),
            "ema_9":  _safe_float(df["EMA_9"].iloc[i]),
            "ema_12": _safe_float(df["EMA_12"].iloc[i]),
            "ema_21": _safe_float(df["EMA_21"].iloc[i]),
            "ema_26": _safe_float(df["EMA_26"].iloc[i]),
            # MACD
            "macd":        _safe_float(df["MACD"].iloc[i]),
            "signal_line": _safe_float(df["Signal_Line"].iloc[i]),
            "macd_hist":   _safe_float(df["MACD_Hist"].iloc[i]),
            # Oscillators
            "rsi":        _safe_float(df["RSI"].iloc[i]),
            "stoch_k":    _safe_float(df["Stoch_K"].iloc[i]),
            "stoch_d":    _safe_float(df["Stoch_D"].iloc[i]),
            "williams_r": _safe_float(df["Williams_R"].iloc[i]),
            # Bollinger
            "bb_upper": _safe_float(df["BB_Upper"].iloc[i]),
            "bb_lower": _safe_float(df["BB_Lower"].iloc[i]),
            # Trend
            "adx":      _safe_float(df["ADX"].iloc[i]),
            "plus_di":  _safe_float(df["Plus_DI"].iloc[i]),
            "minus_di": _safe_float(df["Minus_DI"].iloc[i]),
            # Volume & Volatility
            "atr":        _safe_float(df["ATR"].iloc[i]),
            "obv":        _safe_float(df["OBV"].iloc[i]),
            "vwap":       _safe_float(df["VWAP"].iloc[i]),
            "cci":        _safe_float(df["CCI"].iloc[i]),
            "psar":       _safe_float(df["PSAR"].iloc[i]),
            # Ichimoku
            "ichi_tenkan": _safe_float(df["Ichi_Tenkan"].iloc[i]),
            "ichi_kijun":  _safe_float(df["Ichi_Kijun"].iloc[i]),
            "ichi_span_a": _safe_float(df["Ichi_SpanA"].iloc[i]),
            "ichi_span_b": _safe_float(df["Ichi_SpanB"].iloc[i]),
            # Misc
            "volatility":   _safe_float(df["Volatility"].iloc[i]),
            "daily_return": _safe_float(df["Daily_Return"].iloc[i]),
            # Market context
            "market_index_close": _safe_float(index_series.get(date_str)),
            "vix_close":          _safe_float(vix_series.get(date_str)),
            # Targets
            "price_change_1d": _safe_float(df["_price_change_1d"].iloc[i]),
            "price_change_5d": _safe_float(df["_price_change_5d"].iloc[i]),
            # Treasury yields & spread
            "treasury_10y": _safe_float(tnx_series.get(date_str) if tnx_series is not None else None),
            "treasury_2y": _safe_float(irx_series.get(date_str) if irx_series is not None else None),
            "yield_spread": _safe_float(
                ((tnx_series.get(date_str) or 0) - (irx_series.get(date_str) or 0))
                if tnx_series is not None and irx_series is not None else None
            ),
            # Dollar index
            "dxy_close": _safe_float(dxy_series.get(date_str) if dxy_series is not None else None),
            # Sector ETF return
            "sector_etf_return": _safe_float(
                _get_sector_etf_return(symbol, date_str, sector_etf_returns, symbol_sector_map)
            ),
            # Cross-asset prices
            "oil_close": _safe_float(oil_series.get(date_str) if oil_series is not None else None),
            "gold_close": _safe_float(gold_series.get(date_str) if gold_series is not None else None),
            "copper_close": _safe_float(copper_series.get(date_str) if copper_series is not None else None),
        }
        rows.append(row)

    save_training_batch(rows)
    return len(rows)


def run(symbols: list[str] = None, us_only=False, my_only=False):
    """Main entry point."""
    init_db()

    # Determine which stocks to collect
    if symbols:
        stock_list = [(s, "MY" if s.endswith(".KL") else "US") for s in symbols]
    elif us_only:
        stock_list = [(s, "US") for s in US_STOCKS]
    elif my_only:
        stock_list = [(s, "MY") for s in get_bursa_symbols()]
    else:
        # Full universe: S&P 500 + Bursa + Indices
        stock_list = get_full_universe()

    total = len(stock_list)
    log.info(f"Collecting 10-year historical data for {total} stocks...")

    # Pre-load market indices (used as context columns)
    log.info("Loading market indices (SPY, ^KLSE, ^VIX)...")
    spy_series = _load_index_series("SPY", "10y")
    klci_series = _load_index_series("^KLSE", "10y")
    vix_series = _load_index_series("^VIX", "10y")
    log.info(f"  SPY: {len(spy_series)} days, KLCI: {len(klci_series)} days, VIX: {len(vix_series)} days")

    # Treasury yields
    log.info("Loading treasury yields (^TNX, ^IRX)...")
    tnx_series = _load_index_series("^TNX", "10y")   # 10-year yield
    irx_series = _load_index_series("^IRX", "10y")   # 13-week T-bill rate
    log.info(f"  10Y: {len(tnx_series)} days, 13W: {len(irx_series)} days")

    # Dollar index
    log.info("Loading dollar index (DX-Y.NYB / UUP fallback)...")
    dxy_series = _load_index_series("DX-Y.NYB", "10y")
    if dxy_series.empty:
        log.info("  DX-Y.NYB unavailable, trying UUP ETF as proxy...")
        dxy_series = _load_index_series("UUP", "10y")
    log.info(f"  DXY: {len(dxy_series)} days")

    # Cross-asset prices
    log.info("Loading cross-asset prices (oil, gold, copper)...")
    oil_series = _load_index_series("CL=F", "10y")    # Crude oil futures
    gold_series = _load_index_series("GC=F", "10y")   # Gold futures
    copper_series = _load_index_series("HG=F", "10y") # Copper futures
    log.info(f"  Oil: {len(oil_series)}, Gold: {len(gold_series)}, Copper: {len(copper_series)} days")

    # Sector ETF daily returns
    log.info("Loading sector ETF returns...")
    sector_etf_returns = {}
    for etf in set(GICS_SECTOR_ETF.values()):
        ret = _load_return_series(etf, "10y")
        if not ret.empty:
            sector_etf_returns[etf] = ret
    log.info(f"  Loaded {len(sector_etf_returns)} sector ETFs")

    # Symbol → GICS Sector mapping
    symbol_sector_map = _build_symbol_sector_map()

    total_rows = 0
    ok = 0
    for i, (symbol, market) in enumerate(stock_list, 1):
        log.info(f"Processing {i}/{total}: {symbol} ({market})")
        index_series = klci_series if market == "MY" else spy_series
        count = collect_stock(
            symbol, index_series, vix_series,
            tnx_series=tnx_series, irx_series=irx_series,
            dxy_series=dxy_series,
            oil_series=oil_series, gold_series=gold_series,
            copper_series=copper_series,
            sector_etf_returns=sector_etf_returns,
            symbol_sector_map=symbol_sector_map,
        )
        if count > 0:
            ok += 1
            total_rows += count
            log.info(f"  {symbol}: {count} rows saved")
        # Small delay to be nice to yfinance
        if i % 10 == 0:
            import time
            time.sleep(1)

    log.info(f"\nDone — {ok}/{total} stocks collected, {total_rows} total rows")


if __name__ == "__main__":
    args = sys.argv[1:]
    us_only = "--us-only" in args
    my_only = "--my-only" in args
    symbols = [a for a in args if not a.startswith("--")]
    run(symbols=symbols or None, us_only=us_only, my_only=my_only)
