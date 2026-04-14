-- ============================================================
-- TPRM_AI Database Setup Script
-- Run this in pgAdmin Query Tool (connected as postgres superuser)
-- ============================================================

-- Step 1: Check if pgvector extension is available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        RAISE NOTICE '✓ pgvector extension is AVAILABLE';
    ELSE
        RAISE NOTICE '✗ pgvector extension is NOT AVAILABLE — you need to install it first';
        RAISE NOTICE 'See docs/windows-setup.md for installation instructions';
    END IF;
END $$;

-- Step 2: Create the application database (if not exists)
-- NOTE: CREATE DATABASE cannot run inside a transaction block.
-- If tprm_db does not exist, run this separately:
--   CREATE DATABASE tprm_db;

-- Step 3: Create the application user (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tprm_user') THEN
        CREATE ROLE tprm_user WITH LOGIN PASSWORD 'tprm_password';
        RAISE NOTICE '✓ Created user tprm_user';
    ELSE
        RAISE NOTICE '✓ User tprm_user already exists';
    END IF;
END $$;

-- Step 4: Grant privileges
-- (Run after connecting to tprm_db)
-- GRANT ALL PRIVILEGES ON DATABASE tprm_db TO tprm_user;
-- GRANT ALL ON SCHEMA public TO tprm_user;

-- Step 5: Enable pgvector extension (run in tprm_db)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Step 6: Verify pgvector
-- SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
