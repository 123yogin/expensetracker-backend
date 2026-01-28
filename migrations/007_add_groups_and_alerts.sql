-- Migration 007: Add Group Splitting and Budget Alerts
-- Support for splitwise-style groups and budget notifications

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Group Members (many-to-many relationship between groups and... well, users don't exist yet, so we'll use simple names for now)
-- In a real app with auth, this would link to users table.
-- For now, we will store "members" as simple text names linked to a group
CREATE TABLE IF NOT EXISTS group_members (
    id UUID PRIMARY KEY,
    group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, name)
);

-- Expense Splits (detailed split information)
CREATE TABLE IF NOT EXISTS expense_splits (
    id UUID PRIMARY KEY,
    expense_id UUID NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    member_id UUID REFERENCES group_members(id) ON DELETE SET NULL, -- Who owes this part
    amount DECIMAL(10,2) NOT NULL,
    is_paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add group_id to expenses table
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES groups(id) ON DELETE SET NULL;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS paid_by_member_id UUID REFERENCES group_members(id) ON DELETE SET NULL;

-- Budget Alerts History (to prevent spamming alerts)
CREATE TABLE IF NOT EXISTS budget_alerts (
    id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    month VARCHAR(7) NOT NULL, -- YYYY-MM
    threshold_percent INTEGER NOT NULL, -- 80 or 100
    alert_message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_expense_splits_expense ON expense_splits(expense_id);
CREATE INDEX IF NOT EXISTS idx_budget_alerts_month ON budget_alerts(month);
