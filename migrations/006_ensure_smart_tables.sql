-- Migration 006: Ensure Smart Features Tables Exist
-- This is a recovery migration to fix missing tables if migration 003 failed or was skipped

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Smart categorization learning table
CREATE TABLE IF NOT EXISTS categorization_patterns (
    id UUID PRIMARY KEY,
    note_keywords TEXT NOT NULL,
    category_id UUID NOT NULL, -- references categories(id) handled in foreign key constraint if needed, but keeping simple for recovery
    confidence_score DECIMAL(3,2) DEFAULT 0.50, -- Learning confidence 0.00 to 1.00
    usage_count INTEGER DEFAULT 1, -- How many times this pattern was used
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Attempt to add foreign key if it doesn't exist (complex to do safely in pure SQL without PL/PGSQL, so skipping explicit constraint check for recovery to avoid errors. 
-- Ideally we assume categories table exists from migration 001)

CREATE INDEX IF NOT EXISTS idx_categorization_keywords ON categorization_patterns USING gin(to_tsvector('english', note_keywords));
CREATE INDEX IF NOT EXISTS idx_categorization_category ON categorization_patterns(category_id);
CREATE INDEX IF NOT EXISTS idx_categorization_confidence ON categorization_patterns(confidence_score DESC);

-- Export/backup tracking table
CREATE TABLE IF NOT EXISTS export_logs (
    id UUID PRIMARY KEY,
    export_type TEXT NOT NULL, -- 'csv', 'pdf', 'json'
    date_range_start DATE,
    date_range_end DATE,
    total_records INTEGER NOT NULL,
    file_size INTEGER, -- in bytes
    export_path TEXT, -- where file was saved/downloaded
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_export_logs_date ON export_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_export_logs_type ON export_logs(export_type);

-- Offline sync support table (for PWA functionality)
CREATE TABLE IF NOT EXISTS offline_sync_queue (
    id UUID PRIMARY KEY,
    operation_type TEXT NOT NULL, -- 'create', 'update', 'delete'
    table_name TEXT NOT NULL, -- 'expenses', 'categories', etc.
    record_id UUID,
    data_payload JSONB, -- The actual data to sync
    sync_status TEXT DEFAULT 'pending', -- 'pending', 'synced', 'failed'
    retry_count INTEGER DEFAULT 0,
    last_retry TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_offline_sync_status ON offline_sync_queue(sync_status);
CREATE INDEX IF NOT EXISTS idx_offline_sync_created ON offline_sync_queue(created_at);

-- User preferences for smart features
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY,
    preference_key TEXT UNIQUE NOT NULL,
    preference_value JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Insert default preferences utilizing reusable logic (idempotent)
INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'smart_categorization_enabled', 'true'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'smart_categorization_enabled');

INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'voice_input_enabled', 'true'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'voice_input_enabled');

INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'auto_backup_enabled', 'false'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'auto_backup_enabled');

INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'offline_mode_enabled', 'true'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'offline_mode_enabled');

INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'receipt_photo_quality', '"medium"'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'receipt_photo_quality');

INSERT INTO user_preferences (id, preference_key, preference_value)
SELECT gen_random_uuid(), 'export_default_format', '"csv"'
WHERE NOT EXISTS (SELECT 1 FROM user_preferences WHERE preference_key = 'export_default_format');
