-- Supabase SQL Migration
-- Creates a standalone users table with manual authentication fields

-- Drop old objects if they exist
DROP TABLE IF EXISTS profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Create users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'intern')),
    department TEXT CHECK (department IN ('Full-Stack', 'AI', 'Sales', 'Social Business Analysis') OR department IS NULL),
    manager_id UUID REFERENCES users(id) ON DELETE SET NULL,
    internship_duration_months INTEGER,
    leave_allotted_days INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'at_risk')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Note: We intentionally DO NOT enable Row Level Security (RLS) on the users table.
-- Security is managed exclusively by the Flask backend which acts as the 'admin' 
-- holding the service role key with full access.
