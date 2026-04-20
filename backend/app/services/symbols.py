from __future__ import annotations

import re


_GOLD_PATTERNS = (
    re.compile(r"^GOLD$", re.IGNORECASE),
    re.compile(r"^XAUUSD[A-Z]?$", re.IGNORECASE),
    re.compile(r"^GOLDUSD$", re.IGNORECASE),
    re.compile(r"^GC[A-Z0-9]+$", re.IGNORECASE),
)


def normalize_symbol(symbol: str | None) -> str:
    raw = (symbol or "").upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", raw)
    for pattern in _GOLD_PATTERNS:
        if pattern.match(cleaned):
            return "XAUUSD"
    return cleaned


def symbols_match(left: str | None, right: str | None) -> bool:
    left_normalized = normalize_symbol(left)
    right_normalized = normalize_symbol(right)
    if not left_normalized or not right_normalized:
        return False
    return left_normalized == right_normalized


def resolve_execution_symbol(
    display_symbol: str | None,
    *,
    broker_symbol: str | None = None,
    tick_symbol: str | None = None,
) -> str:
    """Resolve the concrete broker symbol to use for MT5 execution.

    The UI/history can use canonical symbols such as XAUUSD, while a broker may
    expose the same market as GOLD. Prefer the configured or live broker symbol
    whenever it is equivalent to the display symbol.
    """

    if broker_symbol and (not display_symbol or symbols_match(display_symbol, broker_symbol)):
        return broker_symbol
    if tick_symbol and (not display_symbol or symbols_match(display_symbol, tick_symbol)):
        return tick_symbol
    return display_symbol or broker_symbol or tick_symbol or ""
