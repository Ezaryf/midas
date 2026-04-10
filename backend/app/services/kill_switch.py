from __future__ import annotations

from dataclasses import dataclass, field

from app.services.database import db


@dataclass(frozen=True)
class KillSwitchContext:
    symbol: str
    data_age_seconds: float = 0.0
    regime_stability: float = 1.0
    current_spread: float = 0.0
    typical_spread: float = 0.0
    drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    transition_cluster: bool = False


@dataclass
class KillSwitchDecision:
    halt_trading: bool = False
    require_manual_approval: bool = False
    size_multiplier: float = 1.0
    reasons: list[str] = field(default_factory=list)
    is_enabled: bool = True


class KillSwitch:
    @classmethod
    def get_config(cls, account_id: str = "default"):
        from app.services.database import db
        import os
        db_settings = db.get_settings(account_id) if db and db.is_enabled() else {}
        
        return {
            "enabled": db_settings.get("enable_kill_switch", os.getenv("ENABLE_KILL_SWITCH", "true")).lower() not in ("0", "false", "no", "off"),
            "max_data_age": float(db_settings.get("max_data_age_seconds", "900")),
            "max_drawdown": float(db_settings.get("max_drawdown_percent", "15")),
            "max_consecutive_losses": int(db_settings.get("max_consecutive_losses", "5")),
            "min_regime_stability": float(db_settings.get("min_regime_stability", "0.5")),
        }

    @classmethod
    def check(cls, context: KillSwitchContext) -> KillSwitchDecision:
        cfg = cls.get_config()
        if not cfg["enabled"]:
            return KillSwitchDecision(is_enabled=False)

        decision = KillSwitchDecision()
        if context.data_age_seconds > cfg["max_data_age"]:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("data_staleness")
        if context.drawdown_pct > cfg["max_drawdown"]:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("drawdown_threshold")
        if context.consecutive_losses >= cfg["max_consecutive_losses"]:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("consecutive_losses")
        if decision.halt_trading:
            return decision

        if context.transition_cluster or context.regime_stability < cfg["min_regime_stability"]:
            decision.require_manual_approval = True
            decision.size_multiplier = min(decision.size_multiplier, 0.25)
            decision.reasons.append("regime_instability")
        if context.typical_spread > 0 and context.current_spread > context.typical_spread * 2:
            decision.require_manual_approval = True
            decision.size_multiplier = min(decision.size_multiplier, 0.25)
            decision.reasons.append("spread_anomaly")
        elif context.typical_spread > 0 and context.current_spread > context.typical_spread * 1.25:
            decision.size_multiplier = min(decision.size_multiplier, 0.75)
            decision.reasons.append("moderate_friction")
        return decision

    @classmethod
    def log_event(cls, *, symbol: str, decision: KillSwitchDecision, context: dict) -> None:
        if not db.is_enabled() or not decision.reasons:
            return

        def _do_log():
            try:
                db.log_kill_switch_event(
                    symbol=symbol,
                    action=(
                        "halt_trading"
                        if decision.halt_trading
                        else "require_manual_approval"
                        if decision.require_manual_approval
                        else "reduce_size"
                    ),
                    reasons=decision.reasons,
                    context=context,
                )
            except Exception:
                pass

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _do_log)
        except RuntimeError:
            _do_log()
