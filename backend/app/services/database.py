"""
Database service for MySQL integration.
Handles all database operations for trade history, analytics, and risk management.
With auto-reconnect and graceful degradation when MySQL is unavailable.
"""
import os
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import mysql.connector
    from mysql.connector import pooling
except ImportError:
    mysql = None  # type: ignore
    pooling = None  # type: ignore

from app.schemas.signal import TradeSignal

logger = logging.getLogger(__name__)

# Reconnect backoff: 30s â†’ 60s â†’ 120s â†’ 240s max
_RECONNECT_BASE_SECONDS = 30
_RECONNECT_MAX_SECONDS = 240


def _json_dumps(value):
    return json.dumps(value) if value is not None else None


def _parse_mysql_url(url: str) -> dict:
    """Parse mysql://user:pass@host:port/database into connection kwargs."""
    from urllib.parse import unquote

    # mysql://user:password@host:port/database
    url = url.strip()
    if url.startswith("mysql://"):
        url = url[len("mysql://"):]
    elif url.startswith("mysql+pymysql://"):
        url = url[len("mysql+pymysql://"):]

    # user:password@host:port/database
    at_idx = url.rfind("@")
    if at_idx == -1:
        raise ValueError(f"Invalid MySQL URL â€” no '@' found")

    user_pass = url[:at_idx]
    host_db = url[at_idx + 1:]

    user, password = user_pass.split(":", 1) if ":" in user_pass else (user_pass, "")
    # URL-decode user and password (e.g. %40 â†’ @)
    user = unquote(user)
    password = unquote(password)

    slash_idx = host_db.find("/")
    if slash_idx == -1:
        host_port = host_db
        database = "midas"
    else:
        host_port = host_db[:slash_idx]
        database = host_db[slash_idx + 1:].split("?")[0]

    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 3306

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": database,
    }


