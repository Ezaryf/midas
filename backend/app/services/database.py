"""
Database service for Supabase integration.
Handles all database operations for trade history, analytics, and risk management.
With auto-reconnect and graceful degradation when Supabase is unavailable.
"""
import os
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from supabase import create_client, Client
from app.schemas.signal import TradeSignal

logger = logging.getLogger(__name__)

# Reconnect backoff: 30s → 60s → 120s → 240s max
_RECONNECT_BASE_SECONDS = 30
_RECONNECT_MAX_SECONDS = 240


class DatabaseService:
    def __init__(self):
        self._supabase_url = os.getenv("SUPABASE_URL")
        self._supabase_key = os.getenv("SUPABASE_KEY")
        self.client: Optional[Client] = None
        self._reconnect_attempts: int = 0
        self._last_reconnect_time: float = 0

        self._connect()

    def _connect(self):
        """Attempt to connect to Supabase."""
        if not self._supabase_url or not self._supabase_key:
            logger.warning("Supabase credentials not configured — database features disabled")
            return

        try:
            self.client = create_client(self._supabase_url, self._supabase_key)
            self._reconnect_attempts = 0
            logger.info("✅ Connected to Supabase")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            self.client = None

    def _try_reconnect(self) -> bool:
        """Attempt reconnection with exponential backoff. Returns True if connected."""
        if not self._supabase_url or not self._supabase_key:
            return False

        # Calculate backoff delay
        backoff = min(
            _RECONNECT_BASE_SECONDS * (2 ** self._reconnect_attempts),
            _RECONNECT_MAX_SECONDS,
        )
        elapsed = time.time() - self._last_reconnect_time
        if elapsed < backoff:
            return False  # Too soon to retry

        self._last_reconnect_time = time.time()
        self._reconnect_attempts += 1
        logger.info(f"Attempting Supabase reconnect (attempt {self._reconnect_attempts}, backoff {backoff}s)...")

        try:
            self.client = create_client(self._supabase_url, self._supabase_key)
            # Quick health check — try a lightweight query
            self.client.table("signals").select("id", count="exact").limit(1).execute()
            self._reconnect_attempts = 0
            logger.info("✅ Supabase reconnected successfully")
            return True
        except Exception as e:
            logger.warning(f"Supabase reconnect failed: {e}")
            self.client = None
            return False

    def is_enabled(self) -> bool:
        """Check if database is configured and available. Triggers reconnect if needed."""
        if self.client is not None:
            return True
        # Try to reconnect (respects backoff)
        return self._try_reconnect()

    
    # ── Signals ───────────────────────────────────────────────────────────────
    
    def save_signal(
        self,
        signal: TradeSignal,
        indicators: dict,
        calendar_events: list,
        current_price: float,
        trend: str,
        ai_provider: str,
        ai_model: str,
        regime_summary: str | None = None,
    ) -> str:
        """Save a generated signal to database. Returns signal ID."""
        if not self.is_enabled():
            return "db_disabled"
        
        try:
            data = {
                "direction": signal.direction,
                "entry_price": float(signal.entry_price),
                "stop_loss": float(signal.stop_loss),
                "take_profit_1": float(signal.take_profit_1),
                "take_profit_2": float(signal.take_profit_2),
                "confidence": float(signal.confidence),
                "reasoning": signal.reasoning,
                "symbol": signal.symbol,
                "analysis_batch_id": signal.analysis_batch_id,
                "trading_style": signal.trading_style,
                "setup_type": signal.setup_type,
                "market_regime": signal.market_regime,
                "score": float(signal.score),
                "rank": int(signal.rank),
                "is_primary": bool(signal.is_primary),
                "entry_window_low": float(signal.entry_window_low),
                "entry_window_high": float(signal.entry_window_high),
                "context_tags": signal.context_tags,
                "source": signal.source,
                "context": {
                    "regime_summary": regime_summary,
                    "context_tags": signal.context_tags,
                    "source": signal.source,
                },
                "indicators": indicators,
                "calendar_events": calendar_events,
                "current_price": float(current_price),
                "trend": trend,
                "ai_provider": ai_provider,
                "ai_model": ai_model,
            }
            
            result = self.client.table("signals").insert(data).execute()
            signal_id = result.data[0]["id"]
            logger.info(f"✅ Signal saved to database: {signal_id}")
            return signal_id
        
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return "error"
    
    def get_recent_signals(self, limit: int = 10) -> list:
        """Get recent signals for display"""
        if not self.is_enabled():
            return []
        
        try:
            result = self.client.table("signals") \
                .select("*") \
                .order("timestamp", desc=True) \
                .limit(limit) \
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to fetch signals: {e}")
            return []
    
    # ── Orders ────────────────────────────────────────────────────────────────
    
    def save_order(
        self,
        signal_id: str,
        ticket: int,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float,
        magic_number: int,
        comment: str = "",
    ) -> str:
        """Save an executed order to database. Returns order ID."""
        if not self.is_enabled():
            return "db_disabled"
        
        try:
            data = {
                "signal_id": signal_id if signal_id != "db_disabled" else None,
                "ticket": ticket,
                "direction": direction,
                "entry_price": float(entry_price),
                "stop_loss": float(stop_loss),
                "take_profit": float(take_profit),
                "lot_size": float(lot_size),
                "magic_number": magic_number,
                "comment": comment,
                "status": "OPEN",
            }
            
            result = self.client.table("orders").insert(data).execute()
            order_id = result.data[0]["id"]
            logger.info(f"✅ Order saved to database: ticket #{ticket}")
            return order_id
        
        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return "error"
    
    def update_order_close(
        self,
        ticket: int,
        close_price: float,
        profit: float,
        commission: float,
        swap: float,
        close_reason: str,
    ):
        """Update order when it closes"""
        if not self.is_enabled():
            return
        
        try:
            data = {
                "status": "CLOSED",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "close_price": float(close_price),
                "profit": float(profit),
                "commission": float(commission),
                "swap": float(swap),
                "close_reason": close_reason,
            }
            
            self.client.table("orders") \
                .update(data) \
                .eq("ticket", ticket) \
                .execute()
            
            logger.info(f"✅ Order #{ticket} closed: {close_reason} | P&L: {profit}")
        
        except Exception as e:
            logger.error(f"Failed to update order close: {e}")
    
    def get_open_orders(self) -> list:
        """Get all currently open orders"""
        if not self.is_enabled():
            return []
        
        try:
            result = self.client.table("orders") \
                .select("*") \
                .eq("status", "OPEN") \
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            return []
    
    # ── Account Snapshots ─────────────────────────────────────────────────────
    
    def save_account_snapshot(
        self,
        balance: float,
        equity: float,
        margin: float,
        free_margin: float,
        margin_level: float,
        open_positions: int,
        pending_orders: int,
        daily_profit: float,
        daily_trades: int,
    ):
        """Save account state snapshot"""
        if not self.is_enabled():
            return
        
        try:
            data = {
                "balance": float(balance),
                "equity": float(equity),
                "margin": float(margin),
                "free_margin": float(free_margin),
                "margin_level": float(margin_level),
                "open_positions": open_positions,
                "pending_orders": pending_orders,
                "daily_profit": float(daily_profit),
                "daily_trades": daily_trades,
            }
            
            self.client.table("account_snapshots").insert(data).execute()
            logger.debug("Account snapshot saved")
        
        except Exception as e:
            logger.error(f"Failed to save account snapshot: {e}")
    
    def get_equity_curve(self, days: int = 30) -> list:
        """Get equity curve data for charting"""
        if not self.is_enabled():
            return []
        
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            result = self.client.table("account_snapshots") \
                .select("timestamp, equity, balance") \
                .gte("timestamp", cutoff) \
                .order("timestamp", desc=False) \
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to fetch equity curve: {e}")
            return []
    
    # ── Performance Metrics ───────────────────────────────────────────────────
    
    def calculate_performance_metrics(self, period: str = "ALL_TIME"):
        """Calculate and cache performance metrics"""
        if not self.is_enabled():
            return
        
        try:
            # Determine period boundaries
            now = datetime.now(timezone.utc)
            if period == "DAILY":
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "WEEKLY":
                period_start = now - timedelta(days=now.weekday())
            elif period == "MONTHLY":
                period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:  # ALL_TIME
                period_start = datetime(2020, 1, 1)
            
            period_end = now
            
            # Fetch closed orders in period
            orders = self.client.table("orders") \
                .select("*") \
                .eq("status", "CLOSED") \
                .gte("closed_at", period_start.isoformat()) \
                .lte("closed_at", period_end.isoformat()) \
                .execute()
            
            if not orders.data:
                logger.info(f"No closed orders for period {period}")
                return
            
            # Calculate metrics
            total_trades = len(orders.data)
            winning_trades = sum(1 for o in orders.data if o["net_profit"] > 0)
            losing_trades = sum(1 for o in orders.data if o["net_profit"] < 0)
            break_even_trades = total_trades - winning_trades - losing_trades
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            total_profit = sum(o["net_profit"] for o in orders.data if o["net_profit"] > 0)
            total_loss = abs(sum(o["net_profit"] for o in orders.data if o["net_profit"] < 0))
            net_profit = total_profit - total_loss
            
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
            
            avg_win = (total_profit / winning_trades) if winning_trades > 0 else 0
            avg_loss = (total_loss / losing_trades) if losing_trades > 0 else 0
            
            largest_win = max((o["net_profit"] for o in orders.data), default=0)
            largest_loss = min((o["net_profit"] for o in orders.data), default=0)
            
            # Save metrics
            data = {
                "period": period,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "break_even_trades": break_even_trades,
                "win_rate": round(win_rate, 2),
                "total_profit": round(total_profit, 2),
                "total_loss": round(total_loss, 2),
                "net_profit": round(net_profit, 2),
                "profit_factor": round(profit_factor, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "largest_win": round(largest_win, 2),
                "largest_loss": round(largest_loss, 2),
            }
            
            # Upsert (insert or update)
            self.client.table("performance_metrics") \
                .upsert(data, on_conflict="period,period_start") \
                .execute()
            
            logger.info(f"✅ Performance metrics calculated for {period}: {total_trades} trades, {win_rate:.1f}% win rate")
        
        except Exception as e:
            logger.error(f"Failed to calculate performance metrics: {e}")
    
    def get_performance_metrics(self, period: str = "ALL_TIME") -> dict:
        """Get cached performance metrics"""
        if not self.is_enabled():
            return {}
        
        try:
            result = self.client.table("performance_metrics") \
                .select("*") \
                .eq("period", period) \
                .order("period_start", desc=True) \
                .limit(1) \
                .execute()
            
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Failed to fetch performance metrics: {e}")
            return {}
    
    # ── Risk Events ───────────────────────────────────────────────────────────
    
    def log_risk_event(
        self,
        event_type: str,
        description: str,
        action_taken: str,
        metadata: dict = None,
    ):
        """Log a risk management event"""
        if not self.is_enabled():
            return
        
        try:
            data = {
                "event_type": event_type,
                "description": description,
                "action_taken": action_taken,
                "metadata": metadata or {},
            }
            
            self.client.table("risk_events").insert(data).execute()
            logger.warning(f"⚠️ Risk event: {event_type} — {description}")
        
        except Exception as e:
            logger.error(f"Failed to log risk event: {e}")


# Global instance
db = DatabaseService()
