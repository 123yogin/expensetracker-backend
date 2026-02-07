-- Migration: Add user_id to all user-owned tables for multi-tenant isolation
-- user_id stores the Cognito 'sub' claim (UUID string)

-- 1. Add user_id column to expenses table
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);

-- 2. Add user_id column to income table
ALTER TABLE income ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_income_user_id ON income(user_id);

-- 3. Add user_id column to categories table
ALTER TABLE categories ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);

-- 4. Add user_id column to budgets table
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_budgets_user_id ON budgets(user_id);

-- 5. Add user_id column to recurring_expenses table
ALTER TABLE recurring_expenses ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_recurring_user_id ON recurring_expenses(user_id);

-- 6. Add user_id column to expense_templates table
ALTER TABLE expense_templates ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_templates_user_id ON expense_templates(user_id);

-- 7. Add user_id column to quick_shortcuts table
ALTER TABLE quick_shortcuts ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_shortcuts_user_id ON quick_shortcuts(user_id);

-- 8. Add user_id to groups table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'groups') THEN
        ALTER TABLE groups ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_groups_user_id ON groups(user_id);
    END IF;
END $$;

-- 9. Add user_id to budget_alerts if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'budget_alerts') THEN
        ALTER TABLE budget_alerts ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON budget_alerts(user_id);
    END IF;
END $$;

-- 10. Add user_id to export_history if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'export_history') THEN
        ALTER TABLE export_history ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_export_history_user_id ON export_history(user_id);
    END IF;
END $$;

-- 11. Add user_id to export_logs if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'export_logs') THEN
        ALTER TABLE export_logs ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_export_logs_user_id ON export_logs(user_id);
    END IF;
END $$;

-- 12. Add user_id to categorization_patterns if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'categorization_patterns') THEN
        ALTER TABLE categorization_patterns ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_patterns_user_id ON categorization_patterns(user_id);
    END IF;
END $$;

-- 13. Add user_id to user_preferences if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_preferences') THEN
        ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS user_id TEXT;
        -- Add unique constraint for preference per user
        DROP INDEX IF EXISTS idx_prefs_user_id;
        CREATE INDEX IF NOT EXISTS idx_prefs_user_id ON user_preferences(user_id);
    END IF;
END $$;

-- 14. Add user_id to receipt_photos if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'receipt_photos') THEN
        ALTER TABLE receipt_photos ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_receipts_user_id ON receipt_photos(user_id);
    END IF;
END $$;

-- 15. Add user_id to voice_sessions if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'voice_sessions') THEN
        ALTER TABLE voice_sessions ADD COLUMN IF NOT EXISTS user_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_voice_user_id ON voice_sessions(user_id);
    END IF;
END $$;

-- NOTE: After migration, user_id will be NULL for existing records.
-- You may want to assign existing records to a default user or clean them up.
-- Example: UPDATE expenses SET user_id = 'default-user-id' WHERE user_id IS NULL;
