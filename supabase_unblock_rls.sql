-- 1. Drop the restrictive policies from earlier
DROP POLICY IF EXISTS "Block direct client updates" ON public.users;
DROP POLICY IF EXISTS "Block direct client inserts" ON public.users;
DROP POLICY IF EXISTS "Block direct client deletes" ON public.users;

-- 2. Create permissive policies so the backend (using anon key) can manage users
CREATE POLICY "Enable insert for anon users" ON public.users FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update for anon users" ON public.users FOR UPDATE USING (true);
-- (Delete is already covered by the previous script, but just in case)
CREATE POLICY "Enable delete for anon users" ON public.users FOR DELETE USING (true);
