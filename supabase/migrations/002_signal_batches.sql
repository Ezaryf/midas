-- Ranked signal batch metadata for the smarter market-state engine.

ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    ADD COLUMN IF NOT EXISTS analysis_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS setup_type TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS market_regime TEXT NOT NULL DEFAULT 'neutral',
    ADD COLUMN IF NOT EXISTS score NUMERIC(5, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rank INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS entry_window_low NUMERIC(12, 4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS entry_window_high NUMERIC(12, 4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS context_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS context JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_signals_analysis_batch_rank
    ON signals(analysis_batch_id, rank);
