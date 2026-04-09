from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.services.database import db


@dataclass
class ShadowSignal:
    analysis_batch_id: str
    signal_id: str | None
    symbol: str
    trading_style: str
    timeframe: str
    direction: str
    setup_type: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    score: float
    regime_at_signal: str
    session_at_signal: str
    source_data_fresh: str
    regime_confidence_at_entry: float
    volatility_at_entry: float
    spread_estimate: float
    compression_ratio_at_entry: float
    signal_timestamp: datetime
    rank: int
    status: str = "pending"


class ShadowEngine:
    STYLE_TIMEOUT_BARS = {
        "Scalper": 30,
        "Intraday": 24,
        "Swing": 20,
    }

    @staticmethod
    def _session_label(timestamp: datetime) -> str:
        hour = timestamp.astimezone(timezone.utc).hour
        if 8 <= hour < 12:
            return "london"
        if 13 <= hour < 17:
            return "ny"
        if 0 <= hour < 7:
            return "asia"
        return "off"

    def log_candidate(
        self,
        *,
        candidate: Any,
        analysis_batch_id: str,
        symbol: str,
        trading_style: str,
        timeframe: str,
        regime_confidence: float,
        compression_ratio: float,
        data_freshness: str,
        spread_estimate: float,
        volatility_ratio: float,
        signal_timestamp: datetime,
        rank: int,
    ) -> None:
        if not db.is_enabled():
            return
        payload = ShadowSignal(
            analysis_batch_id=analysis_batch_id,
            signal_id=getattr(candidate, "signal_id", None),
            symbol=symbol,
            trading_style=trading_style,
            timeframe=timeframe,
            direction=str(getattr(candidate, "direction", "HOLD")),
            setup_type=str(getattr(candidate, "setup_type", "unknown")),
            entry_price=float(getattr(candidate, "entry_price", 0.0)),
            stop_loss=float(getattr(candidate, "stop_loss", 0.0)),
            take_profit_1=float(getattr(candidate, "take_profit_1", 0.0)),
            take_profit_2=float(getattr(candidate, "take_profit_2", 0.0)),
            score=float(getattr(candidate, "score", getattr(candidate, "confidence", 0.0))),
            regime_at_signal=str(getattr(candidate, "market_regime", "unknown")),
            session_at_signal=self._session_label(signal_timestamp),
            source_data_fresh=data_freshness,
            regime_confidence_at_entry=regime_confidence,
            volatility_at_entry=volatility_ratio,
            spread_estimate=spread_estimate,
            compression_ratio_at_entry=compression_ratio,
            signal_timestamp=signal_timestamp,
            rank=rank,
        )
        try:
            db.save_shadow_candidate(asdict(payload))
        except Exception:
            return

    def advance_pending(self, *, symbol: str, timeframe: str, df: pd.DataFrame, trading_style: str) -> None:
        if not db.is_enabled() or df.empty:
            return
        timeout_bars = self.STYLE_TIMEOUT_BARS.get(trading_style, 20)
        try:
            pending_candidates = db.get_pending_shadow_candidates(symbol=symbol, timeframe=timeframe)
        except Exception:
            return

        for candidate in pending_candidates:
            resolved = self._simulate_candidate(candidate, df=df, timeout_bars=timeout_bars)
            if not resolved:
                continue
            try:
                db.update_shadow_candidate_simulation(candidate["id"], resolved)
            except Exception:
                continue

    def _simulate_candidate(self, candidate: dict[str, Any], *, df: pd.DataFrame, timeout_bars: int) -> dict[str, Any] | None:
        timestamp = candidate.get("signal_timestamp") or candidate.get("created_at")
        if not timestamp:
            return None
        signal_time = pd.Timestamp(timestamp)
        if signal_time.tzinfo is None:
            signal_time = signal_time.tz_localize("UTC")

        future_df = df[df.index > signal_time]
        if future_df.empty:
            return None

        entry_price = float(candidate.get("entry_price", 0.0))
        stop_loss = float(candidate.get("stop_loss", 0.0))
        take_profit = float(candidate.get("take_profit_1", 0.0))
        direction = str(candidate.get("direction", "HOLD"))

        bars = future_df.iloc[:timeout_bars]
        entry_index = None
        mfe_points = 0.0
        mae_points = 0.0
        for offset, (_, row) in enumerate(bars.iterrows()):
            high = float(row["high"])
            low = float(row["low"])
            if entry_index is None and low <= entry_price <= high:
                entry_index = offset
                continue
            if entry_index is None:
                continue

            if direction == "BUY":
                mfe_points = max(mfe_points, high - entry_price)
                mae_points = max(mae_points, entry_price - low)
                if low <= stop_loss:
                    return {
                        "status": "simulated",
                        "simulated_entry_bar_index": entry_index,
                        "simulated_exit_bar_index": offset,
                        "simulated_outcome": "loss",
                        "mfe_points": round(mfe_points, 4),
                        "mae_points": round(mae_points, 4),
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "sl_hit": True,
                    }
                if high >= take_profit:
                    return {
                        "status": "simulated",
                        "simulated_entry_bar_index": entry_index,
                        "simulated_exit_bar_index": offset,
                        "simulated_outcome": "win",
                        "mfe_points": round(mfe_points, 4),
                        "mae_points": round(mae_points, 4),
                        "tp1_hit": True,
                        "tp2_hit": float(candidate.get("take_profit_2", take_profit)) <= high,
                        "sl_hit": False,
                    }
            else:
                mfe_points = max(mfe_points, entry_price - low)
                mae_points = max(mae_points, high - entry_price)
                if high >= stop_loss:
                    return {
                        "status": "simulated",
                        "simulated_entry_bar_index": entry_index,
                        "simulated_exit_bar_index": offset,
                        "simulated_outcome": "loss",
                        "mfe_points": round(mfe_points, 4),
                        "mae_points": round(mae_points, 4),
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "sl_hit": True,
                    }
                if low <= take_profit:
                    return {
                        "status": "simulated",
                        "simulated_entry_bar_index": entry_index,
                        "simulated_exit_bar_index": offset,
                        "simulated_outcome": "win",
                        "mfe_points": round(mfe_points, 4),
                        "mae_points": round(mae_points, 4),
                        "tp1_hit": True,
                        "tp2_hit": float(candidate.get("take_profit_2", take_profit)) >= low,
                        "sl_hit": False,
                    }

        if len(bars) < timeout_bars:
            return None

        return {
            "status": "simulated",
            "simulated_entry_bar_index": entry_index,
            "simulated_exit_bar_index": len(bars) - 1,
            "simulated_outcome": "timeout" if entry_index is not None else "no_trade",
            "mfe_points": round(mfe_points, 4),
            "mae_points": round(mae_points, 4),
            "tp1_hit": False,
            "tp2_hit": False,
            "sl_hit": False,
        }

    def compare_to_actual(self, outcome: dict[str, Any]) -> None:
        if not db.is_enabled():
            return
        signal_id = outcome.get("signal_id")
        if not signal_id:
            return
        try:
            db.update_shadow_candidate_actual(signal_id=signal_id, outcome=outcome)
        except Exception:
            return
