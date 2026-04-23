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
import re
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
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
from app.services.candle_normalization import (
    classify_mt5_candle_error,
    dataframe_to_candle_payload,
    normalize_mt5_rates,
)
from app.services.mt5_access import mt5_access_status, mt5_call

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MT5Bridge")

# Suppress verbose third-party loggers
logging.getLogger("MetaTrader5").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

# ── Config ────────────────────────────────────────────────────────────────────
WS_URL        = os.getenv("MIDAS_WS_URL", "ws://localhost:8000/ws/mt5")
MT5_LOGIN     = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD  = os.getenv("MT5_PASSWORD", "")
MT5_SERVER    = os.getenv("MT5_SERVER", "")
SYMBOL        = os.getenv("MT5_SYMBOL", "XAUUSD")
CANDLE_SYMBOL_OVERRIDE = os.getenv("MT5_CANDLE_SYMBOL", "").strip()
CANDLE_SYMBOL = CANDLE_SYMBOL_OVERRIDE or SYMBOL
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "0.1"))
DEFAULT_LOT   = float(os.getenv("DEFAULT_LOT", "0.01"))
MAGIC_NUMBER  = 20250101
MT5_BROKER_TICK_MAX_AGE_SECONDS = float(os.getenv("MT5_BROKER_TICK_MAX_AGE_SECONDS", "5"))
MT5_PRICE_CHANGE_STALE_SECONDS = float(os.getenv("MT5_PRICE_CHANGE_STALE_SECONDS", "30"))
MT5_ORDER_DEVIATION_POINTS = int(os.getenv("MT5_ORDER_DEVIATION_POINTS", "30"))
MT5_CLOSE_RETRY_ATTEMPTS = int(os.getenv("MT5_CLOSE_RETRY_ATTEMPTS", "3"))
CANDLE_PUSH_INTERVAL = float(os.getenv("CANDLE_PUSH_INTERVAL", "5.0"))
ENABLE_CANDLE_STREAM = os.getenv("ENABLE_CANDLE_STREAM", "true").lower() in {"1", "true", "yes", "on"}
STATE_PUSH_INTERVAL = float(os.getenv("STATE_PUSH_INTERVAL", "5.0"))
BRIDGE_HEARTBEAT_INTERVAL = float(os.getenv("BRIDGE_HEARTBEAT_INTERVAL", "2.0"))
CANDLE_TIMEFRAMES = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "1h": mt5.TIMEFRAME_H1,
    "4h": mt5.TIMEFRAME_H4,
}
CANDLE_BARS = int(os.getenv("CANDLE_BARS", "60"))

BRIDGE_STATUS: dict = {
    "last_tick_at": None,
    "last_tick_error": None,
    "last_broker_tick_time": None,
    "last_price_change_at": None,
    "last_candle_1m_at": None,
    "last_candle_5m_at": None,
    "last_candle_error_1m": None,
    "last_candle_error_5m": None,
    "last_account_snapshot_at": None,
    "last_positions_snapshot_at": None,
    "candle_symbol": None,
    "candle_symbol_candidates": [],
    "candle_probe_results": [],
    "candle_stream_state": "idle",
    "last_candle_bootstrap_at": None,
    "last_candle_bootstrap_result": None,
    "last_candle_push_error_1m": None,
    "last_candle_push_error_5m": None,
    "last_tick_push_at": None,
    "last_tick_push_duration_ms": None,
    "last_candle_push_duration_1m_ms": None,
    "last_candle_push_duration_5m_ms": None,
    "core_feeds_state": "idle",
    "optional_services_state": "idle",
}

TICK_STATE: dict[str, object | None] = {
    "last_broker_tick_time": None,
    "last_bid": None,
    "last_ask": None,
    "last_price_change_at": None,
    "tick_sequence": 0,
    "tick_fresh": False,
    "broker_tick_age_seconds": None,
}

OPTIONAL_SERVICES_LOCK = threading.Lock()
OPTIONAL_SERVICES_STARTED = False
OPTIONAL_SERVICES_TASKS: list[asyncio.Task] = []


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
    if terminal is None:
        logger.error("Failed to get MT5 terminal info")
        return False
    logger.info(f"MT5 terminal: {terminal.name}")

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

    # Auto-detect symbol — prioritize standard XAUUSD naming
    candidates = ["XAUUSD", "GOLDUSD", "XAUUSDm", "XAUUSD.", "GOLD.", "GOLD"]
    resolved = None
    for sym in candidates:
        mt5.symbol_select(sym, True)
        info_sym = mt5.symbol_info(sym)
        if info_sym is not None:
            # Pre-flight check: ensure price is in the reasonable range for Gold (~1500-6500)
            # Higher limit set to accommodate 2026 market environment where Gold > 4800.
            tick = mt5.symbol_info_tick(sym)
            if tick and (1500 < tick.bid < 6500):
                resolved = sym
                break
            else:
                logger.warning(f"Symbol '{sym}' found but price {tick.bid if tick else 'N/A'} is outside normal Gold range. Skipping.")
    
    if resolved is None:
        # Fallback to whatever matches, but warn loudly
        for sym in candidates:
            if mt5.symbol_info(sym):
                resolved = sym
                logger.warning(f"⚠️ Using symbol '{resolved}' despite price anomaly. Chart spikes may occur.")
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
    candle_symbol = _discover_candle_symbol(SYMBOL, resolved, getattr(tick, "symbol", None) if tick else None)
    if candle_symbol:
        globals()["CANDLE_SYMBOL"] = candle_symbol
    else:
        globals()["CANDLE_SYMBOL"] = CANDLE_SYMBOL_OVERRIDE or SYMBOL
    logger.info(f"✅ Symbol: {resolved} | Bid: {tick.bid if tick else 'N/A'} | Ask: {tick.ask if tick else 'N/A'}")
    logger.info(f"✅ Candle symbol: {globals()['CANDLE_SYMBOL'] or 'unresolved'}")
    return True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - parsed).total_seconds(), 0.0)
    except ValueError:
        return None


def _mt5_last_error_payload() -> dict:
    try:
        code, message = mt5.last_error()
        return {"code": code, "message": message}
    except Exception as exc:
        return {"code": None, "message": str(exc)}


def _mt5_last_error_text() -> str:
    err = _mt5_last_error_payload()
    return f"{err.get('code')}:{err.get('message')}"


def _format_mt5_candle_error(prefix: str) -> str:
    raw = _mt5_last_error_text()
    return f"{prefix}:{classify_mt5_candle_error(raw)}:{raw}"


