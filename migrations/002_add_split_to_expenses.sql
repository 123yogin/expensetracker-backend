-- Migration 002: Add Split Columns to Expenses table
-- Adds is_split, split_amount, and split_with columns idempotently

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS is_split BOOLEAN DEFAULT FALSE;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS split_amount DECIMAL(10,2) DEFAULT 0.00;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS split_with TEXT;
