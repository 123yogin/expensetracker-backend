-- Migration 001: Initial Schema
-- Includes categories, expenses, income, budgets, and recurring_expenses

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- PRE-MIGRATION: Ensure correct types if tables already exist as TEXT
DO $$
BEGIN
    -- Fix categories.id if it is TEXT
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'categories' AND column_name = 'id' AND data_type = 'text'
    ) THEN
        -- Check if there are any existing foreign keys that might block the conversion
        -- (Usually, if we are at Migration 001, we are either starting fresh or categories was created manually)
        ALTER TABLE categories ALTER COLUMN id TYPE UUID USING id::uuid;
    END IF;

    -- Fix other tables if they exist as TEXT (e.g. from a partial previous migration)
    -- expenses
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'expenses') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'expenses' AND column_name = 'id' AND data_type = 'text') THEN
            ALTER TABLE expenses ALTER COLUMN id TYPE UUID USING id::uuid;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'expenses' AND column_name = 'category_id' AND data_type = 'text') THEN
            ALTER TABLE expenses ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
        END IF;
    END IF;

    -- income
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'income') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'income' AND column_name = 'id' AND data_type = 'text') THEN
            ALTER TABLE income ALTER COLUMN id TYPE UUID USING id::uuid;
        END IF;
    END IF;

    -- budgets
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'budgets') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'budgets' AND column_name = 'id' AND data_type = 'text') THEN
            ALTER TABLE budgets ALTER COLUMN id TYPE UUID USING id::uuid;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'budgets' AND column_name = 'category_id' AND data_type = 'text') THEN
            ALTER TABLE budgets ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
        END IF;
    END IF;

    -- recurring_expenses
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'recurring_expenses') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'recurring_expenses' AND column_name = 'id' AND data_type = 'text') THEN
            ALTER TABLE recurring_expenses ALTER COLUMN id TYPE UUID USING id::uuid;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'recurring_expenses' AND column_name = 'category_id' AND data_type = 'text') THEN
            ALTER TABLE recurring_expenses ALTER COLUMN category_id TYPE UUID USING category_id::uuid;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expenses (
    id UUID PRIMARY KEY,
    date DATE NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id UUID NOT NULL REFERENCES categories(id),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id);

CREATE TABLE IF NOT EXISTS income (
    id UUID PRIMARY KEY,
    date DATE NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    source TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_income_date ON income(date);

CREATE TABLE IF NOT EXISTS budgets (
    id UUID PRIMARY KEY,
    category_id UUID UNIQUE NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budgets_category_id ON budgets(category_id);

CREATE TABLE IF NOT EXISTS recurring_expenses (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
    frequency TEXT NOT NULL,
    next_date DATE NOT NULL,
    note TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recurring_next_date ON recurring_expenses(next_date);
