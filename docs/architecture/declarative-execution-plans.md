# Declarative execution plans

The interpreter in `app/multiagent/execution_plan.py` accepts a versioned JSON plan with an explicit ordered list of steps. It does not convert natural-language text into executable steps. The assistant/orchestration layer must return a structured `result.plan` before the orchestrator dispatches it.

## Runtime flow

1. The orchestrator normalizes the assistant's domain `Response` or legacy dictionary response.
2. An explicit structured plan is passed to `TaskRunner.execute({"plan": plan, "user": authenticated_user_id})`.
3. `TaskRunner` validates the plan, resolves only capabilities in the host-configured authorizer allowlist, checks policy before each dispatch, and records lifecycle events.
4. Result projections are bounded and explicit references can only point to declared earlier steps.
5. Legacy `tasks` payloads remain supported during migration.

The `authenticated_user_id` must come from trusted request middleware/session context. A caller-controlled `user` field is ignored. If no authenticated identity is present, the plan uses `anonymous` and will normally be denied by the capability authorizer.

## Durable journal

The Supabase migration `202610260002_execution_plan_events.sql` creates an append-only event table with RLS enabled. The follow-up migration `202610270002_execution_plan_events_append_only_grants.sql` limits the `service_role` to SELECT and INSERT and grants no table privileges to `anon` or `authenticated`.

Configure these server-side environment variables on the runtime service:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Never expose the service-role key to clients, mobile apps, logs, or browser code. The service-role client is deliberately separate from the normal publishable/anon client. If it is missing or the journal insert fails, plan execution fails closed.

The journal stores only allowlisted event metadata; raw arguments, user prompts, tool results, and credentials must not be added to it. Database retention and access monitoring should be configured according to the deployment's privacy policy.

## Approval boundary

Plan arguments cannot self-assert `human_confirmed` or `remote_authorized`. Sensitive capabilities remain `approval_required` until a trusted approval/resume protocol binds approval to the authenticated principal, exact plan digest, capability, and expiration. Do not resume a side-effecting step automatically after an unknown outcome.

## Operational constraints

- The execution budget is checked between steps; it is not a preemptive timeout for a blocking connector.
- An exception after dispatch is an unknown outcome, not a safe-to-retry failure.
- A journal failure after a connector call may mean the external side effect occurred without a durable completion record.
- The production migration must be applied and verified before enabling declarative plans on a deployment.
