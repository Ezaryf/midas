import asyncio
import logging
import os
from datetime import datetime
from app.api.ws.mt5_handler import manager

logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "10"))  # Faster for scalping

# Trading session times (GMT)
LONDON_SESSION = (8, 12)   # 8:00-12:00 GMT
NY_SESSION = (13, 17)      # 13:00-17:00 GMT

# Daily limits
MAX_DAILY_TRADES = 5
MAX_DAILY_LOSS_PCT = 2.0
MAX_CONSECUTIVE_LOSSES = 3

# Broker costs (adjust to your broker)
GOLD_SPREAD_POINTS = 5.0
COMMISSION_PER_LOT = 2.0

# Style configs — defined once, used by both loop and API
STYLE_CONFIG = {
    "Scalper": {
        "timeframes": ["5m", "1m"],  # M5 primary, M1 for timing
        "lookback":   ["1d", "2d"],
        "min_confidence":          50,  # Higher threshold
        "signal_confidence":       60,  # Higher threshold
        "auto_execute_confidence": 75,  # Higher threshold
        "max_signals":             3,   # REDUCED from 8 to 3
        "rr_min":    1.5,  # IMPROVED from 1.0 to 1.5
        "rr_target": 2.0,  # IMPROVED from 1.5 to 2.0
        "atr_sl_mult":  0.8,  # IMPROVED from 0.5 to 0.8
        "atr_tp_mult":  1.2,  # IMPROVED from 0.5 to 1.2
        # Realistic limits for scalping gold (accounting for spread)
        "max_sl_points": 15.0,  # INCREASED from 8 to 15
        "max_tp1_points": 22.0, # INCREASED from 8 to 22 (1.5:1 RR)
        "max_tp2_points": 30.0, # INCREASED from 12 to 30 (2:1 RR)
        "min_entry_separation": 50.0,  # NEW: Min 50pts between entries
        "max_positions_per_direction": 1,  # NEW: Only 1 BUY or 1 SELL at a time
    },
    "Intraday": {
        "timeframes": ["15m", "1h"],
        "lookback":   ["5d", "7d"],
        "min_confidence":          40,
        "signal_confidence":       55,
        "auto_execute_confidence": 75,
        "max_signals":             6,
        "rr_min":    1.5,
        "rr_target": 2.5,
        "atr_sl_mult":  1.5,
        "atr_tp_mult":  1.5,
        "max_sl_points": 30.0,
        "max_tp1_points": 45.0,
        "max_tp2_points": 75.0,
    },
    "Swing": {
        "timeframes": ["1h", "4h"],
        "lookback":   ["10d", "20d"],
        "min_confidence":          45,
        "signal_confidence":       60,
        "auto_execute_confidence": 80,
        "max_signals":             4,
        "rr_min":    2.0,
        "rr_target": 3.5,
        "atr_sl_mult":  2.0,
        "atr_tp_mult":  2.0,
        "max_sl_points": 80.0,
        "max_tp1_points": 160.0,
        "max_tp2_points": 280.0,
    },
}


