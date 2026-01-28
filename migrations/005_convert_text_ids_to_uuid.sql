-- Migration 005: Convert all TEXT ID columns to UUID
-- This migration converts the database schema to use UUID consistently
-- Handles the case where the database was created with TEXT IDs

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

-- Step 2: Convert categories.id from TEXT to UUID (if needed)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'categories' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        -- Convert categories.id to UUID
        ALTER TABLE categories 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Step 3: Convert all other id columns from TEXT to UUID (if needed)

-- Convert expenses.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'expenses' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE expenses 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert expenses.category_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'expenses' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE expenses 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Convert income.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'income' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE income 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert budgets.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'budgets' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE budgets 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert budgets.category_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'budgets' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE budgets 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Convert recurring_expenses.id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'recurring_expenses' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE recurring_expenses 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert recurring_expenses.category_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'recurring_expenses' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE recurring_expenses 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Convert categorization_patterns.category_id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'categorization_patterns' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE categorization_patterns 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Convert offline_sync_queue.record_id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'offline_sync_queue' 
        AND column_name = 'record_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE offline_sync_queue 
        ALTER COLUMN record_id TYPE UUID USING record_id::uuid;
    END IF;
END $$;

-- Convert expense_templates.id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'expense_templates' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE expense_templates 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert expense_templates.category_id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'expense_templates' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE expense_templates 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Convert quick_shortcuts.id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'quick_shortcuts' 
        AND column_name = 'id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE quick_shortcuts 
        ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;
END $$;

-- Convert quick_shortcuts.category_id (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'quick_shortcuts' 
        AND column_name = 'category_id' 
        AND data_type = 'text'
    ) THEN
        ALTER TABLE quick_shortcuts 
        ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
    END IF;
END $$;

-- Step 4: Recreate foreign key constraints with UUID types

-- Recreate expenses.category_id foreign key
ALTER TABLE expenses 
ADD CONSTRAINT expenses_category_id_fkey 
FOREIGN KEY (category_id) REFERENCES categories(id) 
ON DELETE RESTRICT;

-- Recreate budgets.category_id foreign key
ALTER TABLE budgets 
ADD CONSTRAINT budgets_category_id_fkey 
FOREIGN KEY (category_id) REFERENCES categories(id) 
ON DELETE CASCADE;

-- Recreate recurring_expenses.category_id foreign key
ALTER TABLE recurring_expenses 
ADD CONSTRAINT recurring_expenses_category_id_fkey 
FOREIGN KEY (category_id) REFERENCES categories(id) 
ON DELETE SET NULL;

-- Recreate categorization_patterns.category_id foreign key (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'categorization_patterns') THEN
        ALTER TABLE categorization_patterns 
        ADD CONSTRAINT categorization_patterns_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) 
        ON DELETE CASCADE;
    END IF;
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
END $$;
