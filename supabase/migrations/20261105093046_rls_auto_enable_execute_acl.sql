-- The event trigger is an internal DDL hook, not a client RPC.
-- The existing event trigger keeps working after creation-time EXECUTE checks;
-- only postgres (the function owner) needs direct function privileges.
revoke all privileges on function public.rls_auto_enable()
    from public, anon, authenticated, service_role;