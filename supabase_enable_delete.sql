-- Allow DELETE on all tables for the backend (since it uses the anon key)
CREATE POLICY "Enable delete for anon users on users" ON public.users FOR DELETE USING (true);

-- Also ensure DELETE is allowed on related tables just in case RLS is enabled on them
DO $$
DECLARE
    tbl_name text;
BEGIN
    FOR tbl_name IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        BEGIN
            EXECUTE format('CREATE POLICY "Enable delete for anon users" ON %I FOR DELETE USING (true);', tbl_name);
        EXCEPTION
            WHEN duplicate_object THEN NULL;
            WHEN others THEN NULL;
        END;
    END LOOP;
END
$$;
