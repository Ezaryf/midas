-- Trading State Persistence Table
-- Stores daily counters and trading configuration so they survive backend restarts.
-- Uses the "singleton" pattern: one row, upserted on every state change.

CREATE TABLE IF NOT EXISTS trading_state (
    id TEXT PRIMARY KEY DEFAULT 'singleton',
    daily_trades INTEGER NOT NULL DEFAULT 0,
    daily_pnl DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    last_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
    trading_style TEXT NOT NULL DEFAULT 'Scalper',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert the initial row
INSERT INTO trading_state (id) VALUES ('singleton')
ON CONFLICT (id) DO NOTHING;

-- Enable RLS but allow service role full access
ALTER TABLE trading_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access" ON trading_state
    FOR ALL
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE trading_state IS 'Persistent trading state — survives backend restarts. Single-row table (id=singleton).';
