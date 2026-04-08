import asyncio
import logging
import os
from datetime import datetime, timezone

from app.api.ws.mt5_handler import manager

logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "10"))

# Trading session times (GMT)
LONDON_SESSION = (8, 12)
NY_SESSION = (13, 17)

# Daily limits
MAX_DAILY_TRADES = 5
MAX_DAILY_LOSS_PCT = 2.0
MAX_CONSECUTIVE_LOSSES = 3

# Broker costs (kept for compatibility with bridge/test tooling)
GOLD_SPREAD_POINTS = 5.0
COMMISSION_PER_LOT = 2.0

STYLE_CONFIG = {
    "Scalper": {
        "timeframes": ["5m", "1m"],
        "lookback": ["2d", "1d"],
        "min_pattern_confidence": 58,
        "auto_execute_confidence": 78,
        "rr_min": 1.35,
        "rr_target": 1.9,
        "stop_buffer_atr": 0.30,
        "entry_window_atr": 0.12,
        "max_backups": 2,
    },
    "Intraday": {
        "timeframes": ["15m", "1h"],
        "lookback": ["5d", "7d"],
        "min_pattern_confidence": 55,
        "auto_execute_confidence": 75,
        "rr_min": 1.5,
        "rr_target": 2.35,
        "stop_buffer_atr": 0.35,
        "entry_window_atr": 0.16,
        "max_backups": 2,
    },
    "Swing": {
        "timeframes": ["1h", "4h"],
        "lookback": ["10d", "20d"],
        "min_pattern_confidence": 55,
        "auto_execute_confidence": 80,
        "rr_min": 1.8,
        "rr_target": 3.0,
        "stop_buffer_atr": 0.45,
        "entry_window_atr": 0.22,
        "max_backups": 2,
    },
}


async def background_trading_loop():
    logger.info(f"Trading loop started. Analysis every {ANALYSIS_INTERVAL}s.")

    from app.services.trading_state import trading_state as state

    try:
        style = state.trading_style or manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
        symbol = getattr(state, "target_symbol", "XAUUSD")
        if is_trading_session_active():
            await run_analysis_cycle(trading_style=style, symbol=symbol)
        else:
            logger.info("Outside trading hours - skipping initial analysis")
    except Exception as exc:
        logger.error(f"Initial analysis error: {exc}")

    while True:
        try:
            await asyncio.sleep(ANALYSIS_INTERVAL)
            state.check_and_reset_daily()

            if state.daily_trades >= MAX_DAILY_TRADES:
                logger.warning(f"Daily trade limit reached ({MAX_DAILY_TRADES}). Pausing until tomorrow.")
                await asyncio.sleep(300)
                continue

            if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                logger.warning(f"Consecutive loss limit reached ({MAX_CONSECUTIVE_LOSSES}). Pausing for 1 hour.")
                await asyncio.sleep(3600)
                state.reset_consecutive_losses()
                continue

            if not is_trading_session_active():
                logger.debug("Outside trading hours - skipping analysis")
                continue

            if is_high_impact_news_upcoming():
                logger.warning("High-impact news event within 30 minutes - skipping analysis")
                continue

            style = state.trading_style or manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
            symbol = getattr(state, "target_symbol", "XAUUSD")
            await run_analysis_cycle(trading_style=style, symbol=symbol)

        except asyncio.CancelledError:
            logger.info("Trading loop cancelled.")
            raise
        except Exception as exc:
            logger.error(f"Trading loop error: {exc}")
            await asyncio.sleep(30)


def is_trading_session_active() -> bool:
    current_hour = datetime.now(timezone.utc).hour
    if LONDON_SESSION[0] <= current_hour < LONDON_SESSION[1]:
        return True
    if NY_SESSION[0] <= current_hour < NY_SESSION[1]:
        return True
    return False


