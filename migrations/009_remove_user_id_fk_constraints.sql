-- Migration: Remove foreign key constraints on user_id columns
-- Since we use Cognito (external identity provider), user_id is a TEXT field
-- that stores the Cognito 'sub' claim, not a reference to a local users table.

-- Drop foreign key constraints on user_id columns for all tables
-- This is idempotent - it will only drop constraints that exist

DO $$
DECLARE
    constraint_record RECORD;
BEGIN
    -- Find and drop all foreign key constraints named with 'user_id_fkey'
    FOR constraint_record IN
        SELECT tc.table_name, tc.constraint_name
        FROM information_schema.table_constraints tc
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.constraint_name LIKE '%user_id_fkey%'
          AND tc.table_schema = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                      constraint_record.table_name,
                      constraint_record.constraint_name);
        RAISE NOTICE 'Dropped constraint % from table %',
                     constraint_record.constraint_name,
                     constraint_record.table_name;
    END LOOP;
END $$;

-- Also check for constraints with other naming patterns
DO $$
DECLARE
    constraint_record RECORD;
BEGIN
    FOR constraint_record IN
        SELECT 
            kcu.table_name,
            tc.constraint_name
        FROM information_schema.key_column_usage kcu
        JOIN information_schema.table_constraints tc 
            ON kcu.constraint_name = tc.constraint_name
        WHERE kcu.column_name = 'user_id'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                      constraint_record.table_name,
                      constraint_record.constraint_name);
        RAISE NOTICE 'Dropped user_id FK constraint % from table %',
                     constraint_record.constraint_name,
                     constraint_record.table_name;
    END LOOP;
END $$;

-- Ensure user_id columns are TEXT type (not UUID) for Cognito compatibility
-- Cognito 'sub' claim is a string that looks like a UUID but should be stored as TEXT

DO $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN
        SELECT c.table_name, c.data_type
        FROM information_schema.columns c
        WHERE c.column_name = 'user_id'
          AND c.table_schema = 'public'
          AND c.data_type = 'uuid'
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT',
                      tbl.table_name);
        RAISE NOTICE 'Converted user_id to TEXT in table %', tbl.table_name;
    END LOOP;
END $$;