def _broker_tick_time(tick) -> datetime | None:
    tick_time_msc = getattr(tick, "time_msc", None)
    if tick_time_msc:
        try:
            return datetime.fromtimestamp(float(tick_time_msc) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    tick_time = getattr(tick, "time", None)
    if tick_time:
        try:
            return datetime.fromtimestamp(float(tick_time), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    return None


def _tick_freshness(tick) -> tuple[datetime | None, float | None, bool]:
    broker_time = _broker_tick_time(tick)
    if broker_time is None:
        return None, None, False
    age_seconds = max((datetime.now(timezone.utc) - broker_time).total_seconds(), 0.0)
    return broker_time, age_seconds, age_seconds <= MT5_BROKER_TICK_MAX_AGE_SECONDS


def _track_tick_state(tick, *, bid: float, ask: float) -> dict:
    broker_time, age_seconds, tick_fresh = _tick_freshness(tick)
    broker_time_iso = broker_time.isoformat() if broker_time else None
    price_changed = TICK_STATE.get("last_bid") != bid or TICK_STATE.get("last_ask") != ask
    broker_time_changed = TICK_STATE.get("last_broker_tick_time") != broker_time_iso

    if price_changed:
        TICK_STATE["last_price_change_at"] = _utc_now_iso()
        _set_status("last_price_change_at", TICK_STATE["last_price_change_at"])
    if broker_time_changed:
        TICK_STATE["tick_sequence"] = int(TICK_STATE.get("tick_sequence") or 0) + 1

    TICK_STATE["last_bid"] = bid
    TICK_STATE["last_ask"] = ask
    TICK_STATE["last_broker_tick_time"] = broker_time_iso
    TICK_STATE["broker_tick_age_seconds"] = age_seconds
    TICK_STATE["tick_fresh"] = tick_fresh
    _set_status("last_broker_tick_time", broker_time_iso)

    return {
        "broker_tick_time": broker_time_iso,
        "broker_tick_age_seconds": age_seconds,
        "tick_sequence": int(TICK_STATE.get("tick_sequence") or 0),
        "price_changed_at": TICK_STATE.get("last_price_change_at"),
        "tick_fresh": tick_fresh,
    }


def _execution_blockers(auto_trade: bool) -> list[str]:
    blockers: list[str] = []
    terminal_ok = mt5.terminal_info() is not None
    account_ok = mt5_call(
        "bridge.execution_blockers.account_info",
        lambda: mt5.account_info() is not None,
        warn_threshold_ms=250,
    ) if terminal_ok else False
    if not terminal_ok or not account_ok:
        blockers.append("mt5_not_initialized")
    if not auto_trade:
        blockers.append("auto_trade_disabled")
    if not TICK_STATE.get("tick_fresh"):
        blockers.append("broker_tick_stale")
    price_changed_at = TICK_STATE.get("last_price_change_at")
    price_change_age = _iso_age_seconds(str(price_changed_at)) if price_changed_at else None
    if price_change_age is None:
        blockers.append("broker_tick_not_advancing")
    elif price_change_age > MT5_PRICE_CHANGE_STALE_SECONDS:
        blockers.append("broker_tick_not_advancing")
    candle_1m_age = _iso_age_seconds(BRIDGE_STATUS.get("last_candle_1m_at"))
    candle_5m_age = _iso_age_seconds(BRIDGE_STATUS.get("last_candle_5m_at"))
    account_age = _iso_age_seconds(BRIDGE_STATUS.get("last_account_snapshot_at"))
    positions_age = _iso_age_seconds(BRIDGE_STATUS.get("last_positions_snapshot_at"))
    if ENABLE_CANDLE_STREAM and not BRIDGE_STATUS.get("candle_symbol"):
        blockers.append("no_candle_symbol_resolved")
    if ENABLE_CANDLE_STREAM and BRIDGE_STATUS.get("candle_stream_state") == "warming_up":
        blockers.append("candle_bootstrap_pending")
    if ENABLE_CANDLE_STREAM:
        if candle_1m_age is None or candle_1m_age > 20:
            blockers.append("missing_1m_candles")
        if candle_5m_age is None or candle_5m_age > 20:
            blockers.append("missing_5m_candles")
    else:
        blockers.extend(["missing_1m_candles", "missing_5m_candles"])
    if account_age is None or account_age > 30:
        blockers.append("missing_account_snapshot")
    if positions_age is None or positions_age > 30:
        blockers.append("missing_position_snapshot")
    return blockers


def _classify_execution_blockers(reason: str | None) -> list[str]:
    text = str(reason or "").lower()
    blockers: list[str] = []
    if "max concurrent positions" in text:
        blockers.append("max_concurrent_positions")
    if "insufficient free margin" in text:
        blockers.append("insufficient_margin")
    if "daily loss" in text:
        blockers.append("daily_loss_limit")
    if "risk" in text and not blockers:
        blockers.append("risk_blocked")
    if "invalid stops" in text or "retcode 10016" in text:
        blockers.append("invalid_stops")
    if "tick" in text and "stale" in text:
        blockers.append("broker_tick_stale")
    if "symbol" in text and "match" in text:
        blockers.append("symbol_mismatch")
    return blockers


_STATUS_NOW = object()


def _set_status(key: str, value: str | None | object = _STATUS_NOW) -> None:
    BRIDGE_STATUS[key] = _utc_now_iso() if value is _STATUS_NOW else value


def _set_candle_stream_state(state: str, *, result: str | None = None) -> None:
    BRIDGE_STATUS["candle_stream_state"] = state
    BRIDGE_STATUS["core_feeds_state"] = state
    if result is not None:
        BRIDGE_STATUS["last_candle_bootstrap_result"] = result


def _refresh_core_feeds_state() -> None:
    tick_age = _iso_age_seconds(BRIDGE_STATUS.get("last_tick_push_at"))
    candle_1m_age = _iso_age_seconds(BRIDGE_STATUS.get("last_candle_1m_at"))
    candle_5m_age = _iso_age_seconds(BRIDGE_STATUS.get("last_candle_5m_at"))
    if (
        tick_age is not None
        and tick_age <= 5
        and candle_1m_age is not None
        and candle_1m_age <= 20
        and candle_5m_age is not None
        and candle_5m_age <= 20
    ):
        BRIDGE_STATUS["core_feeds_state"] = "ready"
    elif BRIDGE_STATUS.get("candle_stream_state") == "warming_up":
        BRIDGE_STATUS["core_feeds_state"] = "warming_up"
    else:
        BRIDGE_STATUS["core_feeds_state"] = "degraded"


def _reset_candle_stream_status() -> None:
    for key in (
        "last_candle_1m_at",
        "last_candle_5m_at",
        "last_candle_error_1m",
        "last_candle_error_5m",
        "last_candle_push_error_1m",
        "last_candle_push_error_5m",
    ):
        BRIDGE_STATUS[key] = None
    _set_status("last_candle_bootstrap_at")
    _set_candle_stream_state("warming_up", result="warming_up")


def _tick_failure_reason(symbol: str) -> str:
    try:
        if mt5.terminal_info() is None:
            return "mt5_terminal_unavailable"
        if mt5_call("bridge.tick_failure.account_info", lambda: mt5.account_info(), warn_threshold_ms=250) is None:
            return "mt5_account_unavailable"
        info = mt5.symbol_info(symbol)
        if info is None:
            return "broker_symbol_not_found"
        if not getattr(info, "visible", False):
            mt5.symbol_select(symbol, True)
        tick = mt5_call(
            "bridge.tick_failure.symbol_info_tick",
            lambda: mt5.symbol_info_tick(symbol),
            warn_threshold_ms=250,
        )
        if tick is None:
            return "broker_returned_no_tick"
        if float(getattr(tick, "bid", 0.0) or 0.0) <= 0 or float(getattr(tick, "ask", 0.0) or 0.0) <= 0:
            return "broker_tick_invalid_bid_ask"
        return "unknown_tick_blocker"
    except Exception as exc:
        return f"tick_check_error:{exc}"


def _gold_symbol_candidates(*preferred: str | None) -> list[str]:
    candidates: list[str] = []
    for symbol in [CANDLE_SYMBOL_OVERRIDE or None, *preferred, SYMBOL, "XAUUSD", "GOLD", "GOLDUSD", "XAUUSDm", "XAUUSD."]:
        normalized = str(symbol or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _probe_candles(symbol: str, timeframe: str, count: int = 10) -> tuple[int, str | None]:
    tf = CANDLE_TIMEFRAMES.get(timeframe)
    if tf is None:
        return 0, f"unsupported_timeframe:{timeframe}"
    try:
        def _copy():
            mt5.symbol_select(symbol, True)
            return mt5.copy_rates_from_pos(symbol, tf, 0, count)

        rates = mt5_call(
            f"bridge.probe_candles.{timeframe}",
            _copy,
            warn_threshold_ms=250,
        )
        if rates is None:
            return 0, _format_mt5_candle_error("mt5_copy_rates_none")
        if len(rates) == 0:
            return 0, _format_mt5_candle_error("mt5_copy_rates_empty")
        return len(rates), None
    except Exception as exc:
        return 0, f"mt5_copy_rates_error:{exc}"


def _discover_candle_symbol(*preferred: str | None) -> str | None:
    candidates = _gold_symbol_candidates(*preferred)
    BRIDGE_STATUS["candle_symbol_candidates"] = candidates
    probe_results: list[dict] = []
    last_errors: dict[str, dict[str, str | None]] = {}
    for candidate in candidates:
        one_count, one_error = _probe_candles(candidate, "1m")
        five_count, five_error = _probe_candles(candidate, "5m")
        last_errors[candidate] = {"1m": one_error, "5m": five_error}
        probe_results.append(
            {
                "symbol": candidate,
                "timeframes": {
                    "1m": {"count": one_count, "error": one_error},
                    "5m": {"count": five_count, "error": five_error},
                },
            }
        )
        logger.info(
            "Candle probe %s: 1m=%s%s 5m=%s%s",
            candidate,
            one_count,
            f" ({one_error})" if one_error else "",
            five_count,
            f" ({five_error})" if five_error else "",
        )
        if one_count > 0 and five_count > 0:
            BRIDGE_STATUS["candle_probe_results"] = probe_results
            BRIDGE_STATUS["candle_symbol"] = candidate
            _set_status("last_candle_error_1m", None)
            _set_status("last_candle_error_5m", None)
            logger.info(f"✅ Candle symbol resolved: {candidate} (execution symbol: {SYMBOL})")
            return candidate

    BRIDGE_STATUS["candle_probe_results"] = probe_results
    BRIDGE_STATUS["candle_symbol"] = None
    _set_status("last_candle_error_1m", "no_candle_symbol_resolved")
    _set_status("last_candle_error_5m", "no_candle_symbol_resolved")
    logger.error(f"No usable MT5 candle symbol found. Probe errors: {last_errors}")
    return None


def candle_probe_report(*preferred: str | None) -> dict:
    candidates = _gold_symbol_candidates(*preferred)
    results: list[dict] = []
    for candidate in candidates:
        frame_results = {}
        for timeframe in ("1m", "5m", "15m"):
            count, error = _probe_candles(candidate, timeframe)
            frame_results[timeframe] = {"count": count, "error": error}
        results.append({"symbol": candidate, "timeframes": frame_results})
    selected = next(
        (
            item["symbol"]
            for item in results
            if item["timeframes"]["1m"]["count"] > 0 and item["timeframes"]["5m"]["count"] > 0
        ),
        None,
    )
    return {"selected_candle_symbol": selected, "candidates": results}


def _bridge_status_payload(auto_trade: bool) -> dict:
    _refresh_core_feeds_state()
    terminal_ok = mt5.terminal_info() is not None
    account_ok = mt5_call(
        "bridge.status.account_info",
        lambda: mt5.account_info() is not None,
        warn_threshold_ms=250,
    ) if terminal_ok else False
    blockers = _execution_blockers(auto_trade)
    mt5_status = mt5_access_status()
    payload = {
        "connected": True,
        "mt5_initialized": terminal_ok and account_ok,
        "broker_symbol": SYMBOL,
        "execution_symbol": SYMBOL,
        "candle_symbol": CANDLE_SYMBOL,
        "candle_symbol_candidates": BRIDGE_STATUS.get("candle_symbol_candidates", []),
        "candle_probe_results": BRIDGE_STATUS.get("candle_probe_results", []),
        "candle_stream_state": BRIDGE_STATUS.get("candle_stream_state"),
        "last_candle_bootstrap_at": BRIDGE_STATUS.get("last_candle_bootstrap_at"),
        "last_candle_bootstrap_result": BRIDGE_STATUS.get("last_candle_bootstrap_result"),
        "last_tick_at": BRIDGE_STATUS.get("last_tick_at"),
        "last_tick_error": BRIDGE_STATUS.get("last_tick_error"),
        "last_broker_tick_time": BRIDGE_STATUS.get("last_broker_tick_time"),
        "broker_tick_age_seconds": TICK_STATE.get("broker_tick_age_seconds"),
        "tick_sequence": TICK_STATE.get("tick_sequence"),
        "tick_fresh": TICK_STATE.get("tick_fresh"),
        "last_price_change_at": BRIDGE_STATUS.get("last_price_change_at"),
        "last_candle_1m_at": BRIDGE_STATUS.get("last_candle_1m_at"),
        "last_candle_5m_at": BRIDGE_STATUS.get("last_candle_5m_at"),
        "last_candle_error_1m": BRIDGE_STATUS.get("last_candle_error_1m"),
        "last_candle_error_5m": BRIDGE_STATUS.get("last_candle_error_5m"),
        "last_candle_push_error_1m": BRIDGE_STATUS.get("last_candle_push_error_1m"),
        "last_candle_push_error_5m": BRIDGE_STATUS.get("last_candle_push_error_5m"),
        "last_tick_push_at": BRIDGE_STATUS.get("last_tick_push_at"),
        "last_tick_push_duration_ms": BRIDGE_STATUS.get("last_tick_push_duration_ms"),
        "last_candle_push_duration_1m_ms": BRIDGE_STATUS.get("last_candle_push_duration_1m_ms"),
        "last_candle_push_duration_5m_ms": BRIDGE_STATUS.get("last_candle_push_duration_5m_ms"),
        "core_feeds_state": BRIDGE_STATUS.get("core_feeds_state"),
        "optional_services_state": BRIDGE_STATUS.get("optional_services_state"),
        "account_snapshot_at": BRIDGE_STATUS.get("last_account_snapshot_at"),
        "positions_snapshot_at": BRIDGE_STATUS.get("last_positions_snapshot_at"),
        "auto_trade_enabled": auto_trade,
        "candle_stream_enabled": ENABLE_CANDLE_STREAM,
        "execution_ready": not blockers,
        "execution_blockers": blockers,
        "heartbeat_at": _utc_now_iso(),
    }
    payload.update(mt5_status)
    return payload


# ── Order Execution ───────────────────────────────────────────────────────────

_GOLD_PATTERNS = (
    re.compile(r"^GOLD$", re.IGNORECASE),
    re.compile(r"^XAUUSD[A-Z]?$", re.IGNORECASE),
    re.compile(r"^GOLDUSD$", re.IGNORECASE),
    re.compile(r"^GC[A-Z0-9]+$", re.IGNORECASE),
)


def _normalize_order_symbol(symbol: str | None) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", (symbol or "").upper())
    for pattern in _GOLD_PATTERNS:
        if pattern.match(cleaned):
            return "XAUUSD"
    return cleaned


def _symbols_equivalent(left: str | None, right: str | None) -> bool:
    left_normalized = _normalize_order_symbol(left)
    right_normalized = _normalize_order_symbol(right)
    return bool(left_normalized and right_normalized and left_normalized == right_normalized)


def _mt5_symbol_exists(symbol: str | None) -> bool:
    if not symbol:
        return False
    try:
        def _exists():
            mt5.symbol_select(symbol, True)
            return mt5.symbol_info(symbol) is not None

        return mt5_call("bridge.symbol_exists", _exists, warn_threshold_ms=250)
    except Exception:
        return False


def _resolve_order_symbol(signal: dict) -> str:
    display_symbol = signal.get("symbol")
    for candidate in (
        signal.get("broker_symbol"),
        signal.get("execution_symbol"),
        SYMBOL if _symbols_equivalent(display_symbol, SYMBOL) else None,
        display_symbol,
        SYMBOL,
    ):
        if _mt5_symbol_exists(candidate):
            return candidate
    return signal.get("broker_symbol") or signal.get("execution_symbol") or SYMBOL or display_symbol

class MT5OrderRouter:
    """Single bridge-owned order path for opening, closing, and reversing MT5 positions."""

    filling_modes = (
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_RETURN,
    )

    retryable_retcodes = (10004, 10013, 10014, 10015)
    invalid_fill_retcodes = (10030, 10038)

    def __init__(self, *, db=None, risk_manager=None):
        self.db = db
        self.risk_manager = risk_manager

    def execute(self, signal: dict) -> dict:
        direction = str(signal.get("direction", "HOLD")).upper()
        position_action = str(signal.get("position_action") or "open").lower()
        trade_symbol = _resolve_order_symbol(signal)

        if bool(signal.get("is_duplicate")) or position_action == "ignore":
            return {
                "status": "skipped",
                "stage": "precheck",
                "action": position_action,
                "reason": signal.get("position_action_reason") or "Signal suppressed by position manager",
                "broker_symbol": trade_symbol,
                "execution_symbol": trade_symbol,
            }

        if position_action == "close":
            return self.close_positions(trade_symbol, close_reason="position_manager_close", action="close")

        if direction not in ("BUY", "SELL"):
            return {
                "status": "skipped",
                "stage": "precheck",
                "action": position_action,
                "reason": "HOLD signal",
                "broker_symbol": trade_symbol,
                "execution_symbol": trade_symbol,
            }

        if position_action == "reverse":
            close_result = self.close_positions(
                trade_symbol,
                close_reason="position_manager_reverse",
                action="reverse",
            )
            if close_result.get("status") == "error":
                close_result["stage"] = "close"
                close_result["action"] = "reverse"
                return close_result
            open_result = self.open(signal, action="reverse")
            if close_result.get("closed_tickets"):
                open_result["closed_tickets"] = close_result["closed_tickets"]
            return open_result

        return self.open(signal, action=position_action)

    def _fresh_tick(self, symbol: str) -> tuple[object | None, dict | None]:
        def _read_tick():
            mt5.symbol_select(symbol, True)
            return mt5.symbol_info_tick(symbol)

        tick = mt5_call("bridge.order_router.fresh_tick", _read_tick, warn_threshold_ms=250)
        if tick is None:
            return None, {
                "status": "error",
                "stage": "tick",
                "reason": f"No tick for {symbol}",
                "last_error": _mt5_last_error_payload(),
                "broker_symbol": symbol,
                "execution_symbol": symbol,
            }
        if float(getattr(tick, "bid", 0.0) or 0.0) <= 0 or float(getattr(tick, "ask", 0.0) or 0.0) <= 0:
            return None, {
                "status": "error",
                "stage": "tick",
                "reason": f"Invalid bid/ask for {symbol}",
                "last_error": _mt5_last_error_payload(),
                "broker_symbol": symbol,
                "execution_symbol": symbol,
            }
        broker_time, age_seconds, tick_fresh = _tick_freshness(tick)
        if not tick_fresh:
            return None, {
                "status": "error",
                "stage": "tick",
                "reason": f"Broker tick for {symbol} is stale",
                "broker_tick_time": broker_time.isoformat() if broker_time else None,
                "broker_tick_age_seconds": age_seconds,
                "last_error": _mt5_last_error_payload(),
                "broker_symbol": symbol,
                "execution_symbol": symbol,
            }
        return tick, None

    def _risk_adjusted_lot(self, signal: dict, *, direction: str, trade_symbol: str, sl: float) -> tuple[float | None, dict | None]:
        try:
            lot = float(signal.get("lot") or DEFAULT_LOT)
        except (ValueError, TypeError) as exc:
            return None, {"status": "error", "stage": "precheck", "reason": f"Invalid lot: {exc}"}

        if not self.risk_manager:
            return lot, None

        entry_price = float(signal.get("entry_price") or 0.0)
        if entry_price > 0:
            lot = self.risk_manager.calculate_lot_size(entry_price, sl)
            lot = self.risk_manager.calculate_lot_size_from_shadow_performance(
                setup_type=signal.get("setup_type"),
                base_lot_size=lot,
            )
        lot_multiplier = float(signal.get("lot_multiplier") or 1.0)
        if signal.get("position_action") == "scale_in" and "lot_multiplier" not in signal:
            lot_multiplier = float(os.getenv("SCALE_IN_LOT_FRACTION", "0.5"))
        lot = round(max(self.risk_manager.config.min_lot_size, lot * lot_multiplier), 2)

        can_trade, reason = self.risk_manager.can_open_position(
            direction=direction,
            symbol=trade_symbol,
            volume=lot,
            price=entry_price,
        )
        if not can_trade and "Insufficient free margin" in reason:
            min_lot = self.risk_manager.config.min_lot_size
            if lot > min_lot:
                can_trade_min, min_reason = self.risk_manager.can_open_position(
                    direction=direction,
                    symbol=trade_symbol,
                    volume=min_lot,
                    price=entry_price,
                )
                if can_trade_min:
                    lot = min_lot
                    can_trade = True
                else:
                    reason = min_reason

        if not can_trade:
            return None, {
                "status": "blocked",
                "stage": "risk",
                "reason": reason,
                "execution_blockers": _classify_execution_blockers(reason) or ["risk_blocked"],
            }
        return lot, None

    def open(self, signal: dict, *, action: str = "open", max_retries: int = 3) -> dict:
        direction = str(signal.get("direction", "")).upper()
        display_symbol = signal.get("symbol") or SYMBOL
        trade_symbol = _resolve_order_symbol(signal)
        if display_symbol != trade_symbol:
            logger.info(f"Execution symbol resolved: display={display_symbol} broker={trade_symbol}")

        try:
            sl = float(signal.get("stop_loss") or 0)
            tp = float(signal.get("take_profit_1") or 0)
        except (ValueError, TypeError) as exc:
            return {"status": "error", "stage": "precheck", "action": action, "reason": f"Invalid numeric value in signal: {exc}"}

        if direction not in ("BUY", "SELL"):
            return {"status": "skipped", "stage": "precheck", "action": action, "reason": f"direction={direction}"}
        if sl == 0 or tp == 0:
            return {"status": "error", "stage": "precheck", "action": action, "reason": "Stop loss and take profit are required"}

        lot, risk_error = self._risk_adjusted_lot(signal, direction=direction, trade_symbol=trade_symbol, sl=sl)
        if risk_error:
            risk_error.update({"action": action, "broker_symbol": trade_symbol, "execution_symbol": trade_symbol})
            return risk_error

        last_error: dict | None = None
        for attempt in range(1, max_retries + 1):
            tick, tick_error = self._fresh_tick(trade_symbol)
            if tick_error:
                last_error = tick_error
                if attempt < max_retries:
                    import time
                    time.sleep(0.3)
                    continue
                tick_error["action"] = action
                return tick_error

            price = float(tick.ask if direction == "BUY" else tick.bid)
            spread = round(float(tick.ask - tick.bid), 4)
            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

            for filling in self.filling_modes:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": trade_symbol,
                    "volume": lot,
                    "type": order_type,
                    "price": price,
                    "sl": sl,
                    "tp": tp,
                    "deviation": MT5_ORDER_DEVIATION_POINTS,
                    "magic": MAGIC_NUMBER,
                    "comment": f"Midas AI Signal [{action}]",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling,
                }
                result = mt5_call(
                    "bridge.order_router.open_order_send",
                    lambda req=request: mt5.order_send(req),
                    warn_threshold_ms=1000,
                )
                if result is None:
                    last_error = {
                        "status": "error",
                        "stage": "open",
                        "action": action,
                        "reason": "MT5 order_send returned no result while opening",
                        "last_error": _mt5_last_error_payload(),
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                    }
                    continue
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    intended_entry = float(signal.get("entry_price") or price)
                    slippage_points = (price - intended_entry) if direction == "BUY" else (intended_entry - price)
                    return {
                        "status": "ok",
                        "stage": "open",
                        "action": action,
                        "ticket": result.order,
                        "opened_ticket": result.order,
                        "price": price,
                        "lot_size": lot,
                        "spread": spread,
                        "slippage_points": slippage_points,
                        "symbol": display_symbol,
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                        "retcode": result.retcode,
                        "comment": result.comment,
                    }
                if result.retcode in self.invalid_fill_retcodes:
                    last_error = {"status": "error", "stage": "open", "action": action, "retcode": result.retcode, "comment": result.comment}
                    continue
                if result.retcode in self.retryable_retcodes and attempt < max_retries:
                    last_error = {"status": "error", "stage": "open", "action": action, "retcode": result.retcode, "comment": result.comment}
                    break
                return {
                    "status": "error",
                    "stage": "open",
                    "action": action,
                    "retcode": result.retcode,
                    "comment": result.comment,
                    "broker_symbol": trade_symbol,
                    "execution_symbol": trade_symbol,
                }

        return last_error or {
            "status": "error",
            "stage": "open",
            "action": action,
            "reason": "All filling modes rejected by broker",
            "broker_symbol": trade_symbol,
            "execution_symbol": trade_symbol,
        }

    def close_single_position(self, pos, *, close_reason: str, action: str = "close") -> dict:
        trade_symbol = str(getattr(pos, "symbol", "") or SYMBOL)
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        last_error: dict | None = None

        for attempt in range(1, MT5_CLOSE_RETRY_ATTEMPTS + 1):
            tick, tick_error = self._fresh_tick(trade_symbol)
            if tick_error:
                last_error = tick_error
                if attempt < MT5_CLOSE_RETRY_ATTEMPTS:
                    import time
                    time.sleep(0.3)
                    continue
                tick_error.update({"stage": "close", "action": action, "ticket": int(pos.ticket)})
                return tick_error

            price = float(tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask)
            for filling in self.filling_modes:
                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": trade_symbol,
                    "volume": pos.volume,
                    "type": order_type,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": MT5_ORDER_DEVIATION_POINTS,
                    "magic": pos.magic,
                    "comment": f"Position manager - {close_reason}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling,
                }

                result = mt5_call(
                    "bridge.order_router.close_order_send",
                    lambda req=close_request: mt5.order_send(req),
                    warn_threshold_ms=1000,
                )
                if result is None:
                    last_error = {
                        "status": "error",
                        "stage": "close",
                        "action": action,
                        "ticket": int(pos.ticket),
                        "reason": f"Failed to close position #{pos.ticket}: no result",
                        "last_error": _mt5_last_error_payload(),
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                    }
                    continue
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    close_price = getattr(result, "price", None) or price
                    logger.info(
                        f"✅ Position closed: #{pos.ticket} {trade_symbol} | Reason: {close_reason} | Profit: ${float(getattr(result, 'profit', 0.0) or 0.0):.2f}"
                    )
                    if self.db and self.db.is_enabled():
                        try:
                            self.db.update_order_close(
                                ticket=int(pos.ticket),
                                close_price=close_price,
                                profit=float(getattr(result, "profit", getattr(pos, "profit", 0.0)) or 0.0),
                                commission=float(getattr(result, "commission", 0.0) or 0.0),
                                swap=float(getattr(pos, "swap", 0.0) or 0.0),
                                close_reason=close_reason,
                            )
                            from app.services.signal_feedback import signal_feedback_store

                            signal_feedback_store.record_outcome(int(pos.ticket))
                        except Exception as exc:
                            logger.error(f"Failed to persist close for #{pos.ticket}: {exc}")
                    return {
                        "status": "ok",
                        "stage": "close",
                        "action": action,
                        "ticket": int(pos.ticket),
                        "symbol": trade_symbol,
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                        "close_price": close_price,
                        "profit": float(getattr(result, "profit", getattr(pos, "profit", 0.0)) or 0.0),
                        "retcode": result.retcode,
                        "comment": result.comment,
                    }
                if result.retcode in self.invalid_fill_retcodes:
                    last_error = {
                        "status": "error",
                        "stage": "close",
                        "action": action,
                        "ticket": int(pos.ticket),
                        "retcode": result.retcode,
                        "comment": result.comment,
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                    }
                    continue
                if result.retcode in self.retryable_retcodes and attempt < MT5_CLOSE_RETRY_ATTEMPTS:
                    last_error = {
                        "status": "error",
                        "stage": "close",
                        "action": action,
                        "ticket": int(pos.ticket),
                        "retcode": result.retcode,
                        "comment": result.comment,
                        "broker_symbol": trade_symbol,
                        "execution_symbol": trade_symbol,
                    }
                    break
                return {
                    "status": "error",
                    "stage": "close",
                    "action": action,
                    "ticket": int(pos.ticket),
                    "reason": f"Failed to close position #{pos.ticket}: {result.comment}",
                    "retcode": result.retcode,
                    "comment": result.comment,
                    "broker_symbol": trade_symbol,
                    "execution_symbol": trade_symbol,
                }

        return last_error or {
            "status": "error",
            "stage": "close",
            "action": action,
            "ticket": int(pos.ticket),
            "reason": f"Failed to close position #{pos.ticket}: all filling modes rejected",
            "broker_symbol": trade_symbol,
            "execution_symbol": trade_symbol,
        }

    def close_positions(self, symbol: str, *, close_reason: str, action: str = "close") -> dict:
        target_symbol = symbol or SYMBOL
        positions = mt5_call(
            "bridge.order_router.close_positions_get",
            lambda: mt5.positions_get(magic=MAGIC_NUMBER) or [],
            warn_threshold_ms=1000,
        )
        matching_positions = [
            pos
            for pos in positions
            if _symbols_equivalent(target_symbol, str(getattr(pos, "symbol", "")))
        ]

        if not matching_positions:
            return {
                "status": "skipped",
                "stage": "close",
                "action": action,
                "reason": f"No open positions for {target_symbol}",
                "broker_symbol": target_symbol,
                "execution_symbol": target_symbol,
            }

        closed_tickets: list[int] = []
        failures: list[str] = []
        failure_details: list[dict] = []
        for pos in matching_positions:
            close_result = self.close_single_position(pos, close_reason=close_reason, action=action)
            if close_result.get("status") == "ok":
                closed_tickets.append(int(close_result["ticket"]))
            else:
                failures.append(str(close_result.get("reason") or close_result.get("comment") or f"Failed to close #{pos.ticket}"))
                failure_details.append(close_result)

        if failures:
            return {
                "status": "error",
                "stage": "close",
                "action": action,
                "reason": "; ".join(failures),
                "closed_tickets": closed_tickets,
                "failure_details": failure_details,
                "broker_symbol": target_symbol,
                "execution_symbol": target_symbol,
            }

        return {
            "status": "closed",
            "stage": "close",
            "action": action,
            "message": f"Closed {len(closed_tickets)} position(s) for {target_symbol}",
            "closed_tickets": closed_tickets,
            "broker_symbol": target_symbol,
            "execution_symbol": target_symbol,
        }


def place_order(signal: dict, max_retries: int = 3, risk_manager=None) -> dict:
    return MT5OrderRouter(risk_manager=risk_manager).open(signal, max_retries=max_retries)


def _update_position_decision_execution(signal_id: str | None, result: dict, db=None) -> None:
    if not signal_id or not db or not db.is_enabled():
        return

    def _do_update():
        try:
            status = str(result.get("status") or "").lower()
            execution_result = result.get("comment") or result.get("reason") or result.get("message") or status
            db.update_position_decision_execution(
                signal_id=signal_id,
                executed=status in {"ok", "closed"},
                execution_result=execution_result,
            )
        except Exception as exc:
            logger.error(f"Failed to update position decision execution: {exc}")

    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _do_update)
    except RuntimeError:
        _do_update()


