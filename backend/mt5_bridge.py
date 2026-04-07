"""
Midas MT5 Bridge
================
Runs locally on the same Windows machine as MetaTrader 5.
- Streams live XAU/USD ticks to the Midas backend via WebSocket
- Listens for PLACE_ORDER commands and executes them via MT5 API

Requirements:
    pip install MetaTrader5 websockets python-dotenv

Usage:
    python mt5_bridge.py                  # signal display only
    python mt5_bridge.py --auto-trade     # enable order execution
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[MT5Bridge] Loaded config from {env_path}")
    else:
        print(f"[MT5Bridge] No .env found at {env_path} — using environment variables")
except ImportError:
    print("[MT5Bridge] python-dotenv not installed — using environment variables only")

import MetaTrader5 as mt5
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MT5Bridge")

# ── Config ────────────────────────────────────────────────────────────────────
WS_URL        = os.getenv("MIDAS_WS_URL", "ws://localhost:8000/ws/mt5")
MT5_LOGIN     = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD  = os.getenv("MT5_PASSWORD", "")
MT5_SERVER    = os.getenv("MT5_SERVER", "")
SYMBOL        = os.getenv("MT5_SYMBOL", "XAUUSD")
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "1.0"))
DEFAULT_LOT   = float(os.getenv("DEFAULT_LOT", "0.01"))
MAGIC_NUMBER  = 20250101


# ── MT5 Initialisation ────────────────────────────────────────────────────────

def init_mt5() -> bool:
    logger.info("Initialising MetaTrader 5...")

    if not mt5.initialize():
        err = mt5.last_error()
        logger.error(f"mt5.initialize() failed: {err}")
        if err[0] == -6:
            logger.error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error("  FIX: Open MetaTrader 5 and log in FIRST, then re-run this script.")
            logger.error("  The bridge connects to a running MT5 terminal — it cannot start it.")
            logger.error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return False

    terminal = mt5.terminal_info()
    logger.info(f"MT5 terminal: {terminal.name if terminal else 'unknown'}")

    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        logger.info(f"Logging in as account {MT5_LOGIN} on {MT5_SERVER}...")
        ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if not ok:
            err = mt5.last_error()
            logger.error(f"Login failed: {err}")
            logger.error("Check: account number, password, and server name in .env")
            mt5.shutdown()
            return False

        info = mt5.account_info()
        if info:
            logger.info(f"✅ Logged in: {info.name} | {info.server}")
            logger.info(f"   Balance: {info.balance} {info.currency} | Leverage: 1:{info.leverage}")
    else:
        logger.info("No credentials — using currently open MT5 terminal session.")
        info = mt5.account_info()
        if info:
            logger.info(f"✅ Using open session: {info.name} | {info.server}")

    # Auto-detect symbol — try configured name then common variants
    candidates = [SYMBOL, "XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.", "GOLD."]
    resolved = None
    for sym in candidates:
        mt5.symbol_select(sym, True)
        info_sym = mt5.symbol_info(sym)
        if info_sym is not None:
            resolved = sym
            break

    if resolved is None:
        logger.error(f"Could not find symbol. Tried: {candidates}")
        logger.error("Open MT5 → Market Watch, find the gold symbol name, set MT5_SYMBOL in .env")
        return False

    if resolved != SYMBOL:
        logger.warning(f"Symbol '{SYMBOL}' not found — using '{resolved}' instead.")
        # Patch the global so tick_sender uses the right name
        globals()["SYMBOL"] = resolved

    tick = mt5.symbol_info_tick(resolved)
    logger.info(f"✅ Symbol: {resolved} | Bid: {tick.bid if tick else 'N/A'} | Ask: {tick.ask if tick else 'N/A'}")
    return True


# ── Order Execution ───────────────────────────────────────────────────────────

def place_order(signal: dict, max_retries: int = 3, risk_manager=None) -> dict:
    direction = signal.get("direction", "").upper()
    
    # Safely convert to float, handling None values
    try:
        sl  = float(signal.get("stop_loss") or 0)
        tp  = float(signal.get("take_profit_1") or 0)
        lot = float(signal.get("lot") or DEFAULT_LOT)
    except (ValueError, TypeError) as e:
        return {"status": "error", "reason": f"Invalid numeric value in signal: {e}"}

    if direction not in ("BUY", "SELL"):
        return {"status": "skipped", "reason": f"direction={direction}"}
    
    if sl == 0 or tp == 0:
        return {"status": "error", "reason": "Stop loss and take profit are required"}
    
    # ── RISK MANAGEMENT CHECKS ────────────────────────────────────────────────
    
    if risk_manager:
        # 1. Always calculate optimal lot size first
        entry_price = float(signal.get("entry_price", 0))
        if entry_price > 0:
            lot = risk_manager.calculate_lot_size(entry_price, sl)
        
        # 2. Check if we can open a position with this desired lot
        can_trade, reason = risk_manager.can_open_position(
            direction=direction, 
            symbol=SYMBOL, 
            volume=lot, 
            price=entry_price
        )
        
        # 3. If margin is insufficient, attempt fallback to minimum viable lot size
        if not can_trade and "Insufficient free margin" in reason:
            min_lot = risk_manager.config.min_lot_size
            if lot > min_lot:
                logger.warning(f"⚠️ {reason} — Attempting fallback to minimum lot size ({min_lot})")
                can_trade_min, min_reason = risk_manager.can_open_position(
                    direction=direction, 
                    symbol=SYMBOL, 
                    volume=min_lot, 
                    price=entry_price
                )
                if can_trade_min:
                    lot = min_lot
                    can_trade = True
                    logger.info(f"✅ Adjusted to minimum viable lot size: {lot}")
                else:
                    reason = min_reason  # Update reason to the minimum lot failure
        
        # 4. Final check
        if not can_trade:
            logger.warning(f"⚠️ Risk check failed: {reason}")
            return {"status": "blocked", "reason": reason}
            
        logger.info(f"Risk-adjusted lot size approved: {lot}")
    
    # ──────────────────────────────────────────────────────────────────────────

    # Retry loop for transient errors
    for attempt in range(1, max_retries + 1):
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            if attempt < max_retries:
                logger.warning(f"No tick for {SYMBOL}, retrying... ({attempt}/{max_retries})")
                import time; time.sleep(0.5)
                continue
            return {"status": "error", "reason": f"No tick for {SYMBOL} after {max_retries} attempts"}

        price      = tick.ask if direction == "BUY" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

        # Try filling modes in order — brokers differ (XM uses FOK or RETURN)
        filling_modes = [
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN,
        ]

        for filling in filling_modes:
            request = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       SYMBOL,
                "volume":       lot,
                "type":         order_type,
                "price":        price,
                "sl":           sl,
                "tp":           tp,
                "deviation":    30,
                "magic":        MAGIC_NUMBER,
                "comment":      "Midas AI Signal",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            result = mt5.order_send(request)

            if result is None:
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Order placed: {direction} {lot} {SYMBOL} @ {price} | SL {sl} | TP {tp} | #{result.order}")
                return {"status": "ok", "ticket": result.order, "price": price, "lot_size": lot}

            # Unsupported filling — try next
            if result.retcode in (10030, 10038):  # INVALID_FILL
                logger.debug(f"Filling mode {filling} rejected (retcode {result.retcode}), trying next...")
                continue

            # Requote or price changed — retry with fresh tick
            if result.retcode in (10004, 10013, 10014, 10015):  # REQUOTE, INVALID_PRICE, INVALID_STOPS, INVALID_VOLUME
                if attempt < max_retries:
                    logger.warning(f"Requote/price issue (retcode {result.retcode}), retrying with fresh tick... ({attempt}/{max_retries})")
                    import time; time.sleep(0.3)
                    break  # Break filling loop, retry with new tick
                else:
                    return {"status": "error", "retcode": result.retcode, "comment": result.comment}

            # Any other error — stop trying
            logger.error(f"Order failed: retcode {result.retcode} — {result.comment}")
            return {"status": "error", "retcode": result.retcode, "comment": result.comment}

    return {"status": "error", "reason": "All filling modes rejected by broker"}


# ── WebSocket Client ──────────────────────────────────────────────────────────

async def run(auto_trade: bool = False):
    logger.info(f"Connecting to Midas backend at {WS_URL}...")
    logger.info(f"Auto-trade: {'ENABLED ⚡' if auto_trade else 'DISABLED (display only)'}")

    # Start position monitor if auto-trade is enabled
    position_monitor = None
    if auto_trade:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from app.services.position_monitor import get_position_monitor
            position_monitor = get_position_monitor()
            if position_monitor:
                await position_monitor.start()
        except Exception as e:
            logger.error(f"Failed to start position monitor: {e}")

    async for ws in websockets.connect(WS_URL, ping_interval=20, ping_timeout=10):
        try:
            logger.info("✅ Connected to Midas backend. Streaming ticks...")
            await asyncio.gather(
                tick_sender(ws),
                command_receiver(ws, auto_trade),
            )
        except websockets.ConnectionClosed:
            logger.warning("Connection closed — reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error: {e} — reconnecting in 5s...")
            await asyncio.sleep(5)
        finally:
            # Stop position monitor on disconnect
            if position_monitor and position_monitor.running:
                await position_monitor.stop()


async def tick_sender(ws):
    last_price = None
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick and tick.bid > 0 and tick.ask > 0:
            price = round(tick.bid, 2)
            
            # Spike Guard: Ignore price <= 1.0 or massive jumps (> 1%)
            if price <= 1.0:
                logger.warning(f"⚠️ Ignoring invalid price tick: {price}")
            elif last_price is not None and abs(price - last_price) > (last_price * 0.01):
                logger.warning(f"⚠️ Spike Guard (Local): Ignoring potential bad tick {price} (last: {last_price})")
            else:
                last_price = price
                payload = {
                    "type": "TICK",
                    "data": {
                        "symbol": SYMBOL,
                        "bid":    price,
                        "ask":    round(tick.ask, 2),
                        "spread": round(tick.ask - tick.bid, 2),
                        "time":   datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
                    },
                }
                await ws.send(json.dumps(payload))
        await asyncio.sleep(TICK_INTERVAL)


async def command_receiver(ws, auto_trade: bool):
    # Import database service and risk manager
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from app.services.database import db
        from app.services.risk_manager import get_risk_manager
        risk_manager = get_risk_manager()
    except ImportError:
        logger.warning("Database service not available in bridge")
        db = None
        risk_manager = None
    
    async for raw in ws:
        try:
            payload   = json.loads(raw)
            msg_type  = payload.get("type")
            if msg_type != "SIGNAL":
                continue

            data      = payload.get("data", {})
            signal_id = data.get("signal_id", "unknown")
            direction = data.get("direction", "HOLD")
            action    = payload.get("action")

            logger.info(f"📡 Signal received [{signal_id}]: {direction} | confidence {data.get('confidence')}%")
            logger.info(f"   Entry: {data.get('entry_price')} | SL: {data.get('stop_loss')} | TP1: {data.get('take_profit_1')}")

            if action == "PLACE_ORDER":
                if direction in ("BUY", "SELL"):
                    if auto_trade:
                        result = place_order(data, risk_manager=risk_manager)
                        logger.info(f"   Execution result: {result}")
                        
                        # Log risk event if blocked
                        if result.get("status") == "blocked" and db and db.is_enabled():
                            try:
                                await db.log_risk_event(
                                    event_type="POSITION_BLOCKED",
                                    description=result.get("reason", "Unknown"),
                                    action_taken="Order rejected",
                                    metadata={"signal_id": signal_id, "direction": direction},
                                )
                            except Exception as e:
                                logger.error(f"Failed to log risk event: {e}")
                        
                        # Save order to database if successful
                        if result.get("status") == "ok" and db and db.is_enabled():
                            try:
                                await db.save_order(
                                    signal_id=signal_id,
                                    ticket=result.get("ticket"),
                                    direction=direction,
                                    entry_price=result.get("price"),
                                    stop_loss=float(data.get("stop_loss")),
                                    take_profit=float(data.get("take_profit_1")),
                                    lot_size=result.get("lot_size", float(data.get("lot", DEFAULT_LOT))),
                                    magic_number=MAGIC_NUMBER,
                                    comment="Midas AI Signal",
                                )
                            except Exception as e:
                                logger.error(f"Failed to save order to database: {e}")
                        
                        # Send acknowledgment back to backend
                        ack = {
                            "type": "ACK",
                            "signal_id": signal_id,
                            "status": result.get("status"),
                            "ticket": result.get("ticket"),
                            "price": result.get("price"),
                            "message": result.get("comment") or result.get("reason", ""),
                        }
                        await ws.send(json.dumps(ack))
                        
                        if result.get("status") == "ok":
                            logger.info(f"   ✅ Order #{result.get('ticket')} placed @ {result.get('price')}")
                        elif result.get("status") == "blocked":
                            logger.warning(f"   🚫 Order blocked: {result.get('reason')}")
                        else:
                            logger.error(f"   ❌ Order failed: {result}")
                    else:
                        logger.warning("   ⚠️  Auto-trade is OFF — restart with --auto-trade to execute orders")
                        # Send ACK even when auto-trade is off
                        await ws.send(json.dumps({
                            "type": "ACK",
                            "signal_id": signal_id,
                            "status": "skipped",
                            "message": "Auto-trade is disabled",
                        }))
                else:
                    logger.info("   HOLD signal — no order placed.")
                    await ws.send(json.dumps({
                        "type": "ACK",
                        "signal_id": signal_id,
                        "status": "skipped",
                        "message": "HOLD signal",
                    }))

        except json.JSONDecodeError:
            logger.warning("Received non-JSON message, ignoring.")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Default: auto-trade ON if credentials are configured, OFF otherwise
    # Override with --auto-trade (force on) or --display-only (force off)
    has_credentials = bool(MT5_LOGIN and MT5_PASSWORD and MT5_SERVER)

    if "--display-only" in sys.argv:
        auto_trade = False
    elif "--auto-trade" in sys.argv:
        auto_trade = True
    else:
        # Auto-enable if credentials are set in .env
        auto_trade = has_credentials

    print("\n" + "="*55)
    print("  Midas MT5 Bridge")
    print("="*55)
    print(f"  Account : {MT5_LOGIN or '(from open terminal)'}")
    print(f"  Server  : {MT5_SERVER or '(from open terminal)'}")
    print(f"  Symbol  : {SYMBOL}")
    print(f"  Lot     : {DEFAULT_LOT}")
    print(f"  Backend : {WS_URL}")
    print(f"  Mode    : {'AUTO-TRADE ⚡' if auto_trade else 'Display only'}")
    print("="*55 + "\n")

    # Retry init until MT5 is open
    MAX_RETRIES = 10
    for attempt in range(1, MAX_RETRIES + 1):
        if init_mt5():
            break
        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in 10s... (attempt {attempt}/{MAX_RETRIES})")
            logger.info("→ Open MetaTrader 5 and log in, then the bridge will connect automatically.")
            import time; time.sleep(10)
    else:
        logger.error("Could not initialise MT5 after multiple attempts. Exiting.")
        sys.exit(1)

    try:
        asyncio.run(run(auto_trade=auto_trade))
    except KeyboardInterrupt:
        logger.info("Bridge stopped.")
    finally:
        mt5.shutdown()
