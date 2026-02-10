-- Migration: Create jarvis_capabilities table
-- Description: Stores JARVIS self-awareness capabilities and their status
-- Version: 001
-- Date: 2026-02-10

-- Create the jarvis_capabilities table
CREATE TABLE IF NOT EXISTS jarvis_capabilities (
    id INTEGER PRIMARY KEY,
    chapter VARCHAR(100) NOT NULL,
    capability_name VARCHAR(500) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'nonexistent',
    requirements TEXT DEFAULT '[]',  -- JSON array of requirement strings
    implementation_logic TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on chapter for faster chapter-based queries
CREATE INDEX IF NOT EXISTS idx_capabilities_chapter ON jarvis_capabilities(chapter);

-- Create index on status for filtering by capability status
CREATE INDEX IF NOT EXISTS idx_capabilities_status ON jarvis_capabilities(status);

-- Add constraint to ensure status is one of valid values
ALTER TABLE jarvis_capabilities 
ADD CONSTRAINT check_status 
CHECK (status IN ('nonexistent', 'partial', 'complete'));

-- Create trigger to update updated_at timestamp on row updates (PostgreSQL)
-- Note: This is PostgreSQL syntax. For SQLite, you would use different syntax.
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_jarvis_capabilities_updated_at 
    BEFORE UPDATE ON jarvis_capabilities 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE jarvis_capabilities IS 'JARVIS self-awareness capability inventory tracking status and requirements';
COMMENT ON COLUMN jarvis_capabilities.id IS 'Unique capability identifier from JARVIS_OBJECTIVES_MAP';
COMMENT ON COLUMN jarvis_capabilities.chapter IS 'Chapter this capability belongs to';
COMMENT ON COLUMN jarvis_capabilities.capability_name IS 'Human-readable name of the capability';
COMMENT ON COLUMN jarvis_capabilities.status IS 'Current implementation status: nonexistent, partial, or complete';
COMMENT ON COLUMN jarvis_capabilities.requirements IS 'JSON array of technical requirements needed for this capability';
COMMENT ON COLUMN jarvis_capabilities.implementation_logic IS 'Description of how this capability is/should be implemented';
