"""
Backtesting engine to validate prediction accuracy.

Tests our signal-based predictions against actual historical price movements.
Answers the question: "If we followed these signals, would we have made money?"
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from src.data_sources.stock_prices import get_historical_prices, get_technical_signal
from config.settings import SIGNAL_WEIGHTS


@dataclass
class BacktestResult:
    symbol: str
    period: str
    total_signals: int
    correct_signals: int
    accuracy: float
    total_return: float       # % return if following signals
    buy_hold_return: float    # % return of just holding
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    trades: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "period": self.period,
            "total_signals": self.total_signals,
            "correct_signals": self.correct_signals,
            "accuracy": round(self.accuracy * 100, 1),
            "total_return": round(self.total_return, 2),
            "buy_hold_return": round(self.buy_hold_return, 2),
            "alpha": round(self.total_return - self.buy_hold_return, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown": round(self.max_drawdown, 2),
            "win_rate": round(self.win_rate * 100, 1),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "trade_count": len(self.trades),
        }


def backtest_technical(symbol: str, period: str = "1y", hold_days: int = 5) -> BacktestResult:
    """Backtest technical signals against actual price movements.

    Simulates: when our technical analysis says "bullish", does the stock
    actually go up over the next N days?

    Args:
        symbol: Stock ticker
        period: Backtest period (6mo, 1y, 2y)
        hold_days: Days to hold after each signal

    Returns:
        BacktestResult with accuracy, returns, and risk metrics
    """
    df = get_historical_prices(symbol, period=period)
    if df.empty or len(df) < 60:
        return BacktestResult(
            symbol=symbol, period=period, total_signals=0,
            correct_signals=0, accuracy=0, total_return=0,
            buy_hold_return=0, sharpe_ratio=0, max_drawdown=0,
            win_rate=0, avg_win=0, avg_loss=0,
        )

    trades = []
    portfolio_value = 10000.0
    peak_value = portfolio_value
    max_dd = 0
    values = [portfolio_value]

    # Generate signals at each point in time
    for i in range(50, len(df) - hold_days, hold_days):
        window = df.iloc[:i+1]
        latest = window.iloc[-1]

        # Calculate signal from indicators at this point
        score = 0
        if latest["MACD"] > latest["Signal_Line"]:
            score += 0.25
        else:
            score -= 0.25

        if latest["RSI"] < 30:
            score += 0.25
        elif latest["RSI"] > 70:
            score -= 0.25

        if latest["SMA_20"] > latest["SMA_50"]:
            score += 0.25
        else:
            score -= 0.25

        if latest["Close"] < latest["BB_Lower"]:
            score += 0.25
        elif latest["Close"] > latest["BB_Upper"]:
            score -= 0.25

        # Determine action
        if score > 0.15:
            action = "BUY"
        elif score < -0.15:
            action = "SELL"
        else:
            action = "HOLD"

        if action == "HOLD":
            continue

        # Actual outcome
        entry_price = df["Close"].iloc[i]
        exit_price = df["Close"].iloc[i + hold_days]
        pct_change = (exit_price - entry_price) / entry_price * 100

        # Was the prediction correct?
        if action == "BUY":
            trade_return = pct_change
            correct = pct_change > 0
        else:  # SELL
            trade_return = -pct_change  # Short position profits when price drops
            correct = pct_change < 0

        portfolio_value *= (1 + trade_return / 100)
        peak_value = max(peak_value, portfolio_value)
        drawdown = (peak_value - portfolio_value) / peak_value * 100
        max_dd = max(max_dd, drawdown)
        values.append(portfolio_value)

        trades.append({
            "date": df.index[i].strftime("%Y-%m-%d"),
            "action": action,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round(trade_return, 2),
            "correct": correct,
            "signal_score": round(score, 3),
        })

    if not trades:
        buy_hold = ((df["Close"].iloc[-1] - df["Close"].iloc[0]) / df["Close"].iloc[0]) * 100
        return BacktestResult(
            symbol=symbol, period=period, total_signals=0,
            correct_signals=0, accuracy=0, total_return=0,
            buy_hold_return=round(buy_hold, 2), sharpe_ratio=0,
            max_drawdown=0, win_rate=0, avg_win=0, avg_loss=0,
        )

    # Calculate metrics
    correct_count = sum(1 for t in trades if t["correct"])
    wins = [t["return_pct"] for t in trades if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in trades if t["return_pct"] <= 0]
    returns = [t["return_pct"] for t in trades]

    total_return = (portfolio_value / 10000 - 1) * 100
    buy_hold = ((df["Close"].iloc[-1] - df["Close"].iloc[0]) / df["Close"].iloc[0]) * 100

    # Sharpe ratio (annualized)
    if len(returns) > 1 and np.std(returns) > 0:
        avg_ret = np.mean(returns)
        std_ret = np.std(returns)
        trades_per_year = 252 / hold_days
        sharpe = (avg_ret / std_ret) * np.sqrt(trades_per_year)
    else:
        sharpe = 0

    return BacktestResult(
        symbol=symbol,
        period=period,
        total_signals=len(trades),
        correct_signals=correct_count,
        accuracy=correct_count / len(trades) if trades else 0,
        total_return=total_return,
        buy_hold_return=buy_hold,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        win_rate=correct_count / len(trades) if trades else 0,
        avg_win=np.mean(wins) if wins else 0,
        avg_loss=np.mean(losses) if losses else 0,
        trades=trades,
    )