def _close_single_position(pos, *, close_reason: str, db=None) -> dict:
    return MT5OrderRouter(db=db).close_single_position(pos, close_reason=close_reason)


def close_positions_for_symbol(symbol: str, *, close_reason: str, db=None) -> dict:
    return MT5OrderRouter(db=db).close_positions(symbol, close_reason=close_reason)


def _fetch_candles(symbol: str, timeframe: str, count: int = CANDLE_BARS) -> list[dict]:
    tf = CANDLE_TIMEFRAMES.get(timeframe)
    if tf is None:
        if timeframe in {"1m", "5m"}:
            error = f"unsupported_timeframe:{timeframe}"
            _set_status(f"last_candle_error_{timeframe}", error)
            BRIDGE_STATUS[f"last_candle_push_error_{timeframe}"] = error
        return []

    try:
        def _copy():
            mt5.symbol_select(symbol, True)
            return mt5.copy_rates_from_pos(symbol, tf, 0, count)

        rates = mt5_call(
            f"bridge.fetch_candles.{timeframe}",
            _copy,
            warn_threshold_ms=250,
        )
        if rates is None:
            error = _format_mt5_candle_error("mt5_copy_rates_none")
            if timeframe in {"1m", "5m"}:
                _set_status(f"last_candle_error_{timeframe}", error)
                BRIDGE_STATUS[f"last_candle_push_error_{timeframe}"] = error
            logger.warning(f"MT5 returned no candle result for {symbol} {timeframe}: {error}")
            return []
        if len(rates) == 0:
            error = _format_mt5_candle_error("mt5_copy_rates_empty")
            if timeframe in {"1m", "5m"}:
                _set_status(f"last_candle_error_{timeframe}", error)
                BRIDGE_STATUS[f"last_candle_push_error_{timeframe}"] = error
            logger.warning(f"MT5 returned empty candles for {symbol} {timeframe}: {error}")
            return []

        normalized_df, metadata = normalize_mt5_rates(rates, timeframe=timeframe, repair_gaps=True)
        payload = dataframe_to_candle_payload(normalized_df)
        if timeframe in {"1m", "5m"}:
            error = "forward_fill_applied" if metadata.get("has_forward_fill") else None
            _set_status(f"last_candle_error_{timeframe}", error)
            BRIDGE_STATUS[f"last_candle_push_error_{timeframe}"] = error
        return payload
    except Exception as exc:
        if timeframe in {"1m", "5m"}:
            error = f"mt5_copy_rates_error:{exc}"
            _set_status(f"last_candle_error_{timeframe}", error)
            BRIDGE_STATUS[f"last_candle_push_error_{timeframe}"] = error
        logger.warning(f"Failed to fetch candles for {symbol} {timeframe}: {exc}")
        return []


