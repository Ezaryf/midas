import asyncio
from collections import deque
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from app.api.ws.mt5_handler import manager
from app.services.kill_switch import KillSwitch, KillSwitchContext
from app.services.runtime_state import runtime_state
from app.services.symbols import symbols_match

logger = logging.getLogger(__name__)

def get_loop_config(account_id: str = "default"):
    from app.services.database import db
    db_settings = db.get_settings(account_id) if db and db.is_enabled() else {}
    
    return {
        "analysis_interval": int(db_settings.get("analysis_interval_seconds", 10)),
        "max_daily_trades": int(db_settings.get("max_daily_trades", 50)),
        "max_daily_loss_pct": float(db_settings.get("max_daily_loss_pct", "2.0")),
        "max_consecutive_losses": int(db_settings.get("max_consecutive_losses", "3")),
        "gold_spread_points": float(db_settings.get("gold_spread_points", "5.0")),
        "commission_per_lot": float(db_settings.get("commission_per_lot", "2.0")),
    }

LONDON_SESSION = (8, 12)
NY_SESSION = (13, 17)
RECENT_PRIMARY_REGIMES: deque[str] = deque(maxlen=3)

STYLE_CONFIG = {
    "Scalper": {
        "timeframes": ["1m", "5m"],
        "lookback": ["1d", "2d"],
        "min_pattern_confidence": 50,
        "auto_execute_confidence": 62,
        "rr_min": 1.15,
        "rr_target": 1.6,
        "stop_buffer_atr": 0.24,
        "entry_window_atr": 0.18,
        "max_backups": 2,
        "allow_off_session_live": True,
        "tick_freshness_seconds": 90,
        "micro_scalp": True,
    },
    "Intraday": {
        "timeframes": ["15m", "1h"],
        "lookback": ["5d", "7d"],
        "min_pattern_confidence": 48,
        "auto_execute_confidence": 65,
        "rr_min": 1.5,
        "rr_target": 2.35,
        "stop_buffer_atr": 0.35,
        "entry_window_atr": 0.16,
        "max_backups": 2,
    },
    "Swing": {
        "timeframes": ["1h", "4h"],
        "lookback": ["10d", "20d"],
        "min_pattern_confidence": 48,
        "auto_execute_confidence": 70,
        "rr_min": 1.8,
        "rr_target": 3.0,
        "stop_buffer_atr": 0.45,
        "entry_window_atr": 0.22,
        "max_backups": 2,
    },
}


def _latest_tick_is_recent(target_symbol: Optional[str] = None, freshness_seconds: int = 90) -> bool:
    latest_tick = runtime_state.get_tick() or manager.latest_tick or {}
    if not latest_tick:
        return False

    tick_symbol = latest_tick.get("symbol")
    if target_symbol and tick_symbol and not symbols_match(tick_symbol, target_symbol):
        return False

    raw_time = latest_tick.get("received_at") or latest_tick.get("time")
    if not raw_time:
        return bool(latest_tick.get("bid"))

    try:
        tick_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    except ValueError:
        return bool(latest_tick.get("bid"))

    if tick_time.tzinfo is None:
        tick_time = tick_time.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - tick_time).total_seconds()
    return age_seconds <= freshness_seconds and bool(latest_tick.get("bid"))


def is_trading_session_active(style: str | None = None, symbol: str | None = None) -> bool:
    if os.getenv("DISABLE_SESSION_FILTER", "0") == "1":
        return True

    if style in STYLE_CONFIG:
        cfg = STYLE_CONFIG[style]
        if cfg.get("allow_off_session_live"):
            freshness_seconds = int(cfg.get("tick_freshness_seconds", 90))
            if _latest_tick_is_recent(symbol, freshness_seconds):
                return True

    current_hour = datetime.now(timezone.utc).hour
    if LONDON_SESSION[0] <= current_hour < LONDON_SESSION[1]:
        return True
    if NY_SESSION[0] <= current_hour < NY_SESSION[1]:
        return True
    return False


