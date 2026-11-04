-- Lock down legacy tables that have no verified client-side ownership contract.
-- All known application consumers use the server-only service-role client.
-- Keep service_role grants intact; revoke every client role and remove the
-- legacy role-only policy. This is intentionally fail-closed until a
-- per-user/public API contract is designed and tested.
DO $migration$
DECLARE
    v_table text;
    v_columns text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'capabilities',
        'command_results',
        'devices',
        'interactions',
        'jarvis_capabilities',
        'thought_logs',
        'user'
    ]
    LOOP
        EXECUTE format(
            'DROP POLICY IF EXISTS %I ON public.%I',
            'Enable all for authenticated users',
            v_table
        );

        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated',
            v_table
        );

        -- Table-level REVOKE does not remove column-level grants. Revoke those
        -- separately so a previously granted sensitive column cannot remain
        -- reachable through the Data API.
        SELECT string_agg(format('%I', column_name), ', ' ORDER BY ordinal_position)
          INTO v_columns
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = v_table;

        IF v_columns IS NOT NULL THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES (%s) ON TABLE public.%I FROM PUBLIC, anon, authenticated',
                v_columns,
                v_table
            );
        END IF;
    END LOOP;
END;
$migration$;
