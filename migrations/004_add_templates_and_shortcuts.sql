-- Migration 004: Add Expense Templates and Quick Shortcuts
-- This migration adds support for:
-- 1. Expense templates for quick entry
-- 2. Quick shortcuts for dashboard
-- 
-- Note: This migration creates tables that match the current categories.id type
-- Migration 005 will convert everything to UUID if needed

-- Check the type of categories.id and create tables accordingly
DO $$
DECLARE
    category_id_type TEXT;
BEGIN
    -- Get the data type of categories.id
    SELECT data_type INTO category_id_type
    FROM information_schema.columns
    WHERE table_name = 'categories' AND column_name = 'id';
    
    -- If categories.id is TEXT, create tables with TEXT foreign keys
    -- If categories.id is UUID, create tables with UUID foreign keys
    IF category_id_type = 'text' THEN
        -- Create expense_templates with TEXT IDs
        EXECUTE '
        CREATE TABLE IF NOT EXISTS expense_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category_id TEXT REFERENCES categories(id) ON DELETE CASCADE,
            default_amount DECIMAL(10,2),
            note_template TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )';
        
        EXECUTE '
        CREATE TABLE IF NOT EXISTS quick_shortcuts (
            id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )';
    ELSE
        -- Create expense_templates with UUID IDs
        EXECUTE '
        CREATE TABLE IF NOT EXISTS expense_templates (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            category_id UUID REFERENCES categories(id) ON DELETE CASCADE,
            default_amount DECIMAL(10,2),
            note_template TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )';
        
        EXECUTE '
        CREATE TABLE IF NOT EXISTS quick_shortcuts (
            id UUID PRIMARY KEY,
            category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )';
    END IF;
END $$;

-- Create indexes (these work regardless of the ID type)
CREATE INDEX IF NOT EXISTS idx_templates_active ON expense_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_templates_category ON expense_templates(category_id);
CREATE INDEX IF NOT EXISTS idx_shortcuts_active ON quick_shortcuts(is_active);
CREATE INDEX IF NOT EXISTS idx_shortcuts_position ON quick_shortcuts(position);
CREATE INDEX IF NOT EXISTS idx_shortcuts_category ON quick_shortcuts(category_id);