def _account_snapshot() -> dict | None:
    account = mt5_call(
        "bridge.account_snapshot.account_info",
        lambda: mt5.account_info(),
        warn_threshold_ms=250,
    )
    if account is None:
        return None
    data = account._asdict() if hasattr(account, "_asdict") else {}
    return {
        "login": data.get("login", getattr(account, "login", None)),
        "server": data.get("server", getattr(account, "server", None)),
        "name": data.get("name", getattr(account, "name", None)),
        "currency": data.get("currency", getattr(account, "currency", None)),
        "balance": float(data.get("balance", getattr(account, "balance", 0.0)) or 0.0),
        "equity": float(data.get("equity", getattr(account, "equity", 0.0)) or 0.0),
        "margin": float(data.get("margin", getattr(account, "margin", 0.0)) or 0.0),
        "margin_free": float(data.get("margin_free", getattr(account, "margin_free", 0.0)) or 0.0),
        "margin_level": float(data.get("margin_level", getattr(account, "margin_level", 0.0)) or 0.0),
        "profit": float(data.get("profit", getattr(account, "profit", 0.0)) or 0.0),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def _positions_snapshot() -> list[dict]:
    positions = mt5_call(
        "bridge.positions_snapshot.positions_get",
        lambda: mt5.positions_get() or [],
        warn_threshold_ms=250,
    )
    snapshot: list[dict] = []
    for pos in positions:
        direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        current_price = float(getattr(pos, "price_current", 0.0) or 0.0)
        if current_price <= 0:
            tick = mt5_call(
                "bridge.positions_snapshot.symbol_info_tick",
                lambda sym=pos.symbol: mt5.symbol_info_tick(sym),
                warn_threshold_ms=250,
            )
            if tick:
                current_price = float(tick.bid if direction == "BUY" else tick.ask)
        snapshot.append(
            {
                "ticket": int(pos.ticket),
                "symbol": str(pos.symbol),
                "broker_symbol": str(pos.symbol),
                "direction": direction,
                "type": int(pos.type),
                "entry_price": float(pos.price_open),
                "price_open": float(pos.price_open),
                "current_price": current_price or float(pos.price_open),
                "price_current": current_price or float(pos.price_open),
                "volume": float(pos.volume),
                "profit": float(pos.profit),
                "stop_loss": float(pos.sl) if pos.sl else None,
                "take_profit": float(pos.tp) if pos.tp else None,
                "sl": float(pos.sl) if pos.sl else None,
                "tp": float(pos.tp) if pos.tp else None,
                "swap": float(getattr(pos, "swap", 0.0) or 0.0),
                "commission": float(getattr(pos, "commission", 0.0) or 0.0),
                "magic": int(getattr(pos, "magic", 0) or 0),
                "comment": str(getattr(pos, "comment", "") or ""),
                "time": int(pos.time),
                "open_time": datetime.fromtimestamp(int(pos.time), tz=timezone.utc).isoformat(),
            }
        )
    return snapshot


# ── Trade Synchronizer ────────────────────────────────────────────────────────

class TradeSynchronizer:
    """Synchronizes MT5 ground truth (manual trades + history) with MySQL."""
    def __init__(self, db, target_symbol: str, magic_number: int):
        self.db = db
        self.symbol = target_symbol
        self.magic_number = magic_number
        self.last_sync_timestamp = 0

    def sync_all(self):
        """Perform a full synchronization of positions and recent history."""
        if not self.db or not self.db.is_enabled():
            return

        try:
            # 1. Open positions are always synced fresh (small dataset)
            self._sync_positions()

            # 2. History sync with Delta logic
            from_time = None
            if self.last_sync_timestamp == 0:
                # Initialization: Check DB for the last synced ticket
                last_ticket = self.db.get_last_sync_ticket()
                if last_ticket > 0:
                    deals = mt5_call(
                        "bridge.trade_sync.history_deal_by_ticket",
                        lambda: mt5.history_deals_get(ticket=last_ticket),
                        warn_threshold_ms=1000,
                    )
                    if deals:
                        # Start sync from the time of the last known deal
                        from_time = datetime.fromtimestamp(deals[0].time, tz=timezone.utc)
                        logger.info(f"🔄 Resuming history sync from ticket #{last_ticket} ({from_time})")
            
            # If still 0 or no ticket found, start from beginning of time (or max 30 days)
            if from_time is None:
                from_time = datetime.now(timezone.utc) - timedelta(days=30)
                if self.last_sync_timestamp == 0:
                    logger.info("📡 Starting first-time history sync (last 30 days)...")

            # Sync from 'from_time' to now
            self._sync_history(from_time)
            
            # Update last sync timestamp to now (for the next loop)
            self.last_sync_timestamp = int(datetime.now(timezone.utc).timestamp())

        except Exception as e:
            logger.error(f"Trade sync failed: {e}")

    def _sync_positions(self):
        """Fetch all current open positions and mirror to DB."""
        positions = mt5_call(
            "bridge.trade_sync.positions_get",
            lambda: mt5.positions_get(),
            warn_threshold_ms=1000,
        )
        if positions is None:
            return

        for pos in positions:
            data = {
                "ticket": pos.ticket,
                "direction": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "symbol": pos.symbol,
                "entry_price": pos.price_open,
                "lot_size": pos.volume,
                "magic_number": pos.magic,
                "comment": pos.comment,
                "status": "OPEN",
                "created_at": datetime.fromtimestamp(pos.time, tz=timezone.utc),
                "stop_loss": pos.sl,
                "take_profit": pos.tp,
                "profit": pos.profit,
                "commission": getattr(pos, "commission", 0.0),
                "swap": pos.swap,
            }
            self.db.upsert_order_from_mt5(data)

    def _sync_history(self, from_date: datetime):
        """Fetch historical deals since from_date and sync to DB."""
        deals = mt5_call(
            "bridge.trade_sync.history_deals_get",
            lambda: mt5.history_deals_get(from_date, datetime.now(timezone.utc)),
            warn_threshold_ms=1000,
        )
        if deals is None:
            return

        for deal in deals:
            # Only sync deals that are TRADE_ACTION_DEAL and Type BUY/SELL
            if deal.type not in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL):
                continue
            
            data = {
                "ticket": deal.position_id,
                "direction": "BUY" if deal.type == mt5.ORDER_TYPE_BUY else "SELL",
                "symbol": deal.symbol,
                "entry_price": deal.price,
                "lot_size": deal.volume,
                "magic_number": deal.magic,
                "comment": deal.comment,
                "status": "CLOSED" if deal.entry == mt5.DEAL_ENTRY_OUT else "ENTRY_SYNC",
                "created_at": datetime.fromtimestamp(deal.time, tz=timezone.utc),
                "closed_at": datetime.fromtimestamp(deal.time, tz=timezone.utc) if deal.entry == mt5.DEAL_ENTRY_OUT else None,
                "close_price": deal.price if deal.entry == mt5.DEAL_ENTRY_OUT else None,
                "profit": deal.profit,
                "commission": deal.commission,
                "swap": deal.swap,
                "close_reason": "mt5_history_sync"
            }
            self.db.upsert_order_from_mt5(data)

    async def sync_loop(self, interval: int = 30):
        """Periodic sync task."""
        while True:
            await asyncio.to_thread(self.sync_all)
            await asyncio.sleep(interval)