def is_high_impact_news_upcoming(minutes_ahead: int = 30) -> bool:
    try:
        from datetime import timedelta

        from dateutil import parser as dtparser

        from app.services.forex_factory import get_forex_factory

        ff = get_forex_factory()
        events = ff.get_weekly_events()

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=5)
        window_end = now + timedelta(minutes=minutes_ahead)

        for event in events:
            if event.get("impact") != "High":
                continue
            raw_date = event.get("date", "")
            if not raw_date:
                continue
            try:
                event_time = dtparser.parse(raw_date)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                if window_start <= event_time <= window_end:
                    minutes_until = int((event_time - now).total_seconds() // 60)
                    logger.warning(f"High-impact news in {minutes_until}m: {event.get('title', 'Unknown')}")
                    return True
            except (ValueError, TypeError):
                continue

        return False
    except ImportError:
        logger.warning("python-dateutil not installed - news filter disabled")
        return False
    except Exception as exc:
        logger.error(f"Error checking news events: {exc}")
        return False


async def run_analysis_cycle(trading_style: str | None = None, symbol: str | None = None):
    from app.services.analysis_pipeline import TradingEngine
    from app.services.risk_manager import get_risk_manager
    from app.services.trading_state import trading_state

    cycle_started = time.perf_counter()
    style = trading_style or runtime_state.get_trading_style() or os.getenv("TRADING_STYLE", "Scalper")
    style = style.capitalize() if style.lower() in ("scalper", "intraday", "swing") else style
    if style not in STYLE_CONFIG:
        style = "Scalper"

    target_symbol = symbol or runtime_state.get_target_symbol() or "XAUUSD"
    config = STYLE_CONFIG[style]
    logger.info(
        f"Analysis: symbol={target_symbol} | style={style} | "
        f"TFs={config['timeframes']} | RR={config['rr_min']}-{config['rr_target']}"
    )

    risk_manager = get_risk_manager()
    drawdown_pct = 0.0
    if risk_manager:
        account = risk_manager.get_account_info()
        balance = float(account.get("balance", 0.0) or 0.0)
        equity = float(account.get("equity", 0.0) or 0.0)
        if balance > 0:
            drawdown_pct = ((balance - equity) / balance) * 100.0

    precheck = KillSwitch.check(
        KillSwitchContext(
            symbol=target_symbol,
            drawdown_pct=drawdown_pct,
            consecutive_losses=int(getattr(trading_state, "consecutive_losses", 0)),
            transition_cluster=len(RECENT_PRIMARY_REGIMES) == 3 and all(regime == "transition" for regime in RECENT_PRIMARY_REGIMES),
        )
    )
    if precheck.halt_trading:
        KillSwitch.log_event(
            symbol=target_symbol,
            decision=precheck,
            context={"drawdown_pct": drawdown_pct, "consecutive_losses": getattr(trading_state, "consecutive_losses", 0)},
        )
        logger.warning(f"Kill switch halted analysis cycle: {', '.join(precheck.reasons)}")
        return None

    engine = TradingEngine(STYLE_CONFIG)
    response = await engine.analyze(
        trading_style=style,
        symbol=target_symbol,
        session_active=is_trading_session_active(style=style, symbol=target_symbol),
        news_blocked=is_high_impact_news_upcoming(),
        risk_blocked=False,
        publish=True,
        transition_penalty_active=len(RECENT_PRIMARY_REGIMES) == 3 and all(regime == "transition" for regime in RECENT_PRIMARY_REGIMES),
    )
    RECENT_PRIMARY_REGIMES.append(response.data.market_regime)
    elapsed = time.perf_counter() - cycle_started
    logger.info(
        f"Analysis complete in {elapsed:.2f}s | primary={response.data.primary.direction} "
        f"| source={response.data.source} | regime={response.data.market_regime}"
    )
    return response.data


async def background_trading_loop():
    from app.services.trading_state import trading_state as state

    try:
        style = runtime_state.get_trading_style() or state.trading_style or manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
        symbol = runtime_state.get_target_symbol() or getattr(state, "target_symbol", None) or "XAUUSD"
        logger.info("Running forceful initial analysis on startup.")
        await run_analysis_cycle(trading_style=style, symbol=symbol)
    except Exception as exc:
        logger.error(f"Initial analysis error: {exc}")

    while True:
        try:
            loop_cfg = get_loop_config()
            interval = loop_cfg["analysis_interval"]
            
            await asyncio.sleep(interval)
            state.check_and_reset_daily()
            state.refresh_from_db()

            max_daily_trades = loop_cfg["max_daily_trades"]
            if state.daily_trades >= max_daily_trades:
                logger.warning(f"Daily trade limit reached ({max_daily_trades}). Pausing until tomorrow.")
                await asyncio.sleep(300)
                continue

            max_consecutive_losses = loop_cfg["max_consecutive_losses"]
            if state.consecutive_losses >= max_consecutive_losses:
                logger.warning(f"Consecutive loss limit reached ({max_consecutive_losses}). Pausing for 1 hour.")
                await asyncio.sleep(3600)
                state.reset_consecutive_losses()
                continue

            style = runtime_state.get_trading_style() or state.trading_style or manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
            symbol = runtime_state.get_target_symbol() or getattr(state, "target_symbol", None) or "XAUUSD"
            if not is_trading_session_active(style=style, symbol=symbol):
                logger.debug("Outside trading hours - skipping analysis")
                continue

            if is_high_impact_news_upcoming():
                logger.warning("High-impact news event within 30 minutes - skipping analysis")
                continue

            await run_analysis_cycle(trading_style=style, symbol=symbol)

        except asyncio.CancelledError:
            logger.info("Trading loop cancelled.")
            raise
        except Exception as exc:
            logger.error(f"Trading loop error: {exc}")
            await asyncio.sleep(30)