async def background_trading_loop():
    logger.info(f"Trading loop started. Analysis every {ANALYSIS_INTERVAL}s.")
    
    # Daily tracking
    daily_trades = 0
    daily_pnl = 0.0
    consecutive_losses = 0
    last_reset_date = datetime.now().date()

    # Run immediately on startup
    try:
        # Read style from manager first (set by frontend), fallback to env
        style = manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
        if is_trading_session_active():
            result = await run_analysis_cycle(trading_style=style)
            if result:
                daily_trades += 1
                if result.get("loss"):
                    consecutive_losses += 1
                    daily_pnl -= result.get("loss_amount", 0)
                else:
                    consecutive_losses = 0
        else:
            logger.info("Outside trading hours - skipping initial analysis")
    except Exception as e:
        logger.error(f"Initial analysis error: {e}")

    while True:
        try:
            await asyncio.sleep(ANALYSIS_INTERVAL)
            
            # Reset daily counters at midnight
            current_date = datetime.now().date()
            if current_date != last_reset_date:
                logger.info(f"New trading day - resetting counters. Yesterday: {daily_trades} trades, PnL: ${daily_pnl:.2f}")
                daily_trades = 0
                daily_pnl = 0.0
                consecutive_losses = 0
                last_reset_date = current_date
            
            # Check daily limits
            if daily_trades >= MAX_DAILY_TRADES:
                logger.warning(f"Daily trade limit reached ({MAX_DAILY_TRADES}). Pausing until tomorrow.")
                await asyncio.sleep(300)  # Check every 5 min
                continue
            
            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                logger.warning(f"Consecutive loss limit reached ({MAX_CONSECUTIVE_LOSSES}). Pausing for 1 hour.")
                await asyncio.sleep(3600)
                consecutive_losses = 0  # Reset after cooldown
                continue
            
            # Check if in trading session
            if not is_trading_session_active():
                logger.debug("Outside trading hours - skipping analysis")
                continue
            
            # Check for upcoming news events
            if is_high_impact_news_upcoming():
                logger.warning("High-impact news event within 30 minutes - skipping analysis")
                continue
            
            # Run analysis
            # Read style from manager first (set by frontend), fallback to env
            style = manager.trading_style or os.getenv("TRADING_STYLE", "Scalper")
            result = await run_analysis_cycle(trading_style=style)
            
            if result:
                daily_trades += 1
                if result.get("loss"):
                    consecutive_losses += 1
                    daily_pnl -= result.get("loss_amount", 0)
                else:
                    consecutive_losses = 0
                    
        except asyncio.CancelledError:
            logger.info("Trading loop cancelled.")
            raise
        except Exception as e:
            logger.error(f"Trading loop error: {e}")
            await asyncio.sleep(30)


def is_trading_session_active() -> bool:
    """Check if current time is within London or NY session (GMT)."""
    from datetime import datetime, timezone
    
    current_hour = datetime.now(timezone.utc).hour
    
    # London session: 8:00-12:00 GMT
    if LONDON_SESSION[0] <= current_hour < LONDON_SESSION[1]:
        return True
    
    # NY session: 13:00-17:00 GMT
    if NY_SESSION[0] <= current_hour < NY_SESSION[1]:
        return True
    
    return False


def is_high_impact_news_upcoming(minutes_ahead: int = 30) -> bool:
    """Check if high-impact news event is coming up."""
    try:
        from app.services.forex_factory import ForexFactoryService
        from datetime import datetime, timedelta
        
        ff = ForexFactoryService()
        events = ff.get_weekly_events()
        
        now = datetime.now()
        cutoff = now + timedelta(minutes=minutes_ahead)
        
        for event in events:
            if event.get("impact") == "High":
                # Parse event time and check if within window
                # This is simplified - you'd need proper time parsing
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking news events: {e}")
        return False  # Don't block trading on error


