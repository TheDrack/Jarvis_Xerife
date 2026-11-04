-- pgTAP regression tests for the legacy public-table lockdown migration.
-- Run against a disposable Supabase database after applying the migration.
BEGIN;
SELECT plan(5);

SELECT ok(
    (
        SELECT bool_and(
            NOT has_table_privilege(role_name, format('public.%I', table_name), privilege_name)
        )
        FROM unnest(ARRAY[
            'capabilities',
            'command_results',
            'devices',
            'interactions',
            'jarvis_capabilities',
            'thought_logs',
            'user'
        ]) AS tables(table_name)
        CROSS JOIN unnest(ARRAY['anon', 'authenticated']) AS roles(role_name)
        CROSS JOIN unnest(ARRAY[
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
        ]) AS privileges(privilege_name)
    ),
    'anon and authenticated have no table privileges on legacy tables'
);

SELECT ok(
    NOT EXISTS (
        SELECT 1
        FROM information_schema.column_privileges
        WHERE table_schema = 'public'
          AND table_name = ANY (ARRAY[
              'capabilities',
              'command_results',
              'devices',
              'interactions',
              'jarvis_capabilities',
              'thought_logs',
              'user'
          ])
          AND grantee IN ('PUBLIC', 'anon', 'authenticated')
    ),
    'no PUBLIC or client-role column grants remain'
);

SELECT ok(
    (
        SELECT bool_and(
            has_table_privilege('service_role', format('public.%I', table_name), privilege_name)
        )
        FROM unnest(ARRAY[
            'capabilities',
            'command_results',
            'devices',
            'interactions',
            'jarvis_capabilities',
            'thought_logs',
            'user'
        ]) AS tables(table_name)
        CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS privileges(privilege_name)
    ),
    'service_role retains the CRUD privileges used by trusted server adapters'
);

SELECT is(
    (
        SELECT count(*)::integer
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = ANY (ARRAY[
              'capabilities',
              'command_results',
              'devices',
              'interactions',
              'jarvis_capabilities',
              'thought_logs',
              'user'
          ])
          AND policyname = 'Enable all for authenticated users'
    ),
    0,
    'the broad authenticated-role policy is removed from every legacy table'
);

SELECT ok(
    NOT has_column_privilege('anon', 'public.user', 'hashed_password', 'SELECT')
    AND NOT has_column_privilege('authenticated', 'public.user', 'hashed_password', 'SELECT')
    AND NOT has_column_privilege('anon', 'public.user', 'hashed_password', 'UPDATE')
    AND NOT has_column_privilege('authenticated', 'public.user', 'hashed_password', 'UPDATE'),
    'password hashes are inaccessible to client roles'
);

SELECT * FROM finish();
ROLLBACK;
