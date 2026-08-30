-- V11 Cleanup SQL
-- Run before V11 experiment to ensure clean state

-- Delete existing data
DELETE FROM audit_items;
DELETE FROM audit_sessions;
DELETE FROM purchase_orders;
DELETE FROM inventory_items;
DELETE FROM sales_transactions;
DELETE FROM products;
DELETE FROM branches;
DELETE FROM users;

-- Reset sequences
ALTER SEQUENCE IF EXISTS users_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS branches_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS products_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS inventory_items_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS sales_transactions_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS purchase_orders_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS audit_sessions_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS audit_items_id_seq RESTART WITH 1;

-- V11: Add new columns for context engine
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS branch_a_stock DECIMAL;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS branch_b_stock DECIMAL;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS supplier_reliability VARCHAR(50);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS ghost_po_risk BOOLEAN DEFAULT FALSE;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS is_promotional BOOLEAN DEFAULT FALSE;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS promotion_uplift_pct DECIMAL;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS normal_velocity DECIMAL;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS trend VARCHAR(50);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS demand_volatility DECIMAL;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS seasonal_type VARCHAR(50);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS days_until_season INTEGER;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS days_since_season_ended INTEGER;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS historical_seasonal_multiplier DECIMAL;

-- V11: Add challenge tracking columns
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_status VARCHAR(50);
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_proposed_decision VARCHAR(50);
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_confidence DECIMAL;
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_reason TEXT;
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_valid BOOLEAN;
ALTER TABLE audit_items ADD COLUMN IF NOT EXISTS challenge_errors JSONB;