async def run_analysis_cycle(trading_style: str | None = None):
    """
    Full analysis cycle. trading_style is passed explicitly — never read from env here.
    This ensures the API call with a specific style produces different results than the loop.
    """
    from app.services.ai_engine import AITradingEngine
    from app.services.forex_factory import ForexFactoryService
    from app.services.technical_analysis import get_latest_indicators, fetch_ohlcv, compute_indicators
    from app.services.pattern_recognition import PatternRecognizer
    from app.services.database import db
    from collections import defaultdict

    def clamp_levels(entry: float, sl: float, tp1: float, tp2: float, direction: str, cfg: dict) -> tuple:
        """Enforce hard point limits per trading style, accounting for spread."""
        sign = 1 if direction == "BUY" else -1
        max_sl  = cfg["max_sl_points"]
        max_tp1 = cfg["max_tp1_points"]
        max_tp2 = cfg["max_tp2_points"]

        # Account for spread in calculations
        spread = GOLD_SPREAD_POINTS
        
        # Clamp SL distance (add spread to effective risk)
        sl_dist = abs(entry - sl)
        if sl_dist > max_sl:
            sl = round(entry - max_sl * sign, 2)
            sl_dist = max_sl

        # Clamp TP1 — must be at least 1.5:1 RR after spread
        # Effective risk = SL distance + spread
        effective_risk = sl_dist + spread
        min_tp1_dist = effective_risk * cfg["rr_min"]
        
        tp1_dist = abs(tp1 - entry)
        tp1_dist = max(min_tp1_dist, min(tp1_dist, max_tp1))
        tp1 = round(entry + tp1_dist * sign, 2)

        # Clamp TP2 — must be > TP1, at most max_tp2
        min_tp2_dist = tp1_dist * 1.3  # At least 30% more than TP1
        tp2_dist = abs(tp2 - entry)
        tp2_dist = max(min_tp2_dist, min(tp2_dist, max_tp2))
        tp2 = round(entry + tp2_dist * sign, 2)

        return sl, tp1, tp2

    # Use passed style, fall back to env, fall back to Scalper
    style = trading_style or os.getenv("TRADING_STYLE", "Scalper")
    # Normalize capitalization
    style = style.capitalize() if style.lower() in ("scalper", "intraday", "swing") else style
    if style not in STYLE_CONFIG:
        style = "Scalper"

    config = STYLE_CONFIG[style]
    logger.info(f"Analysis: style={style} | TFs={config['timeframes']} | RR={config['rr_min']}-{config['rr_target']} | Spread={GOLD_SPREAD_POINTS}pts")

    loop = asyncio.get_event_loop()

    # Fetch indicators using the PRIMARY timeframe for this style (M5 for scalper)
    indicators = await loop.run_in_executor(None, get_latest_indicators, config["timeframes"][0])
    current_price = indicators.pop("current_price")
    trend         = indicators.pop("trend")
    atr           = indicators.get("ATRr_14", 15.0)

    # Use live MT5 price if available
    latest_tick = manager.latest_tick
    if latest_tick:
        current_price = float(latest_tick.get("bid", current_price))

    # ── Pattern detection — prioritize PRIMARY timeframe ──────────────────────
    all_patterns = []
    try:
        for i, (tf, lookback) in enumerate(zip(config["timeframes"], config["lookback"])):
            df = await loop.run_in_executor(None, fetch_ohlcv, tf, lookback)
            if df is None or len(df) < 20:
                logger.warning(f"  {tf}: insufficient data ({len(df) if df is not None else 0} bars)")
                continue
            df = await loop.run_in_executor(None, compute_indicators, df)
            recognizer = PatternRecognizer(min_confidence=config["min_confidence"])
            tf_patterns = await loop.run_in_executor(None, recognizer.detect_all_patterns, df)
            
            for p in tf_patterns:
                p.timeframe = tf
                # PRIMARY timeframe (M5) gets higher weight
                if i == 0:
                    p.confidence = min(p.confidence + 10, 95)
                # Secondary timeframe (M1) gets lower weight
                elif i == 1:
                    p.confidence = max(p.confidence - 5, 40)
            
            all_patterns.extend(tf_patterns)
            logger.info(f"  {tf}: {len(tf_patterns)} patterns")

        # Confluence boost — same zone on multiple timeframes
        groups = defaultdict(list)
        for p in all_patterns:
            key = (round(p.entry_price / 10) * 10, p.direction)
            groups[key].append(p)
        for group in groups.values():
            if len(group) > 1:
                for p in group:
                    p.confidence = min(p.confidence + 8 * (len(group) - 1), 92)

    except Exception as e:
        logger.error(f"Pattern detection failed: {e}")

    # ── Score by profit potential: RR × confidence ────────────────────────────
    def profit_score(p) -> float:
        risk = abs(p.entry_price - p.stop_loss)
        if risk == 0:
            return 0
        reward = abs(p.take_profit - p.entry_price)
        return (reward / risk) * (p.confidence / 100)

    all_patterns.sort(key=profit_score, reverse=True)

    # ── Build signals with correlation filter ────────────────────────────────
    signals: list[dict] = []
    seen_zones: set[tuple] = set()
    direction_count = {"BUY": 0, "SELL": 0}  # Track positions per direction

    for pattern in all_patterns:
        if pattern.confidence < config["signal_confidence"]:
            continue
        if len(signals) >= config["max_signals"]:
            break
        
        # NEW: Check max positions per direction
        if direction_count[pattern.direction] >= config.get("max_positions_per_direction", 1):
            logger.debug(f"Skipping {pattern.direction} - max positions reached")
            continue

        # NEW: Check minimum entry separation
        min_sep = config.get("min_entry_separation", 50.0)
        too_close = False
        for existing_sig in signals:
            if abs(pattern.entry_price - existing_sig["entry_price"]) < min_sep:
                too_close = True
                logger.debug(f"Skipping entry @ {pattern.entry_price} - too close to {existing_sig['entry_price']}")
                break
        if too_close:
            continue

        zone = (round(pattern.entry_price / 10) * 10, pattern.direction)
        if zone in seen_zones:
            continue
        seen_zones.add(zone)

        # Build raw SL/TP then clamp to style limits
        raw_risk = abs(pattern.entry_price - pattern.stop_loss)
        sign = 1 if pattern.direction == "BUY" else -1
        raw_sl  = pattern.stop_loss
        raw_tp1 = round(pattern.entry_price + raw_risk * config["rr_min"]    * sign, 2)
        raw_tp2 = round(pattern.entry_price + raw_risk * config["rr_target"] * sign, 2)
        sl, tp1, tp2 = clamp_levels(pattern.entry_price, raw_sl, raw_tp1, raw_tp2, pattern.direction, config)
        
        # Calculate real RR after spread
        effective_risk = abs(pattern.entry_price - sl) + GOLD_SPREAD_POINTS
        effective_reward = abs(tp1 - pattern.entry_price) - GOLD_SPREAD_POINTS
        real_rr = effective_reward / effective_risk if effective_risk > 0 else 0
        
        logger.info(f"  Signal: {pattern.direction} @ {pattern.entry_price} | SL: {abs(pattern.entry_price - sl):.1f}pts | TP1: {abs(tp1 - pattern.entry_price):.1f}pts | Real RR: 1:{real_rr:.2f}")

        signals.append({
            "direction":     pattern.direction,
            "entry_price":   pattern.entry_price,
            "stop_loss":     sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "confidence":    round(pattern.confidence, 1),
            "reasoning":     f"{pattern.type.value} ({getattr(pattern, 'timeframe', '?')}): {pattern.description} | Real RR 1:{real_rr:.2f} after {GOLD_SPREAD_POINTS}pt spread",
            "trading_style": style,
            "patterns":      [{"type": pattern.type.value, "confidence": pattern.confidence, "description": pattern.description}],
            "auto_execute":  pattern.confidence >= config["auto_execute_confidence"],
        })
        
        direction_count[pattern.direction] += 1

    # ── Fallback: ensure at least 1-2 quality signals ────────────────────────
    if len(signals) < 2:
        logger.info(f"Only {len(signals)} pattern signals — adding ATR fallback for {style}")
        direction = "BUY" if trend in ("BULLISH", "NEUTRAL") else "SELL"
        opposite  = "SELL" if direction == "BUY" else "BUY"
        sl_mult   = config["atr_sl_mult"]

        # Only add fallback if we don't have max positions in that direction
        for d, entry_offset in [(direction, 0.0), (opposite, atr * 0.5 * (-1 if direction == "BUY" else 1))]:
            if direction_count.get(d, 0) >= config.get("max_positions_per_direction", 1):
                continue
                
            entry   = round(current_price + entry_offset, 2)
            sl_dist = atr * sl_mult
            raw_sl  = round(entry - sl_dist if d == "BUY" else entry + sl_dist, 2)
            raw_tp1 = round(entry + sl_dist * config["rr_min"]    * (1 if d == "BUY" else -1), 2)
            raw_tp2 = round(entry + sl_dist * config["rr_target"] * (1 if d == "BUY" else -1), 2)
            sl, tp1, tp2 = clamp_levels(entry, raw_sl, raw_tp1, raw_tp2, d, config)
            
            # Check minimum separation
            too_close = False
            for existing_sig in signals:
                if abs(entry - existing_sig["entry_price"]) < config.get("min_entry_separation", 50.0):
                    too_close = True
                    break
            if too_close:
                continue
            
            zone    = (round(entry / 10) * 10, d)
            if zone not in seen_zones:
                seen_zones.add(zone)
                
                effective_risk = abs(entry - sl) + GOLD_SPREAD_POINTS
                effective_reward = abs(tp1 - entry) - GOLD_SPREAD_POINTS
                real_rr = effective_reward / effective_risk if effective_risk > 0 else 0
                
                signals.append({
                    "direction":     d,
                    "entry_price":   entry,
                    "stop_loss":     sl,
                    "take_profit_1": tp1,
                    "take_profit_2": tp2,
                    "confidence":    55.0,
                    "reasoning":     f"{style} ATR setup | {d} | Trend: {trend} | SL: {abs(entry - sl):.1f} pts | Real RR: 1:{real_rr:.2f}",
                    "trading_style": style,
                    "patterns":      [],
                    "auto_execute":  False,
                })
                direction_count[d] = direction_count.get(d, 0) + 1

    # ── AI signal ─────────────────────────────────────────────────────────────
    api_key  = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    provider = os.getenv("AI_PROVIDER", "openai")

    if api_key and all_patterns:
        try:
            ff = ForexFactoryService()
            calendar_events = ff.get_weekly_events()[:5]
            engine = AITradingEngine(api_key=api_key, provider=provider)
            ai_signal = await engine.generate_signal(
                current_price=current_price,
                trend=trend,
                indicators=indicators,
                calendar_events=calendar_events,
                patterns=all_patterns[:5],
                trading_style=style,
            )
            ai_signal.trading_style = style  # enforce

            if ai_signal.direction in ("BUY", "SELL"):
                risk = abs(ai_signal.entry_price - ai_signal.stop_loss)
                sign = 1 if ai_signal.direction == "BUY" else -1
                raw_tp1 = round(ai_signal.entry_price + risk * config["rr_min"]    * sign, 2)
                raw_tp2 = round(ai_signal.entry_price + risk * config["rr_target"] * sign, 2)
                sl, tp1, tp2 = clamp_levels(ai_signal.entry_price, ai_signal.stop_loss, raw_tp1, raw_tp2, ai_signal.direction, config)
                ai_signal.stop_loss     = sl
                ai_signal.take_profit_1 = tp1
                ai_signal.take_profit_2 = tp2

                signal_id = await db.save_signal(
                    signal=ai_signal, indicators=indicators, calendar_events=calendar_events,
                    current_price=current_price, trend=trend, ai_provider=provider, ai_model=engine.model,
                )
                sd = ai_signal.model_dump()
                sd["signal_id"]    = signal_id
                sd["patterns"]     = [{"type": p.type.value, "confidence": p.confidence, "description": p.description} for p in all_patterns[:3]]
                sd["auto_execute"] = ai_signal.confidence >= config["auto_execute_confidence"]

                zone = (round(ai_signal.entry_price / 10) * 10, ai_signal.direction)
                if zone not in seen_zones:
                    signals.insert(0, sd)
                    logger.info(f"  AI: {ai_signal.direction} @ {ai_signal.entry_price} conf={ai_signal.confidence}%")
        except Exception as e:
            logger.error(f"AI signal failed: {e}")

    # ── Broadcast ─────────────────────────────────────────────────────────────
    logger.info(f"Broadcasting {len(signals)} {style} signals")
    for sig in signals:
        await manager.broadcast_json({
            "type":   "SIGNAL",
            "action": "PLACE_ORDER" if sig.get("auto_execute") else "DISPLAY",
            "data":   sig,
        })
