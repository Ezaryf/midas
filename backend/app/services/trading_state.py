"""
Persistent Trading State Service
Stores daily counters and trading style in MySQL so they survive restarts.
Falls back to in-memory state when MySQL is unavailable.
"""
import json
import logging
import threading
import asyncio
from datetime import datetime, date
from typing import Optional

from app.services.runtime_state import runtime_state

logger = logging.getLogger(__name__)


class TradingState:
    """
    Persistent trading state backed by MySQL.
    Falls back to in-memory state when DB is unavailable.
    """

    def __init__(self):
        self._lock = threading.Lock()
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

    def _ensure_table(self, db):
        """Create the trading_state table if it does not exist."""
        conn = db._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_state (
                    id VARCHAR(36) PRIMARY KEY,
                    daily_trades INT DEFAULT 0,
                    daily_pnl DECIMAL(14,2) DEFAULT 0,
                    consecutive_losses INT DEFAULT 0,
                    last_reset_date DATE,
                    trading_style VARCHAR(20) DEFAULT 'Scalper',
                    target_symbol VARCHAR(20) DEFAULT 'XAUUSD',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.debug(f"Could not ensure trading_state table: {e}")
        finally:
            conn.close()

    def _restore_from_db(self):
        """Restore state from MySQL on startup."""
        db = self._get_db()
        if not db:
            logger.info("MySQL unavailable — using in-memory trading state")
            return

        try:
            self._ensure_table(db)

            conn = db._get_conn()
            if not conn:
                return

            try:
                cursor = conn.cursor(dictionary=True)

                # Restore from trading_state table
                cursor.execute("SELECT * FROM trading_state ORDER BY updated_at DESC LIMIT 1")
                row = cursor.fetchone()

                if row:
                    self.trading_style = row.get("trading_style", "Scalper")
                    self.target_symbol = row.get("target_symbol", "XAUUSD")
                    self.consecutive_losses = row.get("consecutive_losses", 0)
                    self.daily_pnl = float(row.get("daily_pnl", 0.0))

                    saved_date = row.get("last_reset_date")
                    today = self.last_reset_date
                    if saved_date and saved_date != today:
                        logger.info(f"New trading day detected (saved: {saved_date}) — resetting counters")
                        self.daily_trades = 0
                        self.daily_pnl = 0.0
                        self.consecutive_losses = 0

                # Count today's trades from signals
                today_str = self.last_reset_date.isoformat()
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM signals WHERE created_at >= %s AND COALESCE(status, 'NEW') <> 'NO_TRADE'",
                    (today_str,),
                )
                count_row = cursor.fetchone()
                self.daily_trades = int(count_row["cnt"]) if count_row else 0

                cursor.close()
            finally:
                conn.close()

            self._db_available = True
            runtime_state.set_trading_style(self.trading_style)
            runtime_state.set_target_symbol(self.target_symbol)
            logger.info(
                f"Restored trading state: {self.daily_trades} trades today, "
                f"style={self.trading_style}, consecutive_losses={self.consecutive_losses}"
            )

        except Exception as e:
            logger.warning(f"Could not restore trading state from DB: {e}")

    def _persist(self):
        """Save current state to MySQL (fire-and-forget logic)."""
        db = self._get_db()
        if not db:
            return

        # Snap state under lock to avoid holding lock during I/O
        with self._lock:
            data = (
                self.daily_trades,
                round(self.daily_pnl, 2),
                self.consecutive_losses,
                self.last_reset_date.isoformat(),
                self.trading_style,
                self.target_symbol,
            )

        def _do_persist():
            conn = db._get_conn()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO trading_state (id, daily_trades, daily_pnl, consecutive_losses,
                           last_reset_date, trading_style, target_symbol, updated_at)
                       VALUES ('singleton', %s, %s, %s, %s, %s, %s, NOW())
                       ON DUPLICATE KEY UPDATE
                           daily_trades = VALUES(daily_trades),
                           daily_pnl = VALUES(daily_pnl),
                           consecutive_losses = VALUES(consecutive_losses),
                           last_reset_date = VALUES(last_reset_date),
                           trading_style = VALUES(trading_style),
                           target_symbol = VALUES(target_symbol),
                           updated_at = NOW()
                    """,
                    data,
                )
                conn.commit()
                cursor.close()
            except Exception as e:
                logger.debug(f"Could not persist trading_state: {e}")
            finally:
                conn.close()

        # If we are in an async loop, run in a separate thread to avoid blocking
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _do_persist)
        except RuntimeError:
            # Fallback for sync contexts (startup)
            _do_persist()

    # ── Public API ────────────────────────────────────────────────────────────

    def record_trade(self, is_loss: bool = False, loss_amount: float = 0.0):
        """Record a trade execution and update counters."""
        with self._lock:
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
        with self._lock:
            if current_date != self.last_reset_date:
                logger.info(
                    f"New trading day — resetting counters. "
                    f"Yesterday: {self.daily_trades} trades, PnL: ${self.daily_pnl:.2f}"
                )
                self.daily_trades = 0
                self.daily_pnl = 0.0
                self.consecutive_losses = 0
                self.last_reset_date = current_date
                reset_happened = True
            else:
                reset_happened = False

        if reset_happened:
            self._persist()
        return reset_happened

    def set_trading_style(self, style: str):
        """Update the active trading style and persist."""
        with self._lock:
            self.trading_style = style
        runtime_state.set_trading_style(style)
        self._persist()

    def set_target_symbol(self, symbol: str):
        """Update the active target symbol and persist."""
        with self._lock:
            self.target_symbol = symbol
        runtime_state.set_target_symbol(symbol)
        self._persist()

    def reset_consecutive_losses(self):
        """Reset consecutive losses (e.g. after cooldown period)."""
        with self._lock:
            self.consecutive_losses = 0
        self._persist()


# Global singleton
trading_state = TradingState()
