"""
Vectorbt-based research backtesting.
This module is isolated from the live trading loop and is intended for offline strategy analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import os

import pandas as pd

try:
    import vectorbt as vbt  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    vbt = None

from app.schemas.signal import TradeSignal
from app.research.weight_optimizer import optimize_weights_bayesian, optimize_weights_grid
from app.services.candle_source import fetch_candles
from app.services.database import db
from app.services.technical_analysis import compute_indicators


@dataclass
class BacktestSummary:
    total_return: float
    total_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float


@dataclass(frozen=True)
class TrainValWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validate_start: pd.Timestamp
    validate_end: pd.Timestamp


def _timestamp_index(df: pd.DataFrame, signals: Iterable[TradeSignal]) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    short_entries = pd.Series(False, index=df.index)
    short_exits = pd.Series(False, index=df.index)

    for signal in signals:
        if signal.direction not in {"BUY", "SELL"} or signal.timestamp is None:
            continue
        signal_ts = pd.Timestamp(signal.timestamp)
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.tz_localize("UTC")
        nearest_idx = df.index.get_indexer([signal_ts], method="nearest")
        if nearest_idx.size == 0 or nearest_idx[0] < 0:
            continue
        idx = df.index[nearest_idx[0]]
        if signal.direction == "BUY":
            entries.loc[idx] = True
            exits.loc[idx] = True
        else:
            short_entries.loc[idx] = True
            short_exits.loc[idx] = True

    return entries, exits, short_entries, short_exits


def run_signal_backtest(df: pd.DataFrame, signals: Iterable[TradeSignal]) -> BacktestSummary:
    if vbt is None:
        raise RuntimeError("vectorbt is not installed")

    entries, exits, short_entries, short_exits = _timestamp_index(df, signals)
    portfolio = vbt.Portfolio.from_signals(
        close=df["close"],
        entries=entries,
        exits=exits.shift(1, fill_value=False),
        short_entries=short_entries,
        short_exits=short_exits.shift(1, fill_value=False),
        fees=0.0005,
        slippage=0.0002,
    )

    stats = portfolio.stats()
    return BacktestSummary(
        total_return=float(stats.get("Total Return [%]", 0.0)),
        total_trades=int(stats.get("Total Trades", 0)),
        win_rate=float(stats.get("Win Rate [%]", 0.0)),
        max_drawdown=float(stats.get("Max Drawdown [%]", 0.0)),
        sharpe_ratio=float(stats.get("Sharpe Ratio", 0.0)),
    )


def run_candle_source_backtest(symbol: str, timeframe: str, lookback: str) -> pd.DataFrame:
    source_result = fetch_candles(symbol, timeframe, lookback)
    if source_result is None:
        raise RuntimeError(f"No candles available for {symbol} {timeframe}")
    return compute_indicators(source_result.df)


def optimize_weights_walk_forward(
    *,
    df: pd.DataFrame,
    symbol: str,
    trading_style: str,
    timeframe: str,
    search_space: dict[str, list[float]],
    objective,
    train_days: int = 60,
    validate_days: int = 20,
) -> list[dict]:
    if df.empty:
        return []

    index = pd.DatetimeIndex(df.index)
    start = index.min()
    end = index.max()
    windows: list[TrainValWindow] = []
    cursor = start
    while cursor < end:
        train_end = cursor + pd.Timedelta(days=train_days)
        validate_end = train_end + pd.Timedelta(days=validate_days)
        if validate_end > end:
            break
        windows.append(
            TrainValWindow(
                train_start=cursor,
                train_end=train_end,
                validate_start=train_end,
                validate_end=validate_end,
            )
        )
        cursor = validate_end

    use_bayesian = os.getenv("ENABLE_BAYESIAN_WEIGHT_OPTIMIZER", "0") == "1"
    results: list[dict] = []
    for window in windows:
        train_df = df[(index >= window.train_start) & (index < window.train_end)]
        validate_df = df[(index >= window.validate_start) & (index < window.validate_end)]
        if train_df.empty or validate_df.empty:
            continue

        optimizer = optimize_weights_bayesian if use_bayesian else optimize_weights_grid
        result = optimizer(
            search_space=search_space,
            objective=lambda weights: objective(train_df, validate_df, weights),
        )
        payload = {
            "symbol": symbol,
            "trading_style": trading_style,
            "timeframe": timeframe,
            "train_start": window.train_start.to_pydatetime(),
            "train_end": window.train_end.to_pydatetime(),
            "validate_start": window.validate_start.to_pydatetime(),
            "validate_end": window.validate_end.to_pydatetime(),
            "method": result.method,
            "objective_score": result.objective_score,
            "weights": result.weights,
        }
        db.save_optimized_weights(payload)
        results.append(payload)

    return results
