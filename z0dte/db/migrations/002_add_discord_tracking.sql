-- Migration: Add Discord Notification Tracking
-- Date: 2026-04-09
-- Purpose: Track which trade signals have been sent to Discord to avoid duplicates

-- Table to track all Discord notifications sent
CREATE TABLE IF NOT EXISTS calendar_signal_notifications (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(36) NOT NULL,
    notification_type VARCHAR(20) NOT NULL,  -- 'entry' or 'exit'
    discord_sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    symbol VARCHAR(10) NOT NULL,
    opportunity_score NUMERIC(6,4),
    confidence NUMERIC(6,4),
    message_preview TEXT,
    
    UNIQUE (trade_id, notification_type)
);

CREATE INDEX IF NOT EXISTS idx_notifications_trade 
    ON calendar_signal_notifications(trade_id);

CREATE INDEX IF NOT EXISTS idx_notifications_sent_at 
    ON calendar_signal_notifications(discord_sent_at DESC);

-- Add discord tracking columns to trades table (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'calendar_spread_trades') THEN
        ALTER TABLE calendar_spread_trades 
            ADD COLUMN IF NOT EXISTS discord_entry_sent_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS discord_exit_sent_at TIMESTAMP;
    END IF;
END $$;
