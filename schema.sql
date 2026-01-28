-- SQL Schema for Personal Expense Tracker (PostgreSQL)

-- Categories Table
CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expenses Table
CREATE TABLE IF NOT EXISTS expenses (
    id UUID PRIMARY KEY,
    date DATE NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id UUID NOT NULL REFERENCES categories(id),
    note TEXT,
    is_split BOOLEAN DEFAULT FALSE,
    split_amount DECIMAL(10,2) DEFAULT 0.00,
    split_with TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Index for faster queries on expenses
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id);

-- Income Table
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

-- Budgets Table (Global per category)
CREATE TABLE IF NOT EXISTS budgets (
    id UUID PRIMARY KEY,
    category_id UUID UNIQUE NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budgets_category_id ON budgets(category_id);

-- Expense Templates Table (for quick entry)
CREATE TABLE IF NOT EXISTS expense_templates (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    category_id UUID REFERENCES categories(id) ON DELETE CASCADE,
    default_amount DECIMAL(10,2),
    note_template TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_templates_active ON expense_templates(is_active);

-- Quick Shortcuts Table (for dashboard shortcuts)
CREATE TABLE IF NOT EXISTS quick_shortcuts (
    id UUID PRIMARY KEY,
    category_id UUID REFERENCES categories(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_shortcuts_position ON quick_shortcuts(position);

-- Recurring Expenses Table (for automated/reminder bills)
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
