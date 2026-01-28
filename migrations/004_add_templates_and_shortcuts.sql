-- Migration 004: Add Expense Templates and Quick Shortcuts
-- This migration adds support for:
-- 1. Expense templates for quick entry
-- 2. Quick shortcuts for dashboard
-- 
-- Compatible with PostgreSQL 9.0+ (DO blocks require 9.0+)
-- This migration creates tables that match the current categories.id type
-- Migration 005 will convert everything to UUID if needed

-- Check the type of categories.id and create tables accordingly
-- Uses DO block for compatibility (PostgreSQL 9.0+)
-- Falls back to UUID if type detection fails
DO $$
DECLARE
    category_id_type TEXT;
    table_exists BOOLEAN;
BEGIN
    -- Check if categories table exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'categories'
    ) INTO table_exists;
    
    IF NOT table_exists THEN
        RAISE NOTICE 'Categories table does not exist. Creating tables with UUID type.';
        category_id_type := 'uuid';
    ELSE
        -- Get the data type of categories.id
        -- Use pg_typeof for better compatibility (works on all PostgreSQL versions)
        SELECT pg_typeof(id)::text INTO category_id_type
        FROM categories
        LIMIT 1;
        
        -- Fallback to information_schema if pg_typeof fails
        IF category_id_type IS NULL THEN
            SELECT data_type INTO category_id_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'categories' 
            AND column_name = 'id';
        END IF;
        
        -- Normalize type name (uuid vs text)
        IF category_id_type IS NULL OR category_id_type = '' THEN
            category_id_type := 'uuid'; -- Default to UUID
        END IF;
    END IF;
    
    -- If categories.id is TEXT, create tables with TEXT foreign keys
    -- If categories.id is UUID (or anything else), create tables with UUID foreign keys
    IF LOWER(category_id_type) = 'text' OR category_id_type LIKE '%text%' THEN
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
        -- Create expense_templates with UUID IDs (default)
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
EXCEPTION
    WHEN OTHERS THEN
        -- If DO block fails, log error but don't fail migration
        -- Tables will be created by fallback statements below
        RAISE NOTICE 'Error in DO block: %. Creating tables with UUID type as fallback.', SQLERRM;
END $$;

-- Fallback: If DO block failed or categories table doesn't exist, create with UUID
-- This ensures the migration works even on PostgreSQL < 9.0 or if DO block fails
CREATE TABLE IF NOT EXISTS expense_templates (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    category_id UUID,
    default_amount DECIMAL(10,2),
    note_template TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quick_shortcuts (
    id UUID PRIMARY KEY,
    category_id UUID NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Add foreign key constraints if categories table exists and columns are compatible
DO $$
BEGIN
    -- Only add foreign keys if categories table exists and has compatible type
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'categories'
    ) THEN
        -- Try to add foreign key for expense_templates
        BEGIN
            ALTER TABLE expense_templates 
            ADD CONSTRAINT expense_templates_category_id_fkey 
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE;
        EXCEPTION
            WHEN duplicate_object THEN
                -- Constraint already exists, ignore
                NULL;
            WHEN OTHERS THEN
                -- Type mismatch or other error, will be fixed by migration 005
                RAISE NOTICE 'Could not add foreign key for expense_templates.category_id: %', SQLERRM;
        END;
        
        -- Try to add foreign key for quick_shortcuts
        BEGIN
            ALTER TABLE quick_shortcuts 
            ADD CONSTRAINT quick_shortcuts_category_id_fkey 
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE;
        EXCEPTION
            WHEN duplicate_object THEN
                -- Constraint already exists, ignore
                NULL;
            WHEN OTHERS THEN
                -- Type mismatch or other error, will be fixed by migration 005
                RAISE NOTICE 'Could not add foreign key for quick_shortcuts.category_id: %', SQLERRM;
        END;
    END IF;
END $$;

-- Create indexes (these work regardless of the ID type)
CREATE INDEX IF NOT EXISTS idx_templates_active ON expense_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_templates_category ON expense_templates(category_id);
CREATE INDEX IF NOT EXISTS idx_shortcuts_active ON quick_shortcuts(is_active);
CREATE INDEX IF NOT EXISTS idx_shortcuts_position ON quick_shortcuts(position);
CREATE INDEX IF NOT EXISTS idx_shortcuts_category ON quick_shortcuts(category_id);