def is_high_impact_news_upcoming(minutes_ahead: int = 30) -> bool:
    try:
        from app.services.forex_factory import ForexFactoryService
        from datetime import timedelta
        from dateutil import parser as dtparser

        ff = ForexFactoryService()
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
    from app.schemas.signal import AnalysisBatch, TradeSignal
    from app.services.ai_engine import AITradingEngine
    from app.services.candle_source import fetch_candles
    from app.services.database import db
    from app.services.forex_factory import ForexFactoryService
    from app.services.market_state import build_analysis_batch, build_snapshot
    from app.services.pattern_recognition import PatternRecognizer
    from app.services.technical_analysis import compute_indicators

    style = trading_style or os.getenv("TRADING_STYLE", "Scalper")
    style = style.capitalize() if style.lower() in ("scalper", "intraday", "swing") else style
    if style not in STYLE_CONFIG:
        style = "Scalper"

    target_symbol = symbol or "XAUUSD"
    config = STYLE_CONFIG[style]
    loop = asyncio.get_event_loop()

    logger.info(
        f"Analysis: symbol={target_symbol} | style={style} | "
        f"TFs={config['timeframes']} | RR={config['rr_min']}-{config['rr_target']}"
    )

    def build_no_data_batch() -> AnalysisBatch:
        current_price = float(manager.latest_tick.get("bid", 0.0)) if manager.latest_tick else 0.0
        hold = TradeSignal(
            symbol=target_symbol,
            direction="HOLD",
            entry_price=current_price,
            stop_loss=current_price,
            take_profit_1=current_price,
            take_profit_2=current_price,
            confidence=0,
            reasoning="No trade: insufficient candle data from MT5 and Yahoo sources.",
            trading_style=style,
            setup_type="no_data",
            market_regime="unknown",
            score=0,
            rank=1,
            is_primary=True,
            entry_window_low=current_price,
            entry_window_high=current_price,
            context_tags=["no_data"],
            source="unavailable",
        )
        return AnalysisBatch(
            analysis_batch_id="no-data",
            symbol=target_symbol,
            trading_style=style,
            evaluated_at=datetime.now(timezone.utc),
            market_regime="unknown",
            regime_summary="No analysis batch generated because no usable candles were available.",
            source="unavailable",
            source_is_live=False,
            primary=hold,
            backups=[],
        )

    datasets: dict[str, tuple] = {}
    patterns_by_timeframe: dict[str, list] = {}
    current_price: float | None = None

    for timeframe, lookback in zip(config["timeframes"], config["lookback"]):
        source_result = await loop.run_in_executor(None, fetch_candles, target_symbol, timeframe, lookback)
        if source_result is None:
            logger.warning(f"  {timeframe}: no candle source available")
            continue

        df = await loop.run_in_executor(None, compute_indicators, source_result.df)
        source_result.df = df
        datasets[timeframe] = (source_result, df)

        if current_price is None and not df.empty:
            current_price = float(df.iloc[-1]["close"])

        recognizer = PatternRecognizer(min_confidence=config["min_pattern_confidence"])
        try:
            tf_patterns = await loop.run_in_executor(None, recognizer.detect_all_patterns, df)
        except Exception as exc:
            logger.error(f"Pattern detection failed for {timeframe}: {exc}")
            tf_patterns = []

        for pattern in tf_patterns:
            pattern.timeframe = timeframe
        patterns_by_timeframe[timeframe] = tf_patterns

        logger.info(
            f"  {timeframe}: source={source_result.source} live={source_result.is_live} patterns={len(tf_patterns)}"
        )

    primary_tf = config["timeframes"][0]
    if primary_tf not in datasets:
        batch = build_no_data_batch()
        await manager.broadcast_json({"type": "SIGNAL_BATCH", "data": batch.model_dump(mode="json")})
        return batch

    latest_tick = manager.latest_tick or {}
    if latest_tick.get("symbol", target_symbol) == target_symbol and latest_tick.get("bid"):
        current_price = float(latest_tick["bid"])
    else:
        current_price = current_price or float(datasets[primary_tf][1].iloc[-1]["close"])

    snapshots: dict[str, object] = {}
    for timeframe, (source_result, df) in datasets.items():
        snapshots[timeframe] = build_snapshot(
            df=df,
            timeframe=timeframe,
            source=source_result.source,
            is_live=source_result.is_live,
            current_price=current_price,
        )

    # ── Broadcast Market State snapshot for live dashboard metrics ──
    primary_snapshot = snapshots[primary_tf]
    market_state_payload = {
        "timeframe": primary_snapshot.timeframe,
        "source": primary_snapshot.source,
        "is_live": primary_snapshot.is_live,
        "current_price": round(primary_snapshot.current_price, 2),
        "atr": round(primary_snapshot.atr, 2),
        "avg_body": round(primary_snapshot.avg_body, 2),
        "body_strength": round(primary_snapshot.body_strength, 3),
        "upper_wick": round(primary_snapshot.upper_wick, 2),
        "lower_wick": round(primary_snapshot.lower_wick, 2),
        "close_location": round(primary_snapshot.close_location, 3),
        "relative_volume": round(primary_snapshot.relative_volume, 3),
        "efficiency_ratio": round(primary_snapshot.efficiency_ratio, 3),
        "compression_ratio": round(primary_snapshot.compression_ratio, 3),
        "ema_slope": round(primary_snapshot.ema_slope, 4),
        "range_high": round(primary_snapshot.range_high, 2),
        "range_low": round(primary_snapshot.range_low, 2),
        "range_width": round(primary_snapshot.range_width, 2),
        "boundary_touches_high": primary_snapshot.boundary_touches_high,
        "boundary_touches_low": primary_snapshot.boundary_touches_low,
        "recent_high": round(primary_snapshot.recent_high, 2),
        "recent_low": round(primary_snapshot.recent_low, 2),
        "support": round(primary_snapshot.support, 2),
        "resistance": round(primary_snapshot.resistance, 2),
        "recent_minor_high": round(primary_snapshot.recent_minor_high, 2),
        "prior_minor_high": round(primary_snapshot.prior_minor_high, 2),
        "recent_minor_low": round(primary_snapshot.recent_minor_low, 2),
        "prior_minor_low": round(primary_snapshot.prior_minor_low, 2),
        "swings": primary_snapshot.swings,
        "regime": primary_snapshot.regime,
        "regime_confidence": round(primary_snapshot.regime_confidence, 1),
        "notes": primary_snapshot.notes,
        "symbol": target_symbol,
        "trading_style": style,
    }
    await manager.broadcast_json({"type": "MARKET_STATE", "data": market_state_payload})

    batch = build_analysis_batch(
        symbol=target_symbol,
        style=style,
        snapshots=snapshots,
        style_cfg=config,
        patterns_by_timeframe=patterns_by_timeframe,
    )

    def matching_patterns(signal: TradeSignal) -> list[dict]:
        primary_snapshot = snapshots[primary_tf]
        tolerance = max(getattr(primary_snapshot, "atr", 1.0) * 1.2, 0.1)
        matches: list[dict] = []
        for tf_patterns in patterns_by_timeframe.values():
            for pattern in tf_patterns:
                direction = getattr(pattern, "direction", "")
                entry = float(getattr(pattern, "entry_price", signal.entry_price))
                if direction != signal.direction or abs(entry - signal.entry_price) > tolerance:
                    continue
                matches.append(
                    {
                        "type": getattr(getattr(pattern, "type", None), "value", str(getattr(pattern, "type", "pattern"))),
                        "confidence": round(float(getattr(pattern, "confidence", 0.0)), 1),
                        "description": getattr(pattern, "description", ""),
                    }
                )
        matches.sort(key=lambda item: item["confidence"], reverse=True)
        return matches[:3]

    batch.primary.patterns = matching_patterns(batch.primary)
    for backup in batch.backups:
        backup.patterns = matching_patterns(backup)

    api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    provider = os.getenv("AI_PROVIDER", "openai")
    if api_key and batch.primary.direction in ("BUY", "SELL"):
        try:
            batch = await AITradingEngine.explain_batch_with_fallback(
                batch=batch,
                primary_provider=provider,
                primary_api_key=api_key,
            )
        except Exception as exc:
            logger.error(f"AI batch explanation failed: {exc}")

    ff = ForexFactoryService()
    calendar_events = ff.get_weekly_events()[:5]
    primary_snapshot = snapshots[primary_tf]
    primary_row = datasets[primary_tf][1].iloc[-1]
    indicators = {
        "RSI_14": round(float(primary_row.get("RSI_14", 50.0)), 2),
        "MACD_12_26_9": round(float(primary_row.get("MACDh_12_26_9", 0.0)), 4),
        "ATRr_14": round(float(primary_row.get("ATRr_14", getattr(primary_snapshot, "atr", 0.0))), 2),
        "EMA_9": round(float(primary_row.get("EMA_9", 0.0)), 2),
        "EMA_21": round(float(primary_row.get("EMA_21", 0.0)), 2),
        "EMA_50": round(float(primary_row.get("EMA_50", 0.0)), 2),
        "symbol": target_symbol,
    }
    trend = getattr(primary_snapshot, "regime", "neutral").upper()

    for signal in [batch.primary, *batch.backups]:
        signal_id = db.save_signal(
            signal=signal,
            indicators=indicators,
            calendar_events=calendar_events,
            current_price=current_price,
            trend=trend,
            ai_provider=provider if api_key else "deterministic",
            ai_model="bounded-explainer" if api_key else "rule-engine",
            regime_summary=batch.regime_summary,
        )
        if signal_id not in {"db_disabled", "error"}:
            signal.signal_id = signal_id
            signal.id = signal_id

    batch_payload = batch.model_dump(mode="json")
    logger.info(
        f"Broadcasting ranked batch: primary={batch.primary.direction} "
        f"setup={batch.primary.setup_type} backups={len(batch.backups)}"
    )
    await manager.broadcast_json({"type": "SIGNAL_BATCH", "data": batch_payload})

    primary_payload = batch.primary.model_dump(mode="json")
    primary_payload["auto_execute"] = (
        batch.primary.direction in ("BUY", "SELL")
        and batch.primary.confidence >= config["auto_execute_confidence"]
    )
    await manager.broadcast_json(
        {
            "type": "SIGNAL",
            "action": "PLACE_ORDER" if primary_payload["auto_execute"] else "DISPLAY",
            "data": primary_payload,
        }
    )

    return batch
