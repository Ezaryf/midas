-- Midas Trading System - Initial Database Schema
-- Run this migration in your Supabase project

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Signals table: AI-generated trade signals
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL', 'HOLD')),
    entry_price NUMERIC(10, 2) NOT NULL,
    stop_loss NUMERIC(10, 2) NOT NULL,
    take_profit_1 NUMERIC(10, 2) NOT NULL,
    take_profit_2 NUMERIC(10, 2) NOT NULL,
    confidence NUMERIC(5, 2) NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
    reasoning TEXT NOT NULL,
    trading_style TEXT NOT NULL CHECK (trading_style IN ('Scalper', 'Intraday', 'Swing')),
    
    -- Technical context
    indicators JSONB,
    calendar_events JSONB,
    current_price NUMERIC(10, 2),
    trend TEXT,
    
    -- Metadata
    ai_provider TEXT,
    ai_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orders table: Actual MT5 orders executed
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    
    -- MT5 order details
    ticket BIGINT UNIQUE NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    
    -- Prices
    entry_price NUMERIC(10, 2) NOT NULL,
    stop_loss NUMERIC(10, 2) NOT NULL,
    take_profit NUMERIC(10, 2) NOT NULL,
    close_price NUMERIC(10, 2),
    
    -- Position sizing
    lot_size NUMERIC(10, 2) NOT NULL,
    
    -- Timestamps
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    
    -- P&L
    profit NUMERIC(10, 2),
    commission NUMERIC(10, 2) DEFAULT 0,
    swap NUMERIC(10, 2) DEFAULT 0,
    net_profit NUMERIC(10, 2),
    
    -- Status
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED')),
    close_reason TEXT CHECK (close_reason IN ('TP1', 'TP2', 'SL', 'MANUAL', 'TIME_EXIT', 'RISK_LIMIT')),
    
    -- Metadata
    magic_number BIGINT,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Account snapshots: Track equity curve
CREATE TABLE account_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Account metrics
    balance NUMERIC(12, 2) NOT NULL,
    equity NUMERIC(12, 2) NOT NULL,
    margin NUMERIC(12, 2) NOT NULL,
    free_margin NUMERIC(12, 2) NOT NULL,
    margin_level NUMERIC(10, 2),
    
    -- Position counts
    open_positions INT NOT NULL DEFAULT 0,
    pending_orders INT NOT NULL DEFAULT 0,
    
    -- Daily metrics
    daily_profit NUMERIC(10, 2),
    daily_trades INT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance metrics: Cached analytics
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period TEXT NOT NULL CHECK (period IN ('DAILY', 'WEEKLY', 'MONTHLY', 'ALL_TIME')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    
    -- Trade statistics
    total_trades INT NOT NULL DEFAULT 0,
    winning_trades INT NOT NULL DEFAULT 0,
    losing_trades INT NOT NULL DEFAULT 0,
    break_even_trades INT NOT NULL DEFAULT 0,
    
    -- Win rate
    win_rate NUMERIC(5, 2),
    
    -- P&L
    total_profit NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_loss NUMERIC(12, 2) NOT NULL DEFAULT 0,
    net_profit NUMERIC(12, 2) NOT NULL DEFAULT 0,
    
    -- Risk metrics
    profit_factor NUMERIC(10, 2),
    max_drawdown NUMERIC(10, 2),
    max_drawdown_percent NUMERIC(5, 2),
    sharpe_ratio NUMERIC(10, 4),
    sortino_ratio NUMERIC(10, 4),
    
    -- Trade metrics
    avg_win NUMERIC(10, 2),
    avg_loss NUMERIC(10, 2),
    largest_win NUMERIC(10, 2),
    largest_loss NUMERIC(10, 2),
    avg_trade_duration INTERVAL,
    
    -- Metadata
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(period, period_start)
);

-- Risk events: Track risk management actions
CREATE TABLE risk_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'DAILY_LOSS_LIMIT',
        'MAX_POSITIONS',
        'INSUFFICIENT_MARGIN',
        'CORRELATION_BLOCK',
        'DRAWDOWN_LIMIT',
        'NEWS_BLACKOUT'
    )),
    description TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX idx_signals_direction ON signals(direction);
CREATE INDEX idx_orders_signal_id ON orders(signal_id);
CREATE INDEX idx_orders_ticket ON orders(ticket);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_opened_at ON orders(opened_at DESC);
CREATE INDEX idx_orders_closed_at ON orders(closed_at DESC) WHERE closed_at IS NOT NULL;
CREATE INDEX idx_account_snapshots_timestamp ON account_snapshots(timestamp DESC);
CREATE INDEX idx_performance_metrics_period ON performance_metrics(period, period_start DESC);
CREATE INDEX idx_risk_events_timestamp ON risk_events(timestamp DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for orders table
CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to calculate net profit
CREATE OR REPLACE FUNCTION calculate_net_profit()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.profit IS NOT NULL THEN
        NEW.net_profit = NEW.profit + COALESCE(NEW.commission, 0) + COALESCE(NEW.swap, 0);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-calculate net profit
CREATE TRIGGER calculate_order_net_profit
    BEFORE INSERT OR UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION calculate_net_profit();

-- Row Level Security (RLS) - Enable later with auth
-- ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE account_snapshots ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE performance_metrics ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE risk_events ENABLE ROW LEVEL SECURITY;

-- Views for common queries

-- Active orders view
CREATE VIEW active_orders AS
SELECT 
    o.*,
    s.confidence,
    s.reasoning,
    s.ai_provider
FROM orders o
LEFT JOIN signals s ON o.signal_id = s.id
WHERE o.status = 'OPEN'
ORDER BY o.opened_at DESC;

-- Daily performance view
CREATE VIEW daily_performance AS
SELECT 
    DATE(closed_at) as trade_date,
    COUNT(*) as total_trades,
    SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN net_profit < 0 THEN 1 ELSE 0 END) as losing_trades,
    ROUND(SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)::NUMERIC * 100, 2) as win_rate,
    ROUND(SUM(net_profit), 2) as daily_profit
FROM orders
WHERE status = 'CLOSED' AND closed_at IS NOT NULL
GROUP BY DATE(closed_at)
ORDER BY trade_date DESC;

-- Signal performance view (how well AI signals perform)
CREATE VIEW signal_performance AS
SELECT 
    s.id,
    s.timestamp,
    s.direction,
    s.confidence,
    s.ai_provider,
    o.ticket,
    o.net_profit,
    o.close_reason,
    CASE 
        WHEN o.net_profit > 0 THEN 'WIN'
        WHEN o.net_profit < 0 THEN 'LOSS'
        ELSE 'BREAK_EVEN'
    END as outcome
FROM signals s
LEFT JOIN orders o ON s.id = o.signal_id
WHERE s.direction IN ('BUY', 'SELL')
ORDER BY s.timestamp DESC;

COMMENT ON TABLE signals IS 'AI-generated trade signals with full context';
COMMENT ON TABLE orders IS 'Actual MT5 orders executed and their outcomes';
COMMENT ON TABLE account_snapshots IS 'Periodic snapshots of account state for equity curve';
COMMENT ON TABLE performance_metrics IS 'Cached performance analytics by time period';
COMMENT ON TABLE risk_events IS 'Risk management events and actions taken';