class DatabaseService:
    def __init__(self):
        self._mysql_url = os.getenv("MYSQL_URL") or os.getenv("DATABASE_URL")
        self._pool: Optional[pooling.MySQLConnectionPool] = None
        self._reconnect_attempts: int = 0
        self._last_reconnect_time: float = 0

        self._connect()

    def _connect(self):
        """Attempt to connect to MySQL."""
        if not self._mysql_url:
            logger.warning("MySQL URL not configured â€” database features disabled")
            return

        if mysql is None:
            logger.warning("mysql-connector-python not installed â€” database features disabled")
            return

        try:
            params = _parse_mysql_url(self._mysql_url)
            self._pool = pooling.MySQLConnectionPool(
                pool_name="midas_pool",
                pool_size=5,
                pool_reset_session=True,
                **params,
            )
            self._reconnect_attempts = 0

            # Auto-create tables if they don't exist
            self._ensure_tables()

            logger.info("âœ… Connected to MySQL")
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            self._pool = None

    def _get_conn(self):
        """Get a connection from the pool."""
        if self._pool is None:
            return None
        try:
            return self._pool.get_connection()
        except Exception:
            self._pool = None
            return None


    def _column_exists(self, table: str, column: str) -> bool:
        """Check if a column exists in a specific table."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name = %s
                  AND table_schema = (SELECT DATABASE())
            """
            cursor.execute(query, (table, column))
            res = cursor.fetchone()
            cursor.close()
            return bool(res and res[0] > 0)
        except Exception:
            return False
        finally:
            conn.close()

    def _add_column_if_missing(self, table: str, column: str, definition: str):
        """Safely add a column to an existing table if it doesn't exist."""
        if self._column_exists(table, column):
            return

        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            conn.commit()
            cursor.close()
            logger.info(f"✅ Added missing column '{column}' to table '{table}'")
        except Exception as e:
            logger.error(f"Failed to add column '{column}' to table '{table}': {e}")
        finally:
            conn.close()

    def _ensure_tables(self):
        """Create tables if they do not exist."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    direction VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20),
                    analysis_batch_id VARCHAR(64),
                    entry_price DECIMAL(12,4) NOT NULL,
                    stop_loss DECIMAL(12,4) NOT NULL,
                    take_profit_1 DECIMAL(12,4) NOT NULL,
                    take_profit_2 DECIMAL(12,4) NOT NULL,
                    confidence DECIMAL(5,2) NOT NULL,
                    reasoning TEXT NOT NULL,
                    trading_style VARCHAR(20) NOT NULL,
                    setup_type VARCHAR(50),
                    market_regime VARCHAR(50),
                    score DECIMAL(5,2),
                    `rank` INT,
                    is_primary TINYINT(1),
                    entry_window_low DECIMAL(12,4),
                    entry_window_high DECIMAL(12,4),
                    context_tags JSON,
                    source VARCHAR(50),
                    status VARCHAR(20),
                    outcome DECIMAL(12,4),
                    indicators JSON,
                    context JSON,
                    current_price DECIMAL(12,4),
                    trend VARCHAR(20),
                    ai_provider VARCHAR(30),
                    ai_model VARCHAR(50),
                    INDEX idx_created (created_at),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    account_id VARCHAR(36) PRIMARY KEY,
                    config_json JSON NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id VARCHAR(36) PRIMARY KEY,
                    signal_id VARCHAR(36),
                    ticket INT NOT NULL UNIQUE,
                    direction VARCHAR(10) NOT NULL,
                    entry_price DECIMAL(12,4) NOT NULL,
                    stop_loss DECIMAL(12,4) NOT NULL,
                    take_profit DECIMAL(12,4) NOT NULL,
                    lot_size DECIMAL(8,4) NOT NULL,
                    magic_number INT NOT NULL,
                    comment VARCHAR(255),
                    status VARCHAR(20) DEFAULT 'OPEN',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    closed_at DATETIME,
                    close_price DECIMAL(12,4),
                    profit DECIMAL(12,4),
                    commission DECIMAL(12,4),
                    swap DECIMAL(12,4),
                    close_reason VARCHAR(50),
                    INDEX idx_ticket (ticket),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    balance DECIMAL(14,2),
                    equity DECIMAL(14,2),
                    margin_used DECIMAL(14,2),
                    free_margin DECIMAL(14,2),
                    margin_level DECIMAL(10,2),
                    open_positions INT,
                    pending_orders INT,
                    daily_profit DECIMAL(14,2),
                    daily_trades INT,
                    INDEX idx_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id VARCHAR(36) PRIMARY KEY,
                    period VARCHAR(20) NOT NULL,
                    period_start DATETIME NOT NULL,
                    period_end DATETIME NOT NULL,
                    total_trades INT,
                    winning_trades INT,
                    losing_trades INT,
                    break_even_trades INT,
                    win_rate DECIMAL(5,2),
                    total_profit DECIMAL(14,2),
                    total_loss DECIMAL(14,2),
                    net_profit DECIMAL(14,2),
                    profit_factor DECIMAL(8,2),
                    avg_win DECIMAL(14,2),
                    avg_loss DECIMAL(14,2),
                    largest_win DECIMAL(14,2),
                    largest_loss DECIMAL(14,2),
                    UNIQUE INDEX idx_period (period, period_start)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_events (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type VARCHAR(50) NOT NULL,
                    description TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    metadata JSON,
                    INDEX idx_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Ensure orders table has required newer columns
            self._add_column_if_missing("orders", "symbol", "VARCHAR(20)")
            self._add_column_if_missing("orders", "analysis_batch_id", "VARCHAR(64)")
            self._add_column_if_missing("orders", "setup_type", "VARCHAR(64)")
            self._add_column_if_missing("orders", "signal_context", "JSON")
            self._add_column_if_missing("orders", "entry_spread", "DECIMAL(12,4)")
            self._add_column_if_missing("orders", "slippage_points", "DECIMAL(12,4)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_quality_log (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol VARCHAR(20),
                    timeframe VARCHAR(10),
                    source VARCHAR(50),
                    age_seconds DECIMAL(12,4),
                    is_fresh TINYINT(1),
                    allowed_strategy_class VARCHAR(32),
                    signals_blocked INT DEFAULT 0,
                    INDEX idx_data_quality_created (created_at),
                    INDEX idx_data_quality_symbol (symbol, timeframe)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shadow_candidates (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    analysis_batch_id VARCHAR(64),
                    signal_id VARCHAR(36),
                    signal_timestamp DATETIME,
                    symbol VARCHAR(20),
                    trading_style VARCHAR(20),
                    timeframe VARCHAR(10),
                    direction VARCHAR(10),
                    setup_type VARCHAR(64),
                    entry_price DECIMAL(12,4),
                    stop_loss DECIMAL(12,4),
                    take_profit_1 DECIMAL(12,4),
                    take_profit_2 DECIMAL(12,4),
                    score DECIMAL(8,4),
                    rank_order INT,
                    regime_at_signal VARCHAR(50),
                    session_at_signal VARCHAR(16),
                    source_data_fresh VARCHAR(32),
                    regime_confidence_at_entry DECIMAL(8,4),
                    volatility_at_entry DECIMAL(12,4),
                    spread_estimate DECIMAL(12,4),
                    compression_ratio_at_entry DECIMAL(12,4),
                    simulated_entry_bar_index INT,
                    simulated_exit_bar_index INT,
                    simulated_outcome VARCHAR(24),
                    actual_entry_price DECIMAL(12,4),
                    actual_exit_price DECIMAL(12,4),
                    actual_pnl_points DECIMAL(12,4),
                    actual_pnl_dollars DECIMAL(12,4),
                    actual_outcome VARCHAR(24),
                    mfe_points DECIMAL(12,4),
                    mae_points DECIMAL(12,4),
                    tp1_hit TINYINT(1),
                    tp2_hit TINYINT(1),
                    sl_hit TINYINT(1),
                    actual_spread DECIMAL(12,4),
                    slippage_points DECIMAL(12,4),
                    status VARCHAR(24) DEFAULT 'pending',
                    INDEX idx_shadow_status (status),
                    INDEX idx_shadow_symbol (symbol, timeframe)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ticket INT,
                    signal_id VARCHAR(36),
                    analysis_batch_id VARCHAR(64),
                    symbol VARCHAR(20),
                    direction VARCHAR(10),
                    setup_type VARCHAR(64),
                    trading_style VARCHAR(20),
                    intended_entry_price DECIMAL(12,4),
                    intended_stop_loss DECIMAL(12,4),
                    intended_take_profit_1 DECIMAL(12,4),
                    actual_entry_price DECIMAL(12,4),
                    actual_exit_price DECIMAL(12,4),
                    actual_entry_time DATETIME,
                    actual_exit_time DATETIME,
                    regime_at_signal VARCHAR(50),
                    regime_confidence_at_signal DECIMAL(8,4),
                    session_at_signal VARCHAR(16),
                    volatility_bucket_at_signal VARCHAR(16),
                    spread_at_signal DECIMAL(12,4),
                    data_source_at_signal VARCHAR(50),
                    compression_ratio_at_entry DECIMAL(12,4),
                    efficiency_ratio_at_entry DECIMAL(12,4),
                    close_location_at_entry DECIMAL(12,4),
                    body_strength_at_entry DECIMAL(12,4),
                    pnl_points DECIMAL(12,4),
                    pnl_dollars DECIMAL(12,4),
                    outcome VARCHAR(24),
                    actual_spread DECIMAL(12,4),
                    slippage_points DECIMAL(12,4),
                    fill_quality VARCHAR(16),
                    UNIQUE INDEX idx_signal_outcomes_ticket (ticket),
                    INDEX idx_signal_outcomes_signal (signal_id),
                    INDEX idx_signal_outcomes_regime (regime_at_signal, session_at_signal)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimized_weights (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol VARCHAR(20),
                    trading_style VARCHAR(20),
                    timeframe VARCHAR(10),
                    train_start DATETIME,
                    train_end DATETIME,
                    validate_start DATETIME,
                    validate_end DATETIME,
                    method VARCHAR(32),
                    objective_score DECIMAL(12,6),
                    weights JSON
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kill_switch_events (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol VARCHAR(20),
                    action VARCHAR(32),
                    reasons JSON,
                    context JSON,
                    INDEX idx_kill_switch_created (created_at),
                    INDEX idx_kill_switch_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_decisions (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    signal_id VARCHAR(36),
                    symbol VARCHAR(20),
                    signal_direction VARCHAR(10),
                    signal_confidence DECIMAL(8,4),
                    had_position TINYINT(1),
                    position_direction VARCHAR(10),
                    position_pnl_points DECIMAL(12,4),
                    position_pnl_dollars DECIMAL(12,4),
                    position_age_minutes DECIMAL(12,4),
                    action VARCHAR(24),
                    reason TEXT,
                    executed TINYINT(1) DEFAULT 0,
                    execution_result TEXT,
                    INDEX idx_position_decisions_created (created_at),
                    INDEX idx_position_decisions_signal (signal_id),
                    INDEX idx_position_decisions_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()
            cursor.close()
            logger.info("âœ… MySQL tables verified/created")
        except Exception as e:
            logger.error(f"Failed to ensure MySQL tables: {e}")
        finally:
            conn.close()

    def _try_reconnect(self) -> bool:
        """Attempt reconnection with exponential backoff."""
        if not self._mysql_url:
            return False
        if mysql is None:
            return False

        backoff = min(
            _RECONNECT_BASE_SECONDS * (2 ** self._reconnect_attempts),
            _RECONNECT_MAX_SECONDS,
        )
        elapsed = time.time() - self._last_reconnect_time
        if elapsed < backoff:
            return False

        self._last_reconnect_time = time.time()
        self._reconnect_attempts += 1
        logger.info(f"Attempting MySQL reconnect (attempt {self._reconnect_attempts}, backoff {backoff}s)...")

        try:
            params = _parse_mysql_url(self._mysql_url)
            self._pool = pooling.MySQLConnectionPool(
                pool_name="midas_pool",
                pool_size=5,
                pool_reset_session=True,
                **params,
            )
            self._reconnect_attempts = 0
            logger.info("âœ… MySQL reconnected successfully")
            return True
        except Exception as e:
            logger.warning(f"MySQL reconnect failed: {e}")
            self._pool = None
            return False

    def is_enabled(self) -> bool:
        if self._pool is not None:
            return True
        return self._try_reconnect()

    # â”€â”€ Signals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

        conn = self._get_conn()
        if not conn:
            return "db_disabled"

        try:
            signal_id = str(uuid.uuid4())
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO signals (
                    id, direction, entry_price, stop_loss,
                    take_profit_1, take_profit_2, confidence, reasoning,
                    symbol, analysis_batch_id, trading_style, setup_type,
                    market_regime, score, `rank`, is_primary,
                    entry_window_low, entry_window_high, context_tags, source,
                    status, context, indicators, current_price, trend,
                    ai_provider, ai_model
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )""",
                (
                    signal_id,
                    signal.direction,
                    float(signal.entry_price),
                    float(signal.stop_loss),
                    float(signal.take_profit_1),
                    float(signal.take_profit_2),
                    float(signal.confidence),
                    signal.reasoning,
                    signal.symbol,
                    signal.analysis_batch_id,
                    signal.trading_style,
                    signal.setup_type,
                    signal.market_regime,
                    float(signal.score) if signal.score is not None else None,
                    int(signal.rank) if signal.rank is not None else None,
                    bool(signal.is_primary) if signal.is_primary is not None else None,
                    float(signal.entry_window_low) if signal.entry_window_low is not None else None,
                    float(signal.entry_window_high) if signal.entry_window_high is not None else None,
                    _json_dumps(signal.context_tags) if signal.context_tags else None,
                    signal.source,
                    "NO_TRADE" if signal.direction == "HOLD" else "NEW",
                    _json_dumps({
                        "regime_summary": regime_summary,
                        "context_tags": signal.context_tags,
                        "source": signal.source,
                        "no_trade_reasons": signal.no_trade_reasons,
                        "execution_mode": signal.execution_mode,
                        "forced_from_hold": signal.forced_from_hold,
                        "bypassed_blockers": signal.bypassed_blockers,
                        "source_candidate_stage": signal.source_candidate_stage,
                        "position_action": signal.position_action,
                        "position_action_reason": signal.position_action_reason,
                        "is_duplicate": signal.is_duplicate,
                        "calibrated_confidence": signal.calibrated_confidence,
                        "confidence_source": signal.confidence_source,
                    }),
                    _json_dumps(indicators),
                    float(current_price),
                    trend,
                    ai_provider,
                    ai_model,
                ),
            )
            conn.commit()
            cursor.close()
            logger.info(f"âœ… Signal saved to MySQL: {signal_id}")
            return signal_id

        except Exception as e:
            logger.error(f"Failed to save signal to MySQL: {e}")
            return "error"
        finally:
            conn.close()

    def get_recent_signals(self, limit: int = 10) -> list:
        if not self.is_enabled():
            return []

        conn = self._get_conn()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch signals: {e}")
            return []
        finally:
            conn.close()

    def get_signal_by_id(self, signal_id: str | None) -> dict:
        if not signal_id or not self.is_enabled():
            return {}

        conn = self._get_conn()
        if not conn:
            return {}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM signals WHERE id = %s LIMIT 1", (signal_id,))
            row = cursor.fetchone()
            cursor.close()
            return row or {}
        except Exception as e:
            logger.error(f"Failed to fetch signal {signal_id}: {e}")
            return {}
        finally:
            conn.close()

    def update_signal_reasoning(self, signal_id: str, reasoning: str, ai_provider: str, ai_model: str) -> bool:
        """Update a signal's reasoning after asynchronous AI explanation completes."""
        if not self.is_enabled():
            return False

        conn = self._get_conn()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE signals SET
                    reasoning = %s,
                    ai_provider = %s,
                    ai_model = %s
                WHERE id = %s""",
                (reasoning, ai_provider, ai_model, signal_id),
            )
            conn.commit()
            cursor.close()
            logger.info(f"âœ… AI Reasoning updated for signal {signal_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update signal reasoning for {signal_id}: {e}")
            return False
        finally:
            conn.close()

    # â”€â”€ Orders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        symbol: str | None = None,
        analysis_batch_id: str | None = None,
        setup_type: str | None = None,
        signal_context: dict | None = None,
        entry_spread: float | None = None,
        slippage_points: float | None = None,
    ) -> str:
        if not self.is_enabled():
            return "db_disabled"

        conn = self._get_conn()
        if not conn:
            return "db_disabled"

        try:
            order_id = str(uuid.uuid4())
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO orders (
                    id, signal_id, ticket, direction, entry_price,
                    stop_loss, take_profit, lot_size, magic_number, comment, status,
                    symbol, analysis_batch_id, setup_type, signal_context, entry_spread, slippage_points
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    order_id,
                    signal_id if signal_id != "db_disabled" else None,
                    ticket, direction, float(entry_price),
                    float(stop_loss), float(take_profit), float(lot_size),
                    magic_number, comment, "OPEN",
                    symbol,
                    analysis_batch_id,
                    setup_type,
                    _json_dumps(signal_context or {}),
                    float(entry_spread) if entry_spread is not None else None,
                    float(slippage_points) if slippage_points is not None else None,
                ),
            )
            conn.commit()
            cursor.close()
            logger.info(f"âœ… Order saved to MySQL: ticket #{ticket}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return "error"
        finally:
            conn.close()

    def update_order_close(
        self,
        ticket: int,
        close_price: float,
        profit: float,
        commission: float,
        swap: float,
        close_reason: str,
    ):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE orders SET
                    status = 'CLOSED',
                    closed_at = NOW(),
                    close_price = %s,
                    profit = %s,
                    commission = %s,
                    swap = %s,
                    close_reason = %s
                WHERE ticket = %s AND status <> 'CLOSED'""",
                (float(close_price), float(profit), float(commission), float(swap), close_reason, ticket),
            )
            conn.commit()
            cursor.close()
            logger.info(f"âœ… Order #{ticket} closed: {close_reason} | P&L: {profit}")
        except Exception as e:
            logger.error(f"Failed to update order close: {e}")
        finally:
            conn.close()

    def get_open_orders(self) -> list:
        if not self.is_enabled():
            return []

        conn = self._get_conn()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM orders WHERE status = 'OPEN'")
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            return []
        finally:
            conn.close()

    def get_order_by_ticket(self, ticket: int) -> dict:
        if not self.is_enabled():
            return {}

        conn = self._get_conn()
        if not conn:
            return {}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM orders WHERE ticket = %s LIMIT 1", (ticket,))
            row = cursor.fetchone()
            cursor.close()
            return row or {}
        except Exception as e:
            logger.error(f"Failed to fetch order #{ticket}: {e}")
            return {}
        finally:
            conn.close()

    # â”€â”€ Account Snapshots â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO account_snapshots (
                    id, balance, equity, margin_used, free_margin,
                    margin_level, open_positions, pending_orders,
                    daily_profit, daily_trades
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    float(balance), float(equity), float(margin), float(free_margin),
                    float(margin_level), open_positions, pending_orders,
                    float(daily_profit), daily_trades,
                ),
            )
            conn.commit()
            cursor.close()
            logger.debug("Account snapshot saved")
        except Exception as e:
            logger.error(f"Failed to save account snapshot: {e}")
        finally:
            conn.close()

    def get_equity_curve(self, days: int = 30) -> list:
        if not self.is_enabled():
            return []

        conn = self._get_conn()
        if not conn:
            return []

        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT created_at, equity, balance FROM account_snapshots WHERE created_at >= %s ORDER BY created_at",
                (cutoff,),
            )
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch equity curve: {e}")
            return []
        finally:
            conn.close()

    # â”€â”€ Performance Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def calculate_performance_metrics(self, period: str = "ALL_TIME"):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            now = datetime.now(timezone.utc)
            if period == "DAILY":
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "WEEKLY":
                period_start = now - timedelta(days=now.weekday())
            elif period == "MONTHLY":
                period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                period_start = datetime(2020, 1, 1, tzinfo=timezone.utc)

            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT * FROM orders
                   WHERE status = 'CLOSED'
                     AND closed_at >= %s AND closed_at <= %s""",
                (period_start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")),
            )
            orders = cursor.fetchall()

            if not orders:
                cursor.close()
                logger.info(f"No closed orders for period {period}")
                return

            total = len(orders)
            wins = sum(1 for o in orders if float(o.get("profit", 0)) > 0)
            losses = sum(1 for o in orders if float(o.get("profit", 0)) < 0)
            be = total - wins - losses

            total_profit = sum(float(o["profit"]) for o in orders if float(o.get("profit", 0)) > 0)
            total_loss = abs(sum(float(o["profit"]) for o in orders if float(o.get("profit", 0)) < 0))
            net = total_profit - total_loss
            pf = (total_profit / total_loss) if total_loss > 0 else 0
            aw = (total_profit / wins) if wins > 0 else 0
            al = (total_loss / losses) if losses > 0 else 0
            lw = max((float(o["profit"]) for o in orders), default=0)
            ll = min((float(o["profit"]) for o in orders), default=0)

            metric_id = str(uuid.uuid4())
            cursor.execute(
                """INSERT INTO performance_metrics (
                    id, period, period_start, period_end,
                    total_trades, winning_trades, losing_trades, break_even_trades,
                    win_rate, total_profit, total_loss, net_profit,
                    profit_factor, avg_win, avg_loss, largest_win, largest_loss
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    period_end = VALUES(period_end),
                    total_trades = VALUES(total_trades),
                    winning_trades = VALUES(winning_trades),
                    losing_trades = VALUES(losing_trades),
                    break_even_trades = VALUES(break_even_trades),
                    win_rate = VALUES(win_rate),
                    total_profit = VALUES(total_profit),
                    total_loss = VALUES(total_loss),
                    net_profit = VALUES(net_profit),
                    profit_factor = VALUES(profit_factor),
                    avg_win = VALUES(avg_win),
                    avg_loss = VALUES(avg_loss),
                    largest_win = VALUES(largest_win),
                    largest_loss = VALUES(largest_loss)
                """,
                (
                    metric_id, period,
                    period_start.strftime("%Y-%m-%d %H:%M:%S"),
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    total, wins, losses, be,
                    round(wins / total * 100, 2) if total > 0 else 0,
                    round(total_profit, 2), round(total_loss, 2), round(net, 2),
                    round(pf, 2), round(aw, 2), round(al, 2),
                    round(lw, 2), round(ll, 2),
                ),
            )
            conn.commit()
            cursor.close()
            logger.info(f"âœ… Performance metrics calculated for {period}")
        except Exception as e:
            logger.error(f"Failed to calculate performance metrics: {e}")
        finally:
            conn.close()

    def get_performance_metrics(self, period: str = "ALL_TIME") -> dict:
        if not self.is_enabled():
            return {}

        conn = self._get_conn()
        if not conn:
            return {}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM performance_metrics WHERE period = %s ORDER BY period_start DESC LIMIT 1",
                (period,),
            )
            row = cursor.fetchone()
            cursor.close()
            return row if row else {}
        except Exception as e:
            logger.error(f"Failed to fetch performance metrics: {e}")
            return {}
        finally:
            conn.close()

    # â”€â”€ Risk Events â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def log_risk_event(
        self,
        event_type: str,
        description: str,
        action_taken: str,
        metadata: dict = None,
    ):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO risk_events (id, event_type, description, action_taken, metadata)
                   VALUES (%s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), event_type, description, action_taken, json.dumps(metadata or {})),
            )
            conn.commit()
            cursor.close()
            logger.warning(f"âš ï¸ Risk event: {event_type} â€” {description}")
        except Exception as e:
            logger.error(f"Failed to log risk event: {e}")
        finally:
            conn.close()

    def log_data_quality_event(
        self,
        *,
        symbol: str,
        timeframe: str,
        source: str,
        age_seconds: float,
        is_fresh: bool,
        allowed_strategy_class: str,
        signals_blocked: int,
    ):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO data_quality_log (
                    id, symbol, timeframe, source, age_seconds,
                    is_fresh, allowed_strategy_class, signals_blocked
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    symbol,
                    timeframe,
                    source,
                    float(age_seconds),
                    bool(is_fresh),
                    allowed_strategy_class,
                    int(signals_blocked),
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to log data quality event: {e}")
        finally:
            conn.close()

    def save_shadow_candidate(self, payload: dict) -> str:
        if not self.is_enabled():
            return "db_disabled"

        conn = self._get_conn()
        if not conn:
            return "db_disabled"

        try:
            record_id = str(uuid.uuid4())
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO shadow_candidates (
                    id, analysis_batch_id, signal_id, signal_timestamp, symbol, trading_style,
                    timeframe, direction, setup_type, entry_price, stop_loss, take_profit_1,
                    take_profit_2, score, rank_order, regime_at_signal, session_at_signal,
                    source_data_fresh, regime_confidence_at_entry, volatility_at_entry,
                    spread_estimate, compression_ratio_at_entry, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )""",
                (
                    record_id,
                    payload.get("analysis_batch_id"),
                    payload.get("signal_id"),
                    payload.get("signal_timestamp"),
                    payload.get("symbol"),
                    payload.get("trading_style"),
                    payload.get("timeframe"),
                    payload.get("direction"),
                    payload.get("setup_type"),
                    float(payload.get("entry_price") or 0.0),
                    float(payload.get("stop_loss") or 0.0),
                    float(payload.get("take_profit_1") or 0.0),
                    float(payload.get("take_profit_2") or 0.0),
                    float(payload.get("score") or 0.0),
                    int(payload.get("rank") or 0),
                    payload.get("regime_at_signal"),
                    payload.get("session_at_signal"),
                    payload.get("source_data_fresh"),
                    float(payload.get("regime_confidence_at_entry") or 0.0),
                    float(payload.get("volatility_at_entry") or 0.0),
                    float(payload.get("spread_estimate") or 0.0),
                    float(payload.get("compression_ratio_at_entry") or 0.0),
                    payload.get("status", "pending"),
                ),
            )
            conn.commit()
            cursor.close()
            return record_id
        except Exception as e:
            logger.error(f"Failed to save shadow candidate: {e}")
            return "error"
        finally:
            conn.close()

    def get_pending_shadow_candidates(self, *, symbol: str, timeframe: str) -> list:
        if not self.is_enabled():
            return []

        conn = self._get_conn()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT * FROM shadow_candidates
                   WHERE symbol = %s AND timeframe = %s AND status = 'pending'
                   ORDER BY created_at ASC""",
                (symbol, timeframe),
            )
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch pending shadow candidates: {e}")
            return []
        finally:
            conn.close()

    def update_shadow_candidate_simulation(self, record_id: str, resolved: dict):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE shadow_candidates SET
                    status = %s,
                    simulated_entry_bar_index = %s,
                    simulated_exit_bar_index = %s,
                    simulated_outcome = %s,
                    mfe_points = %s,
                    mae_points = %s,
                    tp1_hit = %s,
                    tp2_hit = %s,
                    sl_hit = %s
                   WHERE id = %s""",
                (
                    resolved.get("status", "simulated"),
                    resolved.get("simulated_entry_bar_index"),
                    resolved.get("simulated_exit_bar_index"),
                    resolved.get("simulated_outcome"),
                    resolved.get("mfe_points"),
                    resolved.get("mae_points"),
                    resolved.get("tp1_hit"),
                    resolved.get("tp2_hit"),
                    resolved.get("sl_hit"),
                    record_id,
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to update shadow simulation {record_id}: {e}")
        finally:
            conn.close()

    def bind_shadow_signal(
        self,
        *,
        analysis_batch_id: str | None,
        setup_type: str,
        direction: str,
        signal_id: str,
    ):
        if not analysis_batch_id or not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE shadow_candidates
                   SET signal_id = %s
                   WHERE analysis_batch_id = %s AND setup_type = %s AND direction = %s
                     AND (signal_id IS NULL OR signal_id = '')
                   ORDER BY rank_order ASC
                   LIMIT 1""",
                (signal_id, analysis_batch_id, setup_type, direction),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to bind shadow signal {signal_id}: {e}")
        finally:
            conn.close()

    def update_shadow_candidate_actual(self, *, signal_id: str | None, outcome: dict):
        if not signal_id or not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE shadow_candidates SET
                    actual_entry_price = %s,
                    actual_exit_price = %s,
                    actual_pnl_points = %s,
                    actual_pnl_dollars = %s,
                    actual_outcome = %s,
                    actual_spread = %s,
                    slippage_points = %s
                   WHERE signal_id = %s""",
                (
                    outcome.get("actual_entry_price"),
                    outcome.get("actual_exit_price"),
                    outcome.get("pnl_points"),
                    outcome.get("pnl_dollars"),
                    outcome.get("outcome"),
                    outcome.get("actual_spread"),
                    outcome.get("slippage_points"),
                    signal_id,
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to update shadow actuals for {signal_id}: {e}")
        finally:
            conn.close()

    def save_signal_outcome(self, payload: dict):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO signal_outcomes (
                    id, ticket, signal_id, analysis_batch_id, symbol, direction,
                    setup_type, trading_style, intended_entry_price, intended_stop_loss,
                    intended_take_profit_1, actual_entry_price, actual_exit_price,
                    actual_entry_time, actual_exit_time, regime_at_signal,
                    regime_confidence_at_signal, session_at_signal, volatility_bucket_at_signal,
                    spread_at_signal, data_source_at_signal, compression_ratio_at_entry,
                    efficiency_ratio_at_entry, close_location_at_entry, body_strength_at_entry,
                    pnl_points, pnl_dollars, outcome, actual_spread, slippage_points, fill_quality
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    signal_id = VALUES(signal_id),
                    analysis_batch_id = VALUES(analysis_batch_id),
                    actual_exit_price = VALUES(actual_exit_price),
                    actual_exit_time = VALUES(actual_exit_time),
                    pnl_points = VALUES(pnl_points),
                    pnl_dollars = VALUES(pnl_dollars),
                    outcome = VALUES(outcome),
                    actual_spread = VALUES(actual_spread),
                    slippage_points = VALUES(slippage_points),
                    fill_quality = VALUES(fill_quality)
                """,
                (
                    str(uuid.uuid4()),
                    payload.get("ticket"),
                    payload.get("signal_id"),
                    payload.get("analysis_batch_id"),
                    payload.get("symbol"),
                    payload.get("direction"),
                    payload.get("setup_type"),
                    payload.get("trading_style"),
                    payload.get("intended_entry_price"),
                    payload.get("intended_stop_loss"),
                    payload.get("intended_take_profit_1"),
                    payload.get("actual_entry_price"),
                    payload.get("actual_exit_price"),
                    payload.get("actual_entry_time"),
                    payload.get("actual_exit_time"),
                    payload.get("regime_at_signal"),
                    payload.get("regime_confidence_at_signal"),
                    payload.get("session_at_signal"),
                    payload.get("volatility_bucket_at_signal"),
                    payload.get("spread_at_signal"),
                    payload.get("data_source_at_signal"),
                    payload.get("compression_ratio_at_entry"),
                    payload.get("efficiency_ratio_at_entry"),
                    payload.get("close_location_at_entry"),
                    payload.get("body_strength_at_entry"),
                    payload.get("pnl_points"),
                    payload.get("pnl_dollars"),
                    payload.get("outcome"),
                    payload.get("actual_spread"),
                    payload.get("slippage_points"),
                    payload.get("fill_quality"),
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to save signal outcome: {e}")
        finally:
            conn.close()

    def signal_outcome_exists(self, ticket: int) -> bool:
        if not self.is_enabled():
            return False

        conn = self._get_conn()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM signal_outcomes WHERE ticket = %s LIMIT 1", (ticket,))
            exists = cursor.fetchone() is not None
            cursor.close()
            return exists
        except Exception as e:
            logger.error(f"Failed to check signal outcome for ticket {ticket}: {e}")
            return False
        finally:
            conn.close()

    def get_signal_outcome_calibration_stats(
        self,
        *,
        setup_type: str | None,
        market_regime: str,
        session: str,
        raw_score: float,
    ) -> tuple[float, int, int]:
        if not self.is_enabled():
            return 0.0, 0, 0

        conn = self._get_conn()
        if not conn:
            return 0.0, 0, 0

        low = int(raw_score // 10) * 10
        high = min(low + 10, 100)

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS cnt FROM signal_outcomes")
            total_row = cursor.fetchone() or {}
            total_samples = int(total_row.get("cnt", 0))

            query = """
                SELECT
                    COUNT(*) AS cnt,
                    AVG(CASE WHEN so.outcome = 'win' THEN 1 ELSE 0 END) AS win_rate
                FROM signal_outcomes so
                LEFT JOIN signals s ON s.id = so.signal_id
                WHERE so.regime_at_signal = %s
                  AND so.session_at_signal = %s
                  AND (COALESCE(%s, '') = '' OR so.setup_type = %s)
                  AND COALESCE(s.score, 0) >= %s
                  AND (
                      COALESCE(s.score, 0) < %s
                      OR (%s = 100 AND COALESCE(s.score, 0) <= 100)
                  )
            """
            cursor.execute(query, (market_regime, session, setup_type or "", setup_type, low, high, high))
            row = cursor.fetchone() or {}
            sample_size = int(row.get("cnt", 0))
            win_rate = float(row.get("win_rate") or 0.0)
            cursor.close()
            return win_rate, sample_size, total_samples
        except Exception as e:
            logger.error(f"Failed to fetch calibration stats: {e}")
            return 0.0, 0, 0
        finally:
            conn.close()

    def get_setup_performance_stats(self, *, setup_type: str) -> dict:
        if not self.is_enabled():
            return {"trades": 0, "win_rate": 0.0}

        conn = self._get_conn()
        if not conn:
            return {"trades": 0, "win_rate": 0.0}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT
                       COUNT(*) AS trades,
                       AVG(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS win_rate
                   FROM signal_outcomes
                   WHERE setup_type = %s""",
                (setup_type,),
            )
            row = cursor.fetchone() or {}
            cursor.close()
            return {
                "trades": int(row.get("trades", 0) or 0),
                "win_rate": float(row.get("win_rate", 0.0) or 0.0),
            }
        except Exception as e:
            logger.error(f"Failed to fetch setup performance stats: {e}")
            return {"trades": 0, "win_rate": 0.0}
        finally:
            conn.close()

    def save_optimized_weights(self, payload: dict):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO optimized_weights (
                    id, symbol, trading_style, timeframe, train_start, train_end,
                    validate_start, validate_end, method, objective_score, weights
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    payload.get("symbol"),
                    payload.get("trading_style"),
                    payload.get("timeframe"),
                    payload.get("train_start"),
                    payload.get("train_end"),
                    payload.get("validate_start"),
                    payload.get("validate_end"),
                    payload.get("method"),
                    payload.get("objective_score"),
                    _json_dumps(payload.get("weights") or {}),
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to save optimized weights: {e}")
        finally:
            conn.close()

    def log_kill_switch_event(self, *, symbol: str, action: str, reasons: list[str], context: dict):
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO kill_switch_events (id, symbol, action, reasons, context)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    symbol,
                    action,
                    _json_dumps(reasons),
                    _json_dumps(context),
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to log kill switch event: {e}")
        finally:
            conn.close()

    def save_position_decision(
        self,
        *,
        signal_id: str | None,
        symbol: str,
        signal_direction: str,
        signal_confidence: float,
        had_position: bool,
        position_direction: str | None,
        position_pnl_points: float | None,
        position_pnl_dollars: float | None,
        position_age_minutes: float | None,
        action: str,
        reason: str,
        executed: bool = False,
        execution_result: str | None = None,
    ) -> None:
        if not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO position_decisions (
                    id, signal_id, symbol, signal_direction, signal_confidence,
                    had_position, position_direction, position_pnl_points, position_pnl_dollars,
                    position_age_minutes, action, reason, executed, execution_result
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )""",
                (
                    str(uuid.uuid4()),
                    signal_id,
                    symbol,
                    signal_direction,
                    float(signal_confidence),
                    bool(had_position),
                    position_direction,
                    position_pnl_points,
                    position_pnl_dollars,
                    position_age_minutes,
                    action,
                    reason,
                    bool(executed),
                    execution_result,
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to save position decision: {e}")
        finally:
            conn.close()

    def update_position_decision_execution(
        self,
        *,
        signal_id: str | None,
        executed: bool,
        execution_result: str | None = None,
    ) -> None:
        if not signal_id or not self.is_enabled():
            return

        conn = self._get_conn()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE position_decisions target
                JOIN (
                    SELECT id
                    FROM position_decisions
                    WHERE signal_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                ) latest ON latest.id = target.id
                SET target.executed = %s,
                    target.execution_result = %s
                """,
                (
                    signal_id,
                    bool(executed),
                    execution_result,
                ),
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to update position decision execution: {e}")
        finally:
            conn.close()

    def upsert_order_from_mt5(self, data: dict) -> bool:
        """Upsert an order record from MT5 data (Sync ground truth)."""
        if not self.is_enabled():
            return False

        conn = self._get_conn()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO orders (
                    id, ticket, direction, symbol, entry_price, 
                    stop_loss, take_profit, lot_size, magic_number, comment, status, created_at,
                    closed_at, close_price, profit, commission, swap, close_reason
                ) VALUES (
                    %s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    closed_at = VALUES(closed_at),
                    close_price = VALUES(close_price),
                    profit = VALUES(profit),
                    commission = VALUES(commission),
                    swap = VALUES(swap),
                    close_reason = VALUES(close_reason)
                """,
                (
                    str(uuid.uuid4()),
                    data['ticket'],
                    data['direction'],
                    data['symbol'],
                    data['entry_price'],
                    data.get('stop_loss', 0.0),
                    data.get('take_profit', 0.0),
                    data['lot_size'],
                    data['magic_number'],
                    data['comment'],
                    data['status'],
                    data['created_at'],
                    data.get('closed_at'),
                    data.get('close_price'),
                    data.get('profit'),
                    data.get('commission'),
                    data.get('swap'),
                    data.get('close_reason'),
                ),
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to upsert MT5 order: {e}")
            return False
        finally:
            conn.close()

    def get_last_sync_ticket(self) -> int:
        """Fetch the largest ticket number we have in our database."""
        if not self.is_enabled():
            return 0
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ticket) FROM orders")
            res = cursor.fetchone()
            cursor.close()
            return res[0] if res and res[0] else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def get_settings(self, account_id: str = "default") -> dict:
        """Fetch configuration overrides for a specific account."""
        if not self.is_enabled():
            return {}
        conn = self._get_conn()
        if not conn:
            return {}
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT config_json FROM settings WHERE account_id = %s", (account_id,))
            row = cursor.fetchone()
            cursor.close()
            if row and row["config_json"]:
                if isinstance(row["config_json"], str):
                    return json.loads(row["config_json"])
                return row["config_json"]
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch settings for {account_id}: {e}")
            return {}
        finally:
            conn.close()

    def update_settings(self, account_id: str, data: dict) -> bool:
        """Update configuration overrides for a specific account."""
        if not self.is_enabled():
            return False
            
        # Merge with existing settings
        current = self.get_settings(account_id)
        current.update(data)
        
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO settings (account_id, config_json)
                   VALUES (%s, %s)
                   ON DUPLICATE KEY UPDATE 
                     config_json = VALUES(config_json),
                     updated_at = NOW()
                """,
                (account_id, json.dumps(current))
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Failed to update settings for {account_id}: {e}")
            return False
        finally:
            conn.close()

# Global instance
db = DatabaseService()