# ── WebSocket Client ──────────────────────────────────────────────────────────

def _load_execution_services():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from app.services.database import db
        from app.services.risk_manager import get_risk_manager
        return db, get_risk_manager()
    except Exception as e:
        logger.warning(f"Execution services unavailable in bridge: {e}")
        return None, None


def _start_optional_bridge_services_sync(auto_trade: bool):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    position_monitor = None
    synchronizer = None

    try:
        from app.services.database import db
        from app.services.position_monitor import get_position_monitor

        if db and db.is_enabled():
            synchronizer = TradeSynchronizer(db, SYMBOL, MAGIC_NUMBER)
            logger.info("📡 Trade Synchronizer created.")

        if auto_trade:
            position_monitor = get_position_monitor()
            if position_monitor:
                if hasattr(position_monitor, "start_threaded"):
                    position_monitor.start_threaded()
                else:
                    position_monitor.start()
    except Exception as e:
        logger.error(f"Failed to start optional bridge services: {e}")

    return synchronizer, position_monitor


async def _start_optional_bridge_services(auto_trade: bool):
    global OPTIONAL_SERVICES_STARTED

    with OPTIONAL_SERVICES_LOCK:
        if OPTIONAL_SERVICES_STARTED:
            BRIDGE_STATUS["optional_services_state"] = "running"
            return
        OPTIONAL_SERVICES_STARTED = True
        BRIDGE_STATUS["optional_services_state"] = "starting"

    try:
        started_at = time.perf_counter()
        synchronizer, _position_monitor = await asyncio.to_thread(_start_optional_bridge_services_sync, auto_trade)
        if synchronizer:
            OPTIONAL_SERVICES_TASKS.append(asyncio.create_task(synchronizer.sync_loop(30)))
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms > 1000:
            logger.warning("Optional bridge services startup took %.1fms", elapsed_ms)
        BRIDGE_STATUS["optional_services_state"] = "running"
    except Exception as exc:
        with OPTIONAL_SERVICES_LOCK:
            OPTIONAL_SERVICES_STARTED = False
        BRIDGE_STATUS["optional_services_state"] = f"degraded:{exc}"
        logger.error(f"Failed to start optional bridge services: {exc}")


