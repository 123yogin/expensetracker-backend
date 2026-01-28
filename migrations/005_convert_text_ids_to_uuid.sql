-- Migration 005: Convert all TEXT ID columns to UUID
-- This migration converts the database schema to use UUID consistently
-- Handles the case where the database was created with TEXT IDs
-- 
-- Compatible with PostgreSQL 9.0+ (DO blocks require 9.0+)
-- Uses safe type conversion with USING clause for compatibility
-- Includes error handling for invalid UUID values

-- Helper function to safely convert a column from TEXT to UUID
-- Returns true if conversion succeeded, false otherwise
CREATE OR REPLACE FUNCTION safe_convert_text_to_uuid(
    table_name_param TEXT,
    column_name_param TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    current_type TEXT;
    invalid_count INTEGER;
    sql_stmt TEXT;
BEGIN
    -- Check if column exists and is TEXT type
    SELECT data_type INTO current_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND table_name = table_name_param
    AND column_name = column_name_param;
    
    IF current_type IS NULL THEN
        RETURN FALSE; -- Column doesn't exist
    END IF;
    
    IF current_type != 'text' THEN
        RETURN TRUE; -- Already correct type or not TEXT
    END IF;
    
    -- Check for invalid UUID values (basic regex check)
    sql_stmt := format('SELECT COUNT(*) FROM %I WHERE %I !~ ''^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$''', 
                       table_name_param, column_name_param);
    EXECUTE sql_stmt INTO invalid_count;
    
    IF invalid_count > 0 THEN
        RAISE NOTICE 'Cannot convert %.% to UUID: % invalid UUID values found', 
                     table_name_param, column_name_param, invalid_count;
        RETURN FALSE;
    END IF;
    
    -- Perform the conversion
    sql_stmt := format('ALTER TABLE %I ALTER COLUMN %I TYPE UUID USING %I::uuid', 
                       table_name_param, column_name_param, column_name_param);
    EXECUTE sql_stmt;
    
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error converting %.% to UUID: %', table_name_param, column_name_param, SQLERRM;
        RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Step 1: Drop foreign key constraints that reference categories.id
-- (We'll recreate them after converting the types)

-- Drop foreign keys from expenses
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'expenses_category_id_fkey' 
        AND table_name = 'expenses'
    ) THEN
        ALTER TABLE expenses DROP CONSTRAINT expenses_category_id_fkey;
    END IF;
END $$;

-- Drop foreign keys from budgets
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'budgets_category_id_fkey' 
        AND table_name = 'budgets'
    ) THEN
        ALTER TABLE budgets DROP CONSTRAINT budgets_category_id_fkey;
    END IF;
END $$;

-- Drop foreign keys from recurring_expenses
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'recurring_expenses_category_id_fkey' 
        AND table_name = 'recurring_expenses'
    ) THEN
        ALTER TABLE recurring_expenses DROP CONSTRAINT recurring_expenses_category_id_fkey;
    END IF;
END $$;

-- Drop foreign keys from categorization_patterns (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'categorization_patterns_category_id_fkey' 
        AND table_name = 'categorization_patterns'
    ) THEN
        ALTER TABLE categorization_patterns DROP CONSTRAINT categorization_patterns_category_id_fkey;
    END IF;
END $$;

-- Drop foreign keys from expense_templates (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'expense_templates_category_id_fkey' 
        AND table_name = 'expense_templates'
    ) THEN
        ALTER TABLE expense_templates DROP CONSTRAINT expense_templates_category_id_fkey;
    END IF;
END $$;

-- Drop foreign keys from quick_shortcuts (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'quick_shortcuts_category_id_fkey' 
        AND table_name = 'quick_shortcuts'
    ) THEN
        ALTER TABLE quick_shortcuts DROP CONSTRAINT quick_shortcuts_category_id_fkey;
    END IF;
END $$;

