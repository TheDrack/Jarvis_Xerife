-- Migration: Add user_id and capability_id to evolution_rewards
-- Description: Extends rewards table to support per-user tracking and capability linkage
-- Version: 005
-- Date: 2026-03-06

-- Add user_id column (nullable for backward compat with existing rows)
ALTER TABLE evolution_rewards
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;

-- Add capability_id column for capability-specific aggregation
ALTER TABLE evolution_rewards
    ADD COLUMN IF NOT EXISTS capability_id VARCHAR(100);

-- Index for per-user reward queries
CREATE INDEX IF NOT EXISTS idx_rewards_user_id ON evolution_rewards(user_id);

-- Composite index for capability-time aggregation (as requested in TAREFA 3)
CREATE INDEX IF NOT EXISTS idx_rewards_capability_timestamp
    ON evolution_rewards(capability_id, created_at DESC);

-- Comments
COMMENT ON COLUMN evolution_rewards.user_id IS 'FK to users.id – which user triggered this reward';
COMMENT ON COLUMN evolution_rewards.capability_id IS 'Capability identifier linked to this reward event';

-- RLS policy for user-scoped reward reads
CREATE POLICY "rewards_select_own" ON evolution_rewards
    FOR SELECT
    USING (user_id IS NULL OR user_id = auth.uid());

CREATE POLICY "rewards_insert_service" ON evolution_rewards
    FOR INSERT
    WITH CHECK (TRUE);
