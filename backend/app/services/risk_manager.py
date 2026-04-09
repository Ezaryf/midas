"""
Risk Management Service
Prevents account blowups through position sizing, exposure limits, and drawdown protection.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class RiskConfig:
    """Risk management configuration"""
    def __init__(self):
        # Position sizing
        self.max_risk_percent = float(os.getenv("MAX_RISK_PERCENT", "1.0"))  # 1% per trade
        self.min_lot_size = float(os.getenv("MIN_LOT_SIZE", "0.01"))
        self.max_lot_size = float(os.getenv("MAX_LOT_SIZE", "1.0"))
        
        # Exposure limits
        self.max_concurrent_positions = int(os.getenv("MAX_CONCURRENT_POSITIONS", "3"))
        self.max_daily_trades = int(os.getenv("MAX_DAILY_TRADES", "10"))
        
        # Loss limits
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "500.0"))  # $500
        self.max_drawdown_percent = float(os.getenv("MAX_DRAWDOWN_PERCENT", "20.0"))  # 20%
        
        # Margin requirements
        self.min_margin_level = float(os.getenv("MIN_MARGIN_LEVEL", "200.0"))  # 200%
        self.min_free_margin = float(os.getenv("MIN_FREE_MARGIN", "20.0"))  # $20 buffer (reduced from 1000 to allow small lots)
        
        # Correlation
        self.allow_hedging = os.getenv("ALLOW_HEDGING", "false").lower() == "true"
        
        # News blackout
        self.news_blackout_minutes = int(os.getenv("NEWS_BLACKOUT_MINUTES", "30"))


class RiskManager:
    """
    Manages trading risk through position sizing, exposure limits, and drawdown protection.
    """
    
    def __init__(self, config: Optional[RiskConfig] = None, magic_number: int = 20250101):
        self.config = config or RiskConfig()
        self.magic_number = magic_number
        self._daily_stats_cache = None
        self._daily_stats_timestamp = None
        
        logger.info("Risk Manager initialized:")
        logger.info(f"  Max risk per trade: {self.config.max_risk_percent}%")
        logger.info(f"  Daily loss limit: ${self.config.daily_loss_limit}")
        logger.info(f"  Max concurrent positions: {self.config.max_concurrent_positions}")
        logger.info(f"  Max daily trades: {self.config.max_daily_trades}")
    
    # ── Account Info ──────────────────────────────────────────────────────────
    
    def get_account_info(self) -> dict:
        """Get current account state"""
        account = mt5.account_info()
        if not account:
            return {}
        
        return {
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "free_margin": account.margin_free,
            "margin_level": account.margin_level if account.margin > 0 else 0,
            "profit": account.profit,
        }
    
    def get_open_positions(self) -> list:
        """Get all open positions for this magic number"""
        positions = mt5.positions_get(magic=self.magic_number)
        return list(positions) if positions else []
    
    def get_daily_stats(self, force_refresh: bool = False) -> dict:
        """Get today's trading statistics (cached for 1 minute)"""
        now = datetime.now()
        
        # Return cached if fresh
        if not force_refresh and self._daily_stats_cache and self._daily_stats_timestamp:
            if (now - self._daily_stats_timestamp).seconds < 60:
                return self._daily_stats_cache
        
        # Fetch deals from today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(today_start, now, magic=self.magic_number)
        
        if not deals:
            stats = {
                "daily_trades": 0,
                "daily_profit": 0.0,
                "daily_loss": 0.0,
                "daily_net": 0.0,
            }
        else:
            # Filter only OUT deals (position closes)
            out_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
            
            profits = [d.profit for d in out_deals if d.profit > 0]
            losses = [d.profit for d in out_deals if d.profit < 0]
            
            stats = {
                "daily_trades": len(out_deals),
                "daily_profit": sum(profits),
                "daily_loss": abs(sum(losses)),
                "daily_net": sum(d.profit for d in out_deals),
            }
        
        self._daily_stats_cache = stats
        self._daily_stats_timestamp = now
        return stats
    
    # ── Position Sizing ───────────────────────────────────────────────────────
    
    def calculate_lot_size(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: Optional[float] = None,
    ) -> float:
        """
        Calculate optimal lot size based on risk percentage.
        
        Formula:
        - Risk amount = Balance × Risk%
        - Pip risk = |Entry - SL| × 100 (for gold)
        - Lot size = Risk amount / Pip risk
        
        Example:
        - Balance: $10,000
        - Risk: 1% = $100
        - Entry: 2650, SL: 2640 → 10 points = 1000 pips
        - Lot size = 100 / 1000 = 0.10 lots
        """
        if account_balance is None:
            account = self.get_account_info()
            account_balance = account.get("balance", 10000)
        
        # Calculate risk amount
        risk_amount = account_balance * (self.config.max_risk_percent / 100)
        
        # Calculate pip risk (Gold: $1 = 100 pips)
        point_risk = abs(entry_price - stop_loss)
        pip_risk = point_risk * 100
        
        if pip_risk == 0:
            logger.warning("Zero pip risk — using minimum lot size")
            return self.config.min_lot_size
        
        # Calculate lot size
        lot_size = risk_amount / pip_risk
        
        # Clamp to min/max
        lot_size = max(self.config.min_lot_size, min(lot_size, self.config.max_lot_size))
        
        # Round to 2 decimals
        lot_size = round(lot_size, 2)
        
        logger.info(f"Position sizing: Balance ${account_balance:.2f} | Risk ${risk_amount:.2f} | Pip risk {pip_risk:.0f} → Lot {lot_size}")
        
        return lot_size

    def calculate_lot_size_from_shadow_performance(
        self,
        *,
        setup_type: str | None,
        base_lot_size: float,
    ) -> float:
        if not setup_type:
            return base_lot_size

        try:
            from app.services.database import db

            stats = db.get_setup_performance_stats(setup_type=setup_type)
        except Exception:
            stats = {}

        trades = int(stats.get("trades", 0) or 0)
        win_rate = float(stats.get("win_rate", 0.0) or 0.0)
        size_multiplier = 0.25
        if trades >= 20 and win_rate > 0.70:
            size_multiplier = 1.0
        elif trades >= 20 and win_rate >= 0.50:
            size_multiplier = 0.75

        adjusted = round(base_lot_size * size_multiplier, 2)
        adjusted = max(self.config.min_lot_size, min(adjusted, self.config.max_lot_size))
        logger.info(
            f"Shadow sizing: setup={setup_type} trades={trades} win_rate={win_rate:.2f} "
            f"multiplier={size_multiplier:.2f} -> lot {adjusted}"
        )
        return adjusted
    
    # ── Risk Checks ───────────────────────────────────────────────────────────
    
    def can_open_position(self, direction: str = "BUY", symbol: str = None, volume: float = None, price: float = None) -> tuple[bool, str]:
        """
        Check if opening a new position is allowed.
        Returns (allowed: bool, reason: str)
        """
        
        # 1. Check daily loss limit
        daily_stats = self.get_daily_stats()
        if daily_stats["daily_loss"] >= self.config.daily_loss_limit:
            return False, f"Daily loss limit reached: ${daily_stats['daily_loss']:.2f} / ${self.config.daily_loss_limit:.2f}"
        
        # 2. Check max daily trades
        if daily_stats["daily_trades"] >= self.config.max_daily_trades:
            return False, f"Max daily trades reached: {daily_stats['daily_trades']} / {self.config.max_daily_trades}"
        
        # 3. Check max concurrent positions
        open_positions = self.get_open_positions()
        if len(open_positions) >= self.config.max_concurrent_positions:
            return False, f"Max concurrent positions reached: {len(open_positions)} / {self.config.max_concurrent_positions}"
        
        # 4. Check correlation (no hedging)
        if not self.config.allow_hedging and open_positions:
            existing_directions = {p.type for p in open_positions}
            new_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            
            # Check if opposite direction exists
            if new_type == mt5.ORDER_TYPE_BUY and mt5.ORDER_TYPE_SELL in existing_directions:
                return False, "Hedging not allowed: Already have SELL position"
            if new_type == mt5.ORDER_TYPE_SELL and mt5.ORDER_TYPE_BUY in existing_directions:
                return False, "Hedging not allowed: Already have BUY position"
        
        # 5. Check margin level
        account = self.get_account_info()
        if account.get("margin_level", 0) > 0 and account["margin_level"] < self.config.min_margin_level:
            return False, f"Margin level too low: {account['margin_level']:.1f}% < {self.config.min_margin_level}%"
        
        # 6. Check free margin
        free_margin = account.get("free_margin", 0)
        
        if symbol and volume and price:
            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            margin_required = mt5.order_calc_margin(order_type, symbol, volume, price)
            if margin_required:
                total_required = margin_required + self.config.min_free_margin
                if free_margin < total_required:
                    return False, f"Insufficient free margin for {volume} lots: ${free_margin:.2f} < req ${margin_required:.2f} + buffer ${self.config.min_free_margin:.2f}"
            else:
                # If mt5.order_calc_margin fails, fall back to basic check
                if free_margin < self.config.min_free_margin:
                    return False, f"Insufficient free margin buffer: ${free_margin:.2f} < req buffer ${self.config.min_free_margin:.2f}"
        else:
            # Legacy check without symbol/volume 
            if free_margin < self.config.min_free_margin:
                return False, f"Insufficient free margin buffer: ${free_margin:.2f} < req buffer ${self.config.min_free_margin:.2f}"
        
        # 7. Check drawdown
        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        if balance > 0:
            drawdown_percent = ((balance - equity) / balance) * 100
            if drawdown_percent > self.config.max_drawdown_percent:
                return False, f"Max drawdown exceeded: {drawdown_percent:.1f}% > {self.config.max_drawdown_percent}%"
        
        return True, "OK"
    
    def should_close_all_positions(self) -> tuple[bool, str]:
        """
        Check if all positions should be force-closed due to risk limits.
        Returns (should_close: bool, reason: str)
        """
        
        # Check daily loss limit
        daily_stats = self.get_daily_stats()
        if daily_stats["daily_loss"] >= self.config.daily_loss_limit:
            return True, f"Daily loss limit reached: ${daily_stats['daily_loss']:.2f}"
        
        # Check drawdown
        account = self.get_account_info()
        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        if balance > 0:
            drawdown_percent = ((balance - equity) / balance) * 100
            if drawdown_percent > self.config.max_drawdown_percent:
                return True, f"Max drawdown exceeded: {drawdown_percent:.1f}%"
        
        # Check margin level (critical)
        if account.get("margin_level", 0) > 0 and account["margin_level"] < 100:
            return True, f"Critical margin level: {account['margin_level']:.1f}%"
        
        return False, "OK"
    
    # ── News Blackout ─────────────────────────────────────────────────────────
    
    def is_news_blackout(self, calendar_events: list) -> tuple[bool, str]:
        """
        Check if we're in a news blackout period.
        Returns (is_blackout: bool, reason: str)
        """
        if not calendar_events:
            return False, "OK"
        
        now = datetime.now()
        blackout_window = timedelta(minutes=self.config.news_blackout_minutes)
        
        for event in calendar_events:
            # Parse event time (assuming ISO format or similar)
            try:
                event_time = datetime.fromisoformat(event.get("time", ""))
                time_until = event_time - now
                
                # Check if high-impact event within blackout window
                if event.get("impact") == "High" and abs(time_until) < blackout_window:
                    return True, f"High-impact news in {time_until.seconds // 60} minutes: {event.get('title')}"
            except (ValueError, TypeError, KeyError):
                continue
        
        return False, "OK"
    
    # ── Per-Position Risk ───────────────────────────────────────────────────────

    def get_position_level_risk(self) -> list[dict]:
        """Get per-position P&L and risk metrics for real-time drawdown visibility."""
        positions = self.get_open_positions()
        results = []
        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                continue
            current = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            pnl_points = (current - pos.price_open) if pos.type == mt5.ORDER_TYPE_BUY else (pos.price_open - current)
            risk_points = abs(pos.price_open - pos.sl) if pos.sl else 0
            results.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "entry_price": round(pos.price_open, 2),
                "current_price": round(current, 2),
                "pnl_points": round(pnl_points, 2),
                "pnl_dollars": round(pos.profit, 2),
                "risk_points": round(risk_points, 2),
                "rr_current": round(pnl_points / risk_points, 2) if risk_points > 0 else 0,
                "sl": round(pos.sl, 2) if pos.sl else None,
                "tp": round(pos.tp, 2) if pos.tp else None,
            })
        return results

    # ── Risk Reporting ────────────────────────────────────────────────────────
    
    def get_risk_summary(self) -> dict:
        """Get comprehensive risk status summary with per-position breakdown"""
        account = self.get_account_info()
        daily_stats = self.get_daily_stats()
        open_positions = self.get_open_positions()
        position_risk = self.get_position_level_risk()
        
        can_trade, trade_reason = self.can_open_position()
        should_close, close_reason = self.should_close_all_positions()

        # Real-time drawdown from live positions
        total_unrealized_pnl = sum(p["pnl_dollars"] for p in position_risk)
        worst_position_pnl = min((p["pnl_dollars"] for p in position_risk), default=0)
        
        return {
            "can_trade": can_trade,
            "trade_status": trade_reason,
            "should_close_all": should_close,
            "close_reason": close_reason,
            
            "account": {
                "balance": account.get("balance", 0),
                "equity": account.get("equity", 0),
                "margin_level": account.get("margin_level", 0),
                "free_margin": account.get("free_margin", 0),
            },
            
            "daily": {
                "trades": daily_stats["daily_trades"],
                "profit": daily_stats["daily_profit"],
                "loss": daily_stats["daily_loss"],
                "net": daily_stats["daily_net"],
                "remaining_loss_buffer": self.config.daily_loss_limit - daily_stats["daily_loss"],
            },
            
            "positions": {
                "open": len(open_positions),
                "max": self.config.max_concurrent_positions,
                "remaining": self.config.max_concurrent_positions - len(open_positions),
                "details": position_risk,
                "unrealized_pnl": round(total_unrealized_pnl, 2),
                "worst_position_pnl": round(worst_position_pnl, 2),
            },
            
            "limits": {
                "max_risk_percent": self.config.max_risk_percent,
                "daily_loss_limit": self.config.daily_loss_limit,
                "max_concurrent_positions": self.config.max_concurrent_positions,
                "max_daily_trades": self.config.max_daily_trades,
            },
        }


# Global instance (initialized when MT5 is available)
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> Optional[RiskManager]:
    """Get or create global risk manager instance"""
    global _risk_manager
    
    if _risk_manager is None:
        try:
            # Check if MT5 is initialized
            if mt5.terminal_info() is not None:
                _risk_manager = RiskManager()
            else:
                logger.warning("MT5 not initialized — risk manager unavailable")
        except Exception as e:
            logger.error(f"Failed to initialize risk manager: {e}")
    
    return _risk_manager
