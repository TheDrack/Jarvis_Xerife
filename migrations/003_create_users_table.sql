-- Migration: Create users table
-- Description: User identity table linked to Supabase auth.users
-- Version: 003
-- Date: 2026-03-06

-- Create the users table
-- Note: id references auth.users in Supabase (UUID primary key).
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    hashed_password TEXT,
    disabled BOOLEAN DEFAULT FALSE,
    voice_profile_id UUID,  -- FK to voice_profiles (added after 004 migration)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index on email for fast lookup during authentication
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Index on voice_profile_id for voice-based user resolution
CREATE INDEX IF NOT EXISTS idx_users_voice_profile ON users(voice_profile_id);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_users_updated_at();

-- Comments
COMMENT ON TABLE users IS 'JARVIS user accounts linked to Supabase auth';
COMMENT ON COLUMN users.id IS 'UUID matching auth.users.id in Supabase';
COMMENT ON COLUMN users.email IS 'Unique email address used for login';
COMMENT ON COLUMN users.full_name IS 'Display name of the user';
COMMENT ON COLUMN users.hashed_password IS 'bcrypt-hashed password for local fallback auth';
COMMENT ON COLUMN users.disabled IS 'Whether the account is disabled';
COMMENT ON COLUMN users.voice_profile_id IS 'FK to voice_profiles (biometric identity)';

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can only see their own row
CREATE POLICY "users_select_own" ON users
    FOR SELECT
    USING (id = auth.uid());

-- RLS policy: users can only update their own row
CREATE POLICY "users_update_own" ON users
    FOR UPDATE
    USING (id = auth.uid());

-- RLS policy: service role can insert new users
CREATE POLICY "users_insert_service" ON users
    FOR INSERT
    WITH CHECK (TRUE);
