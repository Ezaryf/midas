"""
Persistent Trading State Service
Stores daily counters and trading style in Supabase so they survive restarts.
Falls back to in-memory state when Supabase is unavailable.
"""
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class TradingState:
    """
    Persistent trading state backed by Supabase.
    Falls back to in-memory state when DB is unavailable.
    """

    def __init__(self):
        self.daily_trades: int = 0
        self.daily_pnl: float = 0.0
        self.consecutive_losses: int = 0
        self.last_reset_date: date = datetime.now().date()
        self.trading_style: str = "Scalper"
        self.target_symbol: str = "XAUUSD"
        self._db_available: bool = False

        # Attempt to restore from database on init
        self._restore_from_db()

    def _get_db(self):
        """Lazy import to avoid circular dependency."""
        try:
            from app.services.database import db
            if db.is_enabled():
                return db
        except Exception:
            pass
        return None

    def _restore_from_db(self):
        """Restore state from Supabase on startup."""
        db = self._get_db()
        if not db:
            logger.info("Supabase unavailable — using in-memory trading state")
            return

        try:
            today_str = self.last_reset_date.isoformat()

            # Restore daily trade count from signals table
            result = db.client.table("signals") \
                .select("id", count="exact") \
                .gte("timestamp", today_str) \
                .execute()
            self.daily_trades = result.count or 0

            # Restore trading style from state table (if it exists)
            try:
                state_result = db.client.table("trading_state") \
                    .select("*") \
                    .order("updated_at", desc=True) \
                    .limit(1) \
                    .execute()

                if state_result.data:
                    row = state_result.data[0]
                    self.trading_style = row.get("trading_style", "Scalper")
                    self.target_symbol = row.get("target_symbol", "XAUUSD")
                    self.consecutive_losses = row.get("consecutive_losses", 0)
                    self.daily_pnl = float(row.get("daily_pnl", 0.0))

                    # Check if the saved state is from today
                    saved_date = row.get("last_reset_date", "")
                    if saved_date and saved_date != today_str:
                        # New day — reset counters but keep style
                        logger.info(f"New trading day detected (saved: {saved_date}) — resetting counters")
                        self.daily_trades = 0
                        self.daily_pnl = 0.0
                        self.consecutive_losses = 0
            except Exception:
                # trading_state table may not exist yet — that's OK
                logger.debug("trading_state table not found — will create on first save")

            self._db_available = True
            logger.info(
                f"Restored trading state: {self.daily_trades} trades today, "
                f"style={self.trading_style}, consecutive_losses={self.consecutive_losses}"
            )

        except Exception as e:
            logger.warning(f"Could not restore trading state from DB: {e}")

    def _persist(self):
        """Save current state to Supabase (fire-and-forget)."""
        db = self._get_db()
        if not db:
            return

        try:
            data = {
                "id": "singleton",  # Single-row upsert pattern
                "daily_trades": self.daily_trades,
                "daily_pnl": round(self.daily_pnl, 2),
                "consecutive_losses": self.consecutive_losses,
                "last_reset_date": self.last_reset_date.isoformat(),
                "trading_style": self.trading_style,
                "target_symbol": self.target_symbol,
                "updated_at": datetime.utcnow().isoformat(),
            }
            db.client.table("trading_state").upsert(data, on_conflict="id").execute()
        except Exception as e:
            logger.debug(f"Could not persist trading state: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def record_trade(self, is_loss: bool = False, loss_amount: float = 0.0):
        """Record a trade execution and update counters."""
        self.daily_trades += 1
        if is_loss:
            self.consecutive_losses += 1
            self.daily_pnl -= loss_amount
        else:
            self.consecutive_losses = 0
        self._persist()

    def check_and_reset_daily(self) -> bool:
        """Check if it's a new day and reset counters. Returns True if reset happened."""
        current_date = datetime.now().date()
        if current_date != self.last_reset_date:
            logger.info(
                f"New trading day — resetting counters. "
                f"Yesterday: {self.daily_trades} trades, PnL: ${self.daily_pnl:.2f}"
            )
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.last_reset_date = current_date
            self._persist()
            return True
        return False

    def set_trading_style(self, style: str):
        """Update the active trading style and persist."""
        self.trading_style = style
        self._persist()

    def set_target_symbol(self, symbol: str):
        """Update the active target symbol and persist."""
        self.target_symbol = symbol
        self._persist()

    def reset_consecutive_losses(self):
        """Reset consecutive losses (e.g. after cooldown period)."""
        self.consecutive_losses = 0
        self._persist()


# Global singleton
trading_state = TradingState()