async def _send_json(ws, payload: dict, send_lock: asyncio.Lock, *, timeout: float = 2.0) -> None:
    async with send_lock:
        try:
            await asyncio.wait_for(ws.send(json.dumps(payload)), timeout=timeout)
        except websockets.exceptions.ConnectionClosed:
            raise


async def run(auto_trade: bool = False):
    logger.info(f"Connecting to Midas backend at {WS_URL}...")
    logger.info(f"Auto-trade: {'ENABLED ⚡' if auto_trade else 'DISABLED (display only)'}")

    async for ws in websockets.connect(WS_URL, ping_interval=20, ping_timeout=10):
        try:
            logger.info("✅ Connected to Midas backend. Streaming ticks...")
            send_lock = asyncio.Lock()
            connection_closed = asyncio.Event()
            if ENABLE_CANDLE_STREAM:
                await _bootstrap_candle_stream(ws, auto_trade, send_lock)
            else:
                _set_candle_stream_state("disabled", result="disabled")
            
            async def mt5_health_check():
                while True:
                    await asyncio.sleep(30)
                    try:
                        account = mt5_call(
                            "bridge.health_check.account_info",
                            lambda: mt5.account_info(),
                            warn_threshold_ms=250,
                        )
                        if account is None:
                            logger.warning("MT5 connection lost — attempting reconnection...")
                            raise ConnectionError("MT5 account unavailable")
                    except Exception:
                        logger.warning("MT5 health check failed")
                        raise

            async def supervised(name: str, factory):
                while True:
                    try:
                        await factory()
                        logger.warning(
                            f"{name} exited unexpectedly without an exception; "
                            "ending current websocket session and reconnecting."
                        )
                        connection_closed.set()
                        return
                    except asyncio.CancelledError:
                        raise
                    except websockets.exceptions.ConnectionClosed as exc:
                        logger.info(
                            f"{name} noticed websocket closed: code={getattr(exc, 'code', '?')} "
                            f"reason={getattr(exc, 'reason', '') or 'n/a'}"
                        )
                        connection_closed.set()
                        return
                    except Exception as exc:
                        logger.warning(f"{name} failed; restarting task in 1s: {exc}")
                        await asyncio.sleep(1)
            
            tasks = [
                asyncio.create_task(supervised("tick sender", lambda: tick_sender(ws, send_lock))),
                asyncio.create_task(supervised("command receiver", lambda: command_receiver(ws, auto_trade, send_lock))),
                asyncio.create_task(supervised("order executor", lambda: order_executor_worker(ws, auto_trade, send_lock))),
                asyncio.create_task(supervised("bridge state sender", lambda: bridge_state_sender(ws, send_lock))),
                asyncio.create_task(supervised("heartbeat sender", lambda: heartbeat_sender(ws, auto_trade, send_lock))),
                asyncio.create_task(mt5_health_check()),
            ]
            if ENABLE_CANDLE_STREAM:
                tasks.append(asyncio.create_task(supervised("candle sender", lambda: candle_sender(ws, send_lock))))
            else:
                logger.info("Candle stream disabled; keeping MT5 tick/execution bridge responsive.")
            asyncio.create_task(_start_optional_bridge_services(auto_trade))
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            errors = []
            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc:
                    errors.append(exc)
            if errors:
                raise errors[0]
            if connection_closed.is_set():
                logger.warning("Connection closed — reconnecting in 5s...")
            else:
                logger.warning("Bridge task ended — reconnecting in 5s...")
            await asyncio.sleep(5)
        except websockets.ConnectionClosed:
            logger.warning("Connection closed — reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error: {e} — reconnecting in 5s...")
            await asyncio.sleep(5)
        finally:
            pass


async def tick_sender(ws, send_lock: asyncio.Lock):
    last_price = None
    last_no_tick_warning = 0.0
    while True:
        cycle_started = time.perf_counter()

        def _read_tick():
            mt5.symbol_select(SYMBOL, True)
            return mt5.symbol_info_tick(SYMBOL)

        tick = mt5_call("bridge.tick_sender.symbol_info_tick", _read_tick, warn_threshold_ms=250)
        if tick and tick.bid > 0 and tick.ask > 0:
            price = round(float(tick.bid), 2)
            ask = round(float(tick.ask), 2)
            tick_meta = _track_tick_state(tick, bid=price, ask=ask)
            
            # Spike Guard: Ignore price <= 1.0 or massive jumps (> 1%)
            if price <= 1.0:
                logger.warning(f"⚠️ Ignoring invalid price tick: {price}")
            elif last_price is not None and abs(price - last_price) > (last_price * 0.01):
                logger.warning(f"⚠️ Spike Guard (Local): Ignoring potential bad tick {price} (last: {last_price})")
            else:
                last_price = price
                _set_status("last_tick_at")
                if tick_meta["tick_fresh"]:
                    _set_status("last_tick_error", None)
                else:
                    _set_status("last_tick_error", "broker_tick_stale")
                payload = {
                    "type": "TICK",
                    "data": {
                        "symbol": SYMBOL,
                        "bid":    price,
                        "ask":    ask,
                        "spread": round(float(tick.ask - tick.bid), 2),
                        "time": tick_meta["broker_tick_time"],
                        "broker_tick_time": tick_meta["broker_tick_time"],
                        "broker_tick_age_seconds": tick_meta["broker_tick_age_seconds"],
                        "bridge_received_at": datetime.now(timezone.utc).isoformat(),
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "tick_sequence": tick_meta["tick_sequence"],
                        "price_changed_at": tick_meta["price_changed_at"],
                        "tick_fresh": tick_meta["tick_fresh"],
                    },
                }
                await _send_json(ws, payload, send_lock, timeout=1.0)
                duration_ms = (time.perf_counter() - cycle_started) * 1000.0
                _set_status("last_tick_push_at")
                BRIDGE_STATUS["last_tick_push_duration_ms"] = round(duration_ms, 2)
                if duration_ms > 250:
                    logger.warning("Tick sender cycle took %.1fms", duration_ms)
                if not tick_meta["tick_fresh"]:
                    now = asyncio.get_running_loop().time()
                    if now - last_no_tick_warning >= 10:
                        logger.warning(
                            f"Broker tick for {SYMBOL} is stale; broker_age={tick_meta['broker_tick_age_seconds']}s; "
                            "not treating this poll as execution-fresh."
                        )
                        last_no_tick_warning = now
        else:
            now = asyncio.get_running_loop().time()
            if now - last_no_tick_warning >= 10:
                reason = _tick_failure_reason(SYMBOL)
                _set_status("last_tick_error", reason)
                logger.warning(f"No valid MT5 tick for {SYMBOL}; reason={reason}; waiting for next tick...")
                last_no_tick_warning = now
        await asyncio.sleep(TICK_INTERVAL)


