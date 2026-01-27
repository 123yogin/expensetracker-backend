-- Migration 001: Initial Schema
-- Includes categories, expenses, income, budgets, and recurring_expenses

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
