-- Migration 010: Production hardening - Fix constraints, add composite indexes
-- ============================================================================
-- This migration addresses audit findings:
--   1. user_id NOT NULL constraints
--   2. Composite unique constraints (per-user uniqueness)
--   3. Performance indexes for common query patterns
--   4. Remove legacy global uniqueness constraints
-- ============================================================================

-- ============================================================
-- STEP 1: Clean up NULL user_id records
-- Records without user_id are legacy data that can't be associated with a user.
-- ============================================================

DELETE FROM expenses WHERE user_id IS NULL;
DELETE FROM income WHERE user_id IS NULL;
DELETE FROM categories WHERE user_id IS NULL;
DELETE FROM budgets WHERE user_id IS NULL;
DELETE FROM recurring_expenses WHERE user_id IS NULL;
DELETE FROM expense_templates WHERE user_id IS NULL;
DELETE FROM quick_shortcuts WHERE user_id IS NULL;

-- Clean optional tables
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'export_history') THEN
        DELETE FROM export_history WHERE user_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'export_logs') THEN
        DELETE FROM export_logs WHERE user_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'categorization_patterns') THEN
        DELETE FROM categorization_patterns WHERE user_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_preferences') THEN
        DELETE FROM user_preferences WHERE user_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'receipt_photos') THEN
        DELETE FROM receipt_photos WHERE user_id IS NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'budget_alerts') THEN
        DELETE FROM budget_alerts WHERE user_id IS NULL;
    END IF;
END $$;


-- ============================================================
-- STEP 2: Add NOT NULL constraints on user_id
-- ============================================================

ALTER TABLE expenses ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE income ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE categories ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE budgets ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE recurring_expenses ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE expense_templates ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE quick_shortcuts ALTER COLUMN user_id SET NOT NULL;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'export_history' AND column_name = 'user_id') THEN
        ALTER TABLE export_history ALTER COLUMN user_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'categorization_patterns' AND column_name = 'user_id') THEN
        ALTER TABLE categorization_patterns ALTER COLUMN user_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_preferences' AND column_name = 'user_id') THEN
        ALTER TABLE user_preferences ALTER COLUMN user_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'receipt_photos' AND column_name = 'user_id') THEN
        ALTER TABLE receipt_photos ALTER COLUMN user_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'budget_alerts' AND column_name = 'user_id') THEN
        ALTER TABLE budget_alerts ALTER COLUMN user_id SET NOT NULL;
    END IF;
END $$;


-- ============================================================
-- STEP 3: Fix unique constraints for multi-tenant isolation
-- Categories and budgets need uniqueness per-user, not globally
-- ============================================================

-- Drop old global unique constraint on categories.name
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'categories_name_key') THEN
        ALTER TABLE categories DROP CONSTRAINT categories_name_key;
    END IF;
END $$;

-- Add per-user unique constraint
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_categories_name_per_user') THEN
        ALTER TABLE categories ADD CONSTRAINT uq_categories_name_per_user UNIQUE (name, user_id);
    END IF;
END $$;

-- Drop old global unique on budgets.category_id
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'budgets_category_id_key') THEN
        ALTER TABLE budgets DROP CONSTRAINT budgets_category_id_key;
    END IF;
END $$;

-- Add per-user unique constraint for budgets
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_budgets_category_per_user') THEN
        ALTER TABLE budgets ADD CONSTRAINT uq_budgets_category_per_user UNIQUE (category_id, user_id);
    END IF;
END $$;

-- Add per-user unique constraint for user_preferences
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_preferences') THEN
        -- Drop old constraint if exists
        BEGIN
            ALTER TABLE user_preferences DROP CONSTRAINT IF EXISTS user_preferences_preference_key_user_id_key;
        EXCEPTION WHEN OTHERS THEN NULL;
        END;
        -- Add proper unique
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_prefs_key_per_user') THEN
            ALTER TABLE user_preferences ADD CONSTRAINT uq_user_prefs_key_per_user UNIQUE (preference_key, user_id);
        END IF;
    END IF;
END $$;


-- ============================================================
-- STEP 4: Add composite indexes for performance
-- These indexes match the most common query patterns
-- ============================================================

-- Expenses: filtered by user + date (most common query)
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date DESC);
-- Expenses: filtered by user + category
CREATE INDEX IF NOT EXISTS idx_expenses_user_category ON expenses(user_id, category_id);

-- Income: filtered by user + date
CREATE INDEX IF NOT EXISTS idx_income_user_date ON income(user_id, date DESC);

-- Categories: user's categories lookup
CREATE INDEX IF NOT EXISTS idx_categories_user_active ON categories(user_id, is_active);

-- Budgets: user's budget lookup by category
CREATE INDEX IF NOT EXISTS idx_budgets_user_category ON budgets(user_id, category_id);

-- Recurring expenses: user + active + next_date (for scheduler)
CREATE INDEX IF NOT EXISTS idx_recurring_user_active_next ON recurring_expenses(user_id, is_active, next_date);

-- Templates: user's templates
CREATE INDEX IF NOT EXISTS idx_templates_user_active ON expense_templates(user_id, is_active);


-- ============================================================
-- STEP 5: Add user_id type constraint (optional - for data integrity)
-- Cognito sub is always a UUID, enforce minimum length
-- ============================================================

ALTER TABLE expenses ADD CONSTRAINT chk_expenses_user_id_length CHECK (length(user_id) >= 36);
ALTER TABLE categories ADD CONSTRAINT chk_categories_user_id_length CHECK (length(user_id) >= 36);
