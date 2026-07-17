-- 1. Setup RLS on the users table (if not already enabled)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- 2. Policy: Allow users to view all profiles
CREATE POLICY "Enable read access for all users" ON public.users
    FOR SELECT USING (true);

-- 3. Policy: Block all direct client updates, inserts, and deletes.
-- The Flask backend will use the service_role key to manage users securely,
-- completely blocking any client-side tampering of roles and departments.
CREATE POLICY "Block direct client updates" ON public.users
    FOR UPDATE USING (false);

CREATE POLICY "Block direct client inserts" ON public.users
    FOR INSERT WITH CHECK (false);

CREATE POLICY "Block direct client deletes" ON public.users
    FOR DELETE USING (false);
