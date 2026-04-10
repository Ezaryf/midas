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


class KillSwitch:
    @classmethod
    def check(cls, context: KillSwitchContext) -> KillSwitchDecision:
        import os
        if os.getenv("ENABLE_KILL_SWITCH", "true").lower() in ("0", "false", "no", "off"):
            return KillSwitchDecision()

        decision = KillSwitchDecision()
        if context.data_age_seconds > 900:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("data_staleness")
        if context.drawdown_pct > 15:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("drawdown_threshold")
        if context.consecutive_losses >= 5:
            decision.halt_trading = True
            decision.size_multiplier = 0.0
            decision.reasons.append("consecutive_losses")
        if decision.halt_trading:
            return decision

        if context.transition_cluster or context.regime_stability < 0.5:
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