-- Step 2: Convert all ID columns from TEXT to UUID using safe conversion function
-- Convert categories.id first (it's referenced by foreign keys)
DO $$
BEGIN
    PERFORM safe_convert_text_to_uuid('categories', 'id');
END $$;

-- Step 3: Convert all other id columns from TEXT to UUID (if needed)
-- Convert all tables using the safe conversion function
DO $$
BEGIN
    -- Convert expenses
    PERFORM safe_convert_text_to_uuid('expenses', 'id');
    PERFORM safe_convert_text_to_uuid('expenses', 'category_id');
    
    -- Convert income
    PERFORM safe_convert_text_to_uuid('income', 'id');
    
    -- Convert budgets
    PERFORM safe_convert_text_to_uuid('budgets', 'id');
    PERFORM safe_convert_text_to_uuid('budgets', 'category_id');
    
    -- Convert recurring_expenses
    PERFORM safe_convert_text_to_uuid('recurring_expenses', 'id');
    PERFORM safe_convert_text_to_uuid('recurring_expenses', 'category_id');
    
    -- Convert categorization_patterns (if exists)
    PERFORM safe_convert_text_to_uuid('categorization_patterns', 'category_id');
    
    -- Convert offline_sync_queue (if exists)
    PERFORM safe_convert_text_to_uuid('offline_sync_queue', 'record_id');
    
    -- Convert expense_templates (if exists)
    PERFORM safe_convert_text_to_uuid('expense_templates', 'id');
    PERFORM safe_convert_text_to_uuid('expense_templates', 'category_id');
    
    -- Convert quick_shortcuts (if exists)
    PERFORM safe_convert_text_to_uuid('quick_shortcuts', 'id');
    PERFORM safe_convert_text_to_uuid('quick_shortcuts', 'category_id');
END $$;

-- Step 4: Recreate foreign key constraints with UUID types
-- Use DO blocks with error handling for maximum compatibility

-- Recreate expenses.category_id foreign key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'expenses_category_id_fkey' 
        AND table_name = 'expenses'
    ) THEN
        ALTER TABLE expenses 
        ADD CONSTRAINT expenses_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE RESTRICT;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create expenses_category_id_fkey: %', SQLERRM;
END $$;

-- Recreate budgets.category_id foreign key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'budgets_category_id_fkey' 
        AND table_name = 'budgets'
    ) THEN
        ALTER TABLE budgets 
        ADD CONSTRAINT budgets_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE CASCADE;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create budgets_category_id_fkey: %', SQLERRM;
END $$;

-- Recreate recurring_expenses.category_id foreign key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'recurring_expenses_category_id_fkey' 
        AND table_name = 'recurring_expenses'
    ) THEN
        ALTER TABLE recurring_expenses 
        ADD CONSTRAINT recurring_expenses_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE SET NULL;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create recurring_expenses_category_id_fkey: %', SQLERRM;
END $$;

-- Recreate categorization_patterns.category_id foreign key (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'categorization_patterns') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'categorization_patterns_category_id_fkey' 
            AND table_name = 'categorization_patterns'
        ) THEN
            ALTER TABLE categorization_patterns 
            ADD CONSTRAINT categorization_patterns_category_id_fkey 
            FOREIGN KEY (category_id) REFERENCES categories(id) 
            ON DELETE CASCADE;
        END IF;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create categorization_patterns_category_id_fkey: %', SQLERRM;
END $$;

-- Drop and recreate expense_templates foreign keys (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'expense_templates') THEN
        -- Drop existing constraint if it exists
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'expense_templates_category_id_fkey' 
            AND table_name = 'expense_templates'
        ) THEN
            ALTER TABLE expense_templates DROP CONSTRAINT expense_templates_category_id_fkey;
        END IF;
        
        -- Recreate with UUID
        ALTER TABLE expense_templates 
        ADD CONSTRAINT expense_templates_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE CASCADE;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create expense_templates_category_id_fkey: %', SQLERRM;
END $$;

-- Drop and recreate quick_shortcuts foreign keys (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'quick_shortcuts') THEN
        -- Drop existing constraint if it exists
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'quick_shortcuts_category_id_fkey' 
            AND table_name = 'quick_shortcuts'
        ) THEN
            ALTER TABLE quick_shortcuts DROP CONSTRAINT quick_shortcuts_category_id_fkey;
        END IF;
        
        -- Recreate with UUID
        ALTER TABLE quick_shortcuts 
        ADD CONSTRAINT quick_shortcuts_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE CASCADE;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not create quick_shortcuts_category_id_fkey: %', SQLERRM;
END $$;

-- Clean up: Drop the helper function (no longer needed after migration)
DROP FUNCTION IF EXISTS safe_convert_text_to_uuid(TEXT, TEXT);