execution_queue = asyncio.Queue()


async def bridge_state_sender(ws, send_lock: asyncio.Lock):
    while True:
        cycle_started = time.perf_counter()
        try:
            account = _account_snapshot()
            if account:
                _set_status("last_account_snapshot_at")
                await _send_json(ws, {"type": "ACCOUNT", "data": account}, send_lock, timeout=1.0)
            positions = _positions_snapshot()
            _set_status("last_positions_snapshot_at")
            await _send_json(
                ws,
                {
                    "type": "POSITIONS",
                    "data": {
                        "symbol": SYMBOL,
                        "positions": positions,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
                send_lock,
                timeout=1.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Bridge state send timed out; continuing.")
        except Exception as exc:
            logger.warning(f"Bridge state snapshot failed: {exc}")
        duration_ms = (time.perf_counter() - cycle_started) * 1000.0
        if duration_ms > 1000:
            logger.warning("Bridge state sender cycle took %.1fms", duration_ms)
        await asyncio.sleep(STATE_PUSH_INTERVAL)


async def heartbeat_sender(ws, auto_trade: bool, send_lock: asyncio.Lock):
    while True:
        await _send_json(
            ws,
            {"type": "BRIDGE_STATUS", "data": _bridge_status_payload(auto_trade)},
            send_lock,
            timeout=1.0,
        )
        await asyncio.sleep(BRIDGE_HEARTBEAT_INTERVAL)


async def order_executor_worker(ws, auto_trade: bool, send_lock: asyncio.Lock):
    db = None
    risk_manager = None
    services_task = asyncio.create_task(asyncio.to_thread(_load_execution_services))

    while True:
        task = await execution_queue.get()
        if services_task.done() and db is None and risk_manager is None:
            db, risk_manager = services_task.result()
        data = task["data"]
        action = task["action"]
        
        signal_id = data.get("signal_id", "unknown")
        direction = str(data.get("direction", "HOLD")).upper()
        display_symbol = data.get("symbol") or SYMBOL
        effective_symbol = _resolve_order_symbol(data)
        position_action = str(data.get("position_action") or "open").lower()
        is_duplicate = bool(data.get("is_duplicate"))
        
        if display_symbol != effective_symbol:
            logger.info(f"⚡ Processing queued execution [{signal_id}]: {direction} ({position_action}) display={display_symbol} broker={effective_symbol}")
        else:
            logger.info(f"⚡ Processing queued execution [{signal_id}]: {direction} ({position_action})")
        
        blockers = _execution_blockers(auto_trade)
        if blockers:
            result = {
                "status": "error",
                "stage": "precheck",
                "action": position_action,
                "reason": f"Bridge execution not ready: {', '.join(blockers)}",
                "execution_blockers": blockers,
                "broker_symbol": effective_symbol,
                "execution_symbol": effective_symbol,
            }
        else:
            router = MT5OrderRouter(db=db, risk_manager=risk_manager)
            result = router.execute(data)

        if result.get("status") == "blocked":
            logger.warning(f"Blocked: {result.get('reason')}")
        elif result.get("status") == "ok":
            logger.info(f"Executed: {direction} {result.get('volume')} lots @ {result.get('price')} (ticket #{result.get('ticket')})")

        if result.get("status") == "blocked" and db and db.is_enabled():
            def _log_risk():
                try:
                    db.log_risk_event(
                        event_type="POSITION_BLOCKED",
                        description=result.get("reason", "Unknown"),
                        action_taken="Order rejected",
                        metadata={
                            "signal_id": signal_id,
                            "direction": direction,
                            "position_action": position_action,
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to log risk event: {e}")
            
            asyncio.get_running_loop().run_in_executor(None, _log_risk)

        if result.get("status") == "ok" and db and db.is_enabled():
            def _save_order():
                try:
                    signal_context = {
                        "analysis_batch_id": data.get("analysis_batch_id"),
                        "setup_type": data.get("setup_type"),
                        "trading_style": data.get("trading_style"),
                        "market_regime": data.get("market_regime"),
                        "regime_at_signal": data.get("market_regime"),
                        "regime_confidence_at_signal": (data.get("evidence") or {}).get("regime_alignment"),
                        "session_at_signal": data.get("session_label") or "off",
                        "volatility_bucket_at_signal": data.get("volatility_bucket"),
                        "spread_at_signal": result.get("spread"),
                        "actual_spread": result.get("spread"),
                        "slippage_points": result.get("slippage_points"),
                        "intended_entry_price": float(data.get("entry_price") or 0.0),
                        "intended_stop_loss": float(data.get("stop_loss") or 0.0),
                        "intended_take_profit_1": float(data.get("take_profit_1") or 0.0),
                        "data_source_at_signal": data.get("source"),
                        "compression_ratio_at_entry": (data.get("evidence") or {}).get("compression_ratio"),
                        "efficiency_ratio_at_entry": (data.get("evidence") or {}).get("efficiency_ratio"),
                        "close_location_at_entry": (data.get("evidence") or {}).get("close_location"),
                        "body_strength_at_entry": (data.get("evidence") or {}).get("body_strength"),
                        "position_action": position_action,
                        "position_action_reason": data.get("position_action_reason"),
                        "calibrated_confidence": data.get("calibrated_confidence"),
                        "confidence_source": data.get("confidence_source"),
                        "display_symbol": display_symbol,
                        "broker_symbol": result.get("broker_symbol") or effective_symbol,
                        "execution_symbol": result.get("execution_symbol") or effective_symbol,
                    }
                    db.save_order(
                        signal_id=signal_id,
                        ticket=result.get("ticket"),
                        direction=direction,
                        entry_price=result.get("price"),
                        stop_loss=float(data.get("stop_loss")),
                        take_profit=float(data.get("take_profit_1")),
                        lot_size=result.get("lot_size", float(data.get("lot", DEFAULT_LOT))),
                        magic_number=MAGIC_NUMBER,
                        comment=f"Midas AI Signal [{position_action}]",
                        symbol=display_symbol,
                        analysis_batch_id=data.get("analysis_batch_id"),
                        setup_type=data.get("setup_type"),
                        signal_context=signal_context,
                        entry_spread=result.get("spread"),
                        slippage_points=result.get("slippage_points"),
                    )
                except Exception as e:
                    logger.error(f"Failed to save order to database: {e}")

            asyncio.get_running_loop().run_in_executor(None, _save_order)

        _update_position_decision_execution(signal_id, result, db=db)

        ack = {
            "type": "ACK",
            "signal_id": signal_id,
            "status": result.get("status"),
            "ticket": result.get("ticket"),
            "opened_ticket": result.get("opened_ticket"),
            "closed_tickets": result.get("closed_tickets", []),
            "price": result.get("price") or result.get("close_price"),
            "message": result.get("comment") or result.get("reason") or result.get("message", ""),
            "stage": result.get("stage"),
            "action": result.get("action") or position_action,
            "retcode": result.get("retcode"),
            "comment": result.get("comment"),
            "last_error": result.get("last_error"),
            "execution_blockers": result.get("execution_blockers"),
            "symbol": display_symbol,
            "broker_symbol": result.get("broker_symbol") or effective_symbol,
            "execution_symbol": result.get("execution_symbol") or effective_symbol,
        }
        await _send_json(ws, ack, send_lock, timeout=1.0)

        if result.get("status") == "ok":
            logger.info(f"   ✅ Order #{result.get('ticket')} placed @ {result.get('price')}")
            # Record entry in trading state to update the real-time counter
            try:
                trading_state.record_entry()
            except Exception as e:
                logger.error(f"Failed to record trade entry: {e}")
        elif result.get("status") == "closed":
            logger.info(f"   {ack.get('message')}")
        elif result.get("status") in {"blocked", "skipped"}:
            logger.warning(f"   🚫 {ack.get('message')}")
        else:
            logger.error(f"   ❌ Order failed: {result}")
        
        try:
            execution_queue.task_done()
        except Exception as e:
            logger.error(f"Failed to mark queue task done: {e}")


async def command_receiver(ws, auto_trade: bool, send_lock: asyncio.Lock):
    try:
        async for raw in ws:
            try:
                payload = json.loads(raw)
                msg_type = payload.get("type")
                
                if msg_type == "CONFIG_UPDATE":
                    try:
                        import sys
                        from pathlib import Path
                        if str(Path(__file__).parent) not in sys.path:
                            sys.path.insert(0, str(Path(__file__).parent))
                        
                        from app.services.risk_manager import get_risk_manager
                        from app.services.position_monitor import get_position_monitor
                        from app.services.position_manager import get_position_manager
                        
                        logger.info("🔄 Received CONFIG_UPDATE: Refreshing all limits from database...")
                        
                        # Update Risk Manager
                        r_manager = get_risk_manager()
                        if r_manager:
                            r_manager.config.refresh_config()
                            logger.info(f"   ► Risk limits: concurrent={r_manager.config.max_concurrent_positions}, trades={r_manager.config.max_daily_trades}")

                        # Update Position Monitor
                        p_monitor = get_position_monitor()
                        if p_monitor and hasattr(p_monitor, "config") and hasattr(p_monitor.config, "refresh_config"):
                            p_monitor.config.refresh_config()
                            logger.info(f"   ► Position Monitor refreshed: T/S={p_monitor.config.trailing_stop_enabled}, P/C={p_monitor.config.partial_close_enabled}")
                            
                        # Update Position Manager
                        p_manager = get_position_manager()
                        if p_manager and hasattr(p_manager, "config") and hasattr(p_manager.config, "from_db"):
                            p_manager.config = p_manager.config.from_db()
                            logger.info(f"   ► Position Manager refreshed: Cooldown={p_manager.config.position_cooldown_seconds}s")

                    except Exception as e:
                        import traceback
                        logger.error(f"Failed to process CONFIG_UPDATE: {e}\n{traceback.format_exc()}")
                    continue

                if msg_type != "SIGNAL":
                    continue

                data = payload.get("data", {})
                signal_id = data.get("signal_id", "unknown")
                direction = str(data.get("direction", "HOLD")).upper()
                action = payload.get("action")

                logger.info(f"Signal: {direction} @{data.get('entry_price')} conf={data.get('confidence')}% sl={data.get('stop_loss')}")

                if action != "PLACE_ORDER":
                    logger.debug("   Display-only signal; no MT5 order requested.")
                    continue

                if not auto_trade:
                    logger.warning("   Auto-trade is OFF - restart with --auto-trade to execute orders")
                    await _send_json(ws, {
                            "type": "ACK",
                            "signal_id": signal_id,
                            "status": "skipped",
                            "message": "Auto-trade is disabled",
                        }, send_lock, timeout=1.0)
                    continue
                
                await execution_queue.put({"action": action, "data": data})
            except websockets.exceptions.ConnectionClosed:
                raise
            except Exception as e:
                logger.error(f"Error processing command: {e}")
    except websockets.exceptions.ConnectionClosed:
        raise


async def _emit_bridge_status(ws, auto_trade: bool, send_lock: asyncio.Lock) -> None:
    try:
        await _send_json(
            ws,
            {"type": "BRIDGE_STATUS", "data": _bridge_status_payload(auto_trade)},
            send_lock,
            timeout=1.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Bridge status send timed out during candle warmup.")


async def _push_candles_for_timeframe(
    ws,
    *,
    trigger: str,
    send_lock: asyncio.Lock,
    candle_symbol: str,
    display_symbol: str,
    tf_name: str,
) -> bool:
    started_at = time.perf_counter()
    candles = _fetch_candles(candle_symbol, tf_name)
    if not candles:
        if tf_name in {"1m", "5m"}:
            BRIDGE_STATUS[f"last_candle_push_duration_{tf_name}_ms"] = round((time.perf_counter() - started_at) * 1000.0, 2)
        logger.debug(f"⚠️ [{trigger}] No candles for {candle_symbol} {tf_name}")
        return False

    if tf_name == "1m":
        _set_status("last_candle_1m_at")
    elif tf_name == "5m":
        _set_status("last_candle_5m_at")
    BRIDGE_STATUS[f"last_candle_push_error_{tf_name}"] = BRIDGE_STATUS.get(f"last_candle_error_{tf_name}")

    logger.info(f"📊 [{trigger}] Sending {len(candles)} candles: display={display_symbol} broker={candle_symbol} {tf_name}")
    payload = {
        "type": "CANDLES",
        "data": {
            "symbol": display_symbol,
            "display_symbol": display_symbol,
            "canonical_symbol": display_symbol,
            "broker_symbol": candle_symbol,
            "timeframe": tf_name,
            "source": "bridge-mt5",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "candles": candles,
        },
    }
    try:
        await _send_json(ws, payload, send_lock, timeout=1.5)
    except asyncio.TimeoutError:
        timeout_error = "bridge_candle_send_timeout"
        if tf_name in {"1m", "5m"}:
            _set_status(f"last_candle_error_{tf_name}", timeout_error)
            BRIDGE_STATUS[f"last_candle_push_error_{tf_name}"] = timeout_error
        logger.warning(f"📊 [{trigger}] Candle send timed out: {candle_symbol} {tf_name}; continuing.")
        return False

    duration_ms = (time.perf_counter() - started_at) * 1000.0
    if tf_name in {"1m", "5m"}:
        BRIDGE_STATUS[f"last_candle_push_duration_{tf_name}_ms"] = round(duration_ms, 2)
    if duration_ms > 250:
        logger.warning("Candle push %s %s took %.1fms", candle_symbol, tf_name, duration_ms)
    logger.debug(f"📊 [{trigger}] Sent candles: {candle_symbol} {tf_name}")
    await asyncio.sleep(0.05)
    return True


async def _bootstrap_candle_stream(ws, auto_trade: bool, send_lock: asyncio.Lock) -> None:
    if not ENABLE_CANDLE_STREAM:
        _set_candle_stream_state("disabled", result="disabled")
        return

    _reset_candle_stream_status()
    await _emit_bridge_status(ws, auto_trade, send_lock)

    candle_symbol = _discover_candle_symbol(CANDLE_SYMBOL, SYMBOL)
    globals()["CANDLE_SYMBOL"] = candle_symbol or CANDLE_SYMBOL_OVERRIDE or SYMBOL
    if not candle_symbol:
        _set_candle_stream_state("degraded", result="no_candle_symbol_resolved")
        await _emit_bridge_status(ws, auto_trade, send_lock)
        return

    display_symbol = _normalize_order_symbol(candle_symbol) or "XAUUSD"
    pushed_1m = await _push_candles_for_timeframe(
        ws,
        trigger="bootstrap",
        send_lock=send_lock,
        candle_symbol=candle_symbol,
        display_symbol=display_symbol,
        tf_name="1m",
    )
    pushed_5m = await _push_candles_for_timeframe(
        ws,
        trigger="bootstrap",
        send_lock=send_lock,
        candle_symbol=candle_symbol,
        display_symbol=display_symbol,
        tf_name="5m",
    )

    if pushed_1m and pushed_5m:
        _set_candle_stream_state("ready", result="ok")
    else:
        bootstrap_result = "partial" if pushed_1m or pushed_5m else "failed"
        _set_candle_stream_state("degraded", result=bootstrap_result)
    await _emit_bridge_status(ws, auto_trade, send_lock)


async def candle_sender(ws, send_lock: asyncio.Lock):
    while True:
        await asyncio.sleep(CANDLE_PUSH_INTERVAL)
        await _push_all_candles(ws, "periodic", send_lock)


async def _push_all_candles(ws, trigger: str, send_lock: asyncio.Lock):
    ordered_timeframes = ["1m", "5m"] + [tf_name for tf_name in CANDLE_TIMEFRAMES.keys() if tf_name not in {"1m", "5m"}]
    candle_symbol = CANDLE_SYMBOL or SYMBOL
    display_symbol = _normalize_order_symbol(candle_symbol) or "XAUUSD"
    required_success = {"1m": False, "5m": False}
    for tf_name in ordered_timeframes:
        pushed = await _push_candles_for_timeframe(
            ws,
            trigger=trigger,
            send_lock=send_lock,
            candle_symbol=candle_symbol,
            display_symbol=display_symbol,
            tf_name=tf_name,
        )
        if tf_name in required_success:
            required_success[tf_name] = pushed
    if ENABLE_CANDLE_STREAM:
        if all(required_success.values()):
            _set_candle_stream_state("ready")
        elif any(required_success.values()):
            _set_candle_stream_state("degraded", result="partial")
        else:
            _set_candle_stream_state("degraded", result="failed")

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
    print(f"  Candles : {CANDLE_SYMBOL_OVERRIDE or '(auto-detect)'}")
    print(f"  Lot     : {DEFAULT_LOT}")
    print(f"  Backend : {WS_URL}")
    print(f"  Mode    : {'AUTO-TRADE [ON]' if auto_trade else 'Display only'}")
    print("="*55 + "\n")

    # Retry init until MT5 is open
    MAX_RETRIES = int(os.getenv("MT5_MAX_RETRIES", "10"))
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

    if "--probe-candles" in sys.argv:
        print(json.dumps(candle_probe_report(SYMBOL, CANDLE_SYMBOL), indent=2))
        mt5.shutdown()
        sys.exit(0)

    try:
        asyncio.run(run(auto_trade=auto_trade))
    except asyncio.CancelledError:
        logger.info("Shutdown requested via task cancellation.")
        raise
    except Exception as e:
        logger.error(f"Bridge crashed: {e}")
    finally:
        mt5.shutdown()
