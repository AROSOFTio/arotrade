-- AroTrade AI Database Initialization

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create custom types
CREATE TYPE user_role AS ENUM ('admin', 'trader', 'viewer');
CREATE TYPE signal_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'executed_demo',
    'executed_live',
    'expired',
    'cancelled'
);

CREATE TYPE trade_status AS ENUM (
    'pending',
    'open',
    'closed',
    'cancelled'
);

CREATE TYPE trading_mode AS ENUM ('demo', 'live');

-- Create initial tables comment
COMMENT ON DATABASE arotrade IS 'AroTrade AI - AI-Powered Trading Platform';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE arotrade TO arotrade;
GRANT ALL PRIVILEGES ON SCHEMA public TO arotrade;
