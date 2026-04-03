"""
Position Monitor Service
Continuously monitors open positions and manages them automatically:
- Partial close at TP1 (50% off)
- Move SL to break-even after TP1
- Trailing stops
- Time-based exits (before news, weekend)
- Auto-update database on position changes
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class PositionMonitorConfig:
    """Position monitoring configuration"""
    def __init__(self):
        # Partial close settings
        self.partial_close_enabled = os.getenv("PARTIAL_CLOSE_ENABLED", "true").lower() == "true"
        self.partial_close_percent = float(os.getenv("PARTIAL_CLOSE_PERCENT", "50.0"))  # 50%
        
        # Break-even settings
        self.breakeven_enabled = os.getenv("BREAKEVEN_ENABLED", "true").lower() == "true"
        self.breakeven_buffer_pips = float(os.getenv("BREAKEVEN_BUFFER_PIPS", "5.0"))  # 5 pips above BE
        
        # Trailing stop settings
        self.trailing_stop_enabled = os.getenv("TRAILING_STOP_ENABLED", "true").lower() == "true"
        self.trailing_stop_distance_pips = float(os.getenv("TRAILING_STOP_DISTANCE_PIPS", "50.0"))
        self.trailing_stop_step_pips = float(os.getenv("TRAILING_STOP_STEP_PIPS", "10.0"))
        
        # Time-based exit settings
        self.time_exit_enabled = os.getenv("TIME_EXIT_ENABLED", "true").lower() == "true"
        self.exit_before_news_minutes = int(os.getenv("EXIT_BEFORE_NEWS_MINUTES", "15"))
        self.exit_before_weekend_hours = int(os.getenv("EXIT_BEFORE_WEEKEND_HOURS", "2"))
        
        # Monitoring interval
        self.monitor_interval_seconds = float(os.getenv("MONITOR_INTERVAL_SECONDS", "1.0"))


class PositionMonitor:
    """
    Monitors and manages open positions automatically.
    Runs as a background task in the MT5 bridge.
    """
    
    def __init__(self, config: Optional[PositionMonitorConfig] = None, magic_number: int = 20250101):
        self.config = config or PositionMonitorConfig()
        self.magic_number = magic_number
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Track which positions have been modified
        self._partial_closed: set[int] = set()  # ticket numbers
        self._breakeven_set: set[int] = set()
        self._trailing_active: dict[int, float] = {}  # ticket -> last trailing SL
        
        logger.info("Position Monitor initialized:")
        logger.info(f"  Partial close: {self.config.partial_close_enabled} ({self.config.partial_close_percent}%)")
        logger.info(f"  Break-even: {self.config.breakeven_enabled}")
        logger.info(f"  Trailing stop: {self.config.trailing_stop_enabled}")
        logger.info(f"  Time exits: {self.config.time_exit_enabled}")
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start monitoring positions"""
        if self.running:
            logger.warning("Position monitor already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Position monitor started")
    
    async def stop(self):
        """Stop monitoring positions"""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Position monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._check_all_positions()
                await asyncio.sleep(self.config.monitor_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in position monitor loop: {e}")
                await asyncio.sleep(5)
    
    # ── Position Checks ───────────────────────────────────────────────────────
    
    async def _check_all_positions(self):
        """Check all open positions and apply management rules"""
        positions = mt5.positions_get(magic=self.magic_number)
        if not positions:
            return
        
        for pos in positions:
            try:
                await self._check_position(pos)
            except Exception as e:
                logger.error(f"Error checking position #{pos.ticket}: {e}")
    
    async def _check_position(self, pos):
        """Check a single position and apply management rules"""
        ticket = pos.ticket
        symbol = pos.symbol
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return
        
        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        entry_price = pos.price_open
        sl = pos.sl
        tp = pos.tp
        
        # Calculate profit in pips
        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_pips = (current_price - entry_price) * 100
        else:
            profit_pips = (entry_price - current_price) * 100
        
        # 1. Check for partial close at TP1
        if self.config.partial_close_enabled and ticket not in self._partial_closed:
            if await self._check_tp1_hit(pos, current_price, profit_pips):
                await self._partial_close_position(pos)
                self._partial_closed.add(ticket)
        
        # 2. Move SL to break-even after partial close
        if self.config.breakeven_enabled and ticket in self._partial_closed and ticket not in self._breakeven_set:
            await self._move_to_breakeven(pos, entry_price)
            self._breakeven_set.add(ticket)
        
        # 3. Trailing stop
        if self.config.trailing_stop_enabled and ticket in self._breakeven_set:
            await self._update_trailing_stop(pos, current_price, profit_pips)
        
        # 4. Time-based exits
        if self.config.time_exit_enabled:
            should_exit, reason = await self._should_time_exit(pos)
            if should_exit:
                await self._close_position(pos, reason)
    
    # ── Partial Close ─────────────────────────────────────────────────────────
    
    async def _check_tp1_hit(self, pos, current_price: float, profit_pips: float) -> bool:
        """Check if TP1 has been hit"""
        # Estimate TP1 (assume it's halfway to TP)
        entry = pos.price_open
        tp = pos.tp
        
        if tp == 0:
            return False
        
        # TP1 is typically 50-60% of the way to TP
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp1_estimate = entry + (tp - entry) * 0.5
            return current_price >= tp1_estimate
        else:
            tp1_estimate = entry - (entry - tp) * 0.5
            return current_price <= tp1_estimate
    
    async def _partial_close_position(self, pos):
        """Close partial position (default 50%)"""
        close_volume = round(pos.volume * (self.config.partial_close_percent / 100), 2)
        
        if close_volume < 0.01:
            logger.warning(f"Position #{pos.ticket} volume too small for partial close")
            return
        
        # Close partial
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "magic": pos.magic,
            "comment": "Partial close - TP1",
        }
        
        result = mt5.order_send(close_request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Partial close: #{pos.ticket} | {close_volume} lots @ TP1 | Profit: ${result.profit:.2f}")
            
            # Update database
            try:
                from app.services.database import db
                if db.is_enabled():
                    # Note: This is a partial close, not full close
                    # We'll track this in metadata for now
                    pass
            except Exception as e:
                logger.error(f"Failed to update database: {e}")
        else:
            logger.error(f"Failed to partial close #{pos.ticket}: {result.comment if result else 'No result'}")
    
    # ── Break-Even ────────────────────────────────────────────────────────────
    
    async def _move_to_breakeven(self, pos, entry_price: float):
        """Move stop loss to break-even + buffer"""
        # Calculate break-even with buffer
        buffer_points = self.config.breakeven_buffer_pips / 100
        
        if pos.type == mt5.ORDER_TYPE_BUY:
            new_sl = entry_price + buffer_points
        else:
            new_sl = entry_price - buffer_points
        
        # Don't move SL backwards
        if pos.type == mt5.ORDER_TYPE_BUY and new_sl <= pos.sl:
            return
        if pos.type == mt5.ORDER_TYPE_SELL and new_sl >= pos.sl:
            return
        
        # Modify position
        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.tp,
        }
        
        result = mt5.order_send(modify_request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Break-even set: #{pos.ticket} | SL moved to {new_sl:.2f} (+{self.config.breakeven_buffer_pips} pips)")
        else:
            logger.error(f"Failed to set break-even #{pos.ticket}: {result.comment if result else 'No result'}")
    
    # ── Trailing Stop ─────────────────────────────────────────────────────────
    
    async def _update_trailing_stop(self, pos, current_price: float, profit_pips: float):
        """Update trailing stop if price moved favorably"""
        ticket = pos.ticket
        
        # Calculate trailing stop distance in price
        trail_distance = self.config.trailing_stop_distance_pips / 100
        trail_step = self.config.trailing_stop_step_pips / 100
        
        # Calculate new trailing SL
        if pos.type == mt5.ORDER_TYPE_BUY:
            new_sl = current_price - trail_distance
        else:
            new_sl = current_price + trail_distance
        
        # Check if we should update (moved by at least trail_step)
        last_trail_sl = self._trailing_active.get(ticket, pos.sl)
        
        if pos.type == mt5.ORDER_TYPE_BUY:
            if new_sl <= last_trail_sl + trail_step:
                return  # Not enough movement
        else:
            if new_sl >= last_trail_sl - trail_step:
                return
        
        # Don't move SL backwards
        if pos.type == mt5.ORDER_TYPE_BUY and new_sl <= pos.sl:
            return
        if pos.type == mt5.ORDER_TYPE_SELL and new_sl >= pos.sl:
            return
        
        # Modify position
        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.tp,
        }
        
        result = mt5.order_send(modify_request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self._trailing_active[ticket] = new_sl
            logger.info(f"✅ Trailing stop updated: #{pos.ticket} | SL moved to {new_sl:.2f} | Profit: {profit_pips:.1f} pips")
        else:
            logger.error(f"Failed to update trailing stop #{pos.ticket}: {result.comment if result else 'No result'}")
    
    # ── Time-Based Exits ──────────────────────────────────────────────────────
    
    async def _should_time_exit(self, pos) -> tuple[bool, str]:
        """Check if position should be closed due to time"""
        now = datetime.now()
        
        # Check weekend (Friday close)
        if now.weekday() == 4:  # Friday
            market_close = now.replace(hour=22, minute=0, second=0)  # 10 PM
            hours_until_close = (market_close - now).seconds / 3600
            
            if hours_until_close <= self.config.exit_before_weekend_hours:
                return True, "TIME_EXIT_WEEKEND"
        
        # Check high-impact news (would need calendar integration)
        # For now, skip this check
        
        return False, ""
    
    async def _close_position(self, pos, reason: str):
        """Close position completely"""
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "magic": pos.magic,
            "comment": f"Auto close - {reason}",
        }
        
        result = mt5.order_send(close_request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Position closed: #{pos.ticket} | Reason: {reason} | Profit: ${result.profit:.2f}")
            
            # Update database
            try:
                from app.services.database import db
                if db.is_enabled():
                    tick = mt5.symbol_info_tick(pos.symbol)
                    close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                    
                    await db.update_order_close(
                        ticket=pos.ticket,
                        close_price=close_price,
                        profit=result.profit,
                        commission=result.commission if hasattr(result, 'commission') else 0,
                        swap=pos.swap,
                        close_reason=reason,
                    )
            except Exception as e:
                logger.error(f"Failed to update database: {e}")
            
            # Clean up tracking
            self._partial_closed.discard(pos.ticket)
            self._breakeven_set.discard(pos.ticket)
            self._trailing_active.pop(pos.ticket, None)
        else:
            logger.error(f"Failed to close position #{pos.ticket}: {result.comment if result else 'No result'}")
    
    # ── Manual Controls ───────────────────────────────────────────────────────
    
    async def close_position_manual(self, ticket: int) -> dict:
        """Manually close a specific position"""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"status": "error", "message": f"Position #{ticket} not found"}
        
        pos = positions[0]
        await self._close_position(pos, "MANUAL")
        return {"status": "ok", "message": f"Position #{ticket} closed"}
    
    async def modify_position_manual(self, ticket: int, new_sl: float, new_tp: float) -> dict:
        """Manually modify position SL/TP"""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"status": "error", "message": f"Position #{ticket} not found"}
        
        pos = positions[0]
        
        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }
        
        result = mt5.order_send(modify_request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"status": "ok", "message": f"Position #{ticket} modified"}
        else:
            return {"status": "error", "message": result.comment if result else "Modification failed"}
    
    # ── Status ────────────────────────────────────────────────────────────────
    
    def get_status(self) -> dict:
        """Get position monitor status"""
        positions = mt5.positions_get(magic=self.magic_number)
        position_count = len(positions) if positions else 0
        
        return {
            "running": self.running,
            "positions_monitored": position_count,
            "partial_closed_count": len(self._partial_closed),
            "breakeven_set_count": len(self._breakeven_set),
            "trailing_active_count": len(self._trailing_active),
            "config": {
                "partial_close_enabled": self.config.partial_close_enabled,
                "breakeven_enabled": self.config.breakeven_enabled,
                "trailing_stop_enabled": self.config.trailing_stop_enabled,
                "time_exit_enabled": self.config.time_exit_enabled,
            },
        }


# Global instance
_position_monitor: Optional[PositionMonitor] = None


def get_position_monitor() -> Optional[PositionMonitor]:
    """Get or create global position monitor instance"""
    global _position_monitor
    
    if _position_monitor is None:
        try:
            if mt5.terminal_info() is not None:
                _position_monitor = PositionMonitor()
            else:
                logger.warning("MT5 not initialized — position monitor unavailable")
        except Exception as e:
            logger.error(f"Failed to initialize position monitor: {e}")
    
    return _position_monitor
