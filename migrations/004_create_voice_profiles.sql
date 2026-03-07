-- Migration: Create voice_profiles table
-- Description: Stores per-user voice biometric embeddings for speaker identification
-- Version: 004
-- Date: 2026-03-06

-- Enable pgvector extension if available (needed for vector similarity search)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Create the voice_profiles table
CREATE TABLE IF NOT EXISTS voice_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Voice embedding as a 512-dimensional float array
    -- When pgvector is available, use: voice_embedding vector(512)
    voice_embedding FLOAT[] NOT NULL,
    samples_count INTEGER DEFAULT 1,
    confidence_score FLOAT DEFAULT 0.0,  -- average confidence across samples
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index on user_id for fast per-user lookup
CREATE INDEX IF NOT EXISTS idx_voice_profiles_user_id ON voice_profiles(user_id);

-- Index on last_updated for staleness checks
CREATE INDEX IF NOT EXISTS idx_voice_profiles_updated ON voice_profiles(last_updated DESC);

-- Add FK from users to voice_profiles (backfill after both tables exist).
-- Dependency note: this closes the circular reference between users and voice_profiles.
--   users.voice_profile_id → voice_profiles.id   (added below)
--   voice_profiles.user_id → users.id             (added in the CREATE TABLE above)
-- Run migration 003 (users table) first, then this migration 004.
ALTER TABLE users
    ADD CONSTRAINT IF NOT EXISTS fk_users_voice_profile
    FOREIGN KEY (voice_profile_id) REFERENCES voice_profiles(id) ON DELETE SET NULL;

-- Trigger to auto-update last_updated
CREATE OR REPLACE FUNCTION update_voice_profiles_last_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_voice_profiles_last_updated
    BEFORE UPDATE ON voice_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_voice_profiles_last_updated();

-- Comments
COMMENT ON TABLE voice_profiles IS 'Per-user voice biometric embeddings for speaker identification';
COMMENT ON COLUMN voice_profiles.id IS 'Unique voice profile identifier';
COMMENT ON COLUMN voice_profiles.user_id IS 'FK to users.id – owner of this voice profile';
COMMENT ON COLUMN voice_profiles.voice_embedding IS '512-dimensional normalised float vector of voice features';
COMMENT ON COLUMN voice_profiles.samples_count IS 'Number of audio samples used to build this profile';
COMMENT ON COLUMN voice_profiles.confidence_score IS 'Average similarity score across matched samples (0.0–1.0)';

-- Enable Row Level Security
ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can only access their own voice profile
CREATE POLICY "voice_profiles_select_own" ON voice_profiles
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "voice_profiles_insert_own" ON voice_profiles
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "voice_profiles_update_own" ON voice_profiles
    FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "voice_profiles_delete_own" ON voice_profiles
    FOR DELETE
    USING (user_id = auth.uid());
