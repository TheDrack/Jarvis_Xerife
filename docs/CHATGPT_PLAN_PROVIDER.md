# ChatGPT plan provider (Sign in with ChatGPT)

## Purpose and boundary

Jarvis can use an eligible ChatGPT plan through OpenAI's documented **Sign in with ChatGPT** open-source flow. This is not a ChatGPT UI automation and does not call the private `chatgpt.com/backend-api` endpoints. OAuth credentials are issued for this Jarvis installation and inference uses the public `https://api.openai.com/v1/responses` endpoint.

This provider is intended for the user's own local Jarvis runtime. Keep its tokens on the user's device or other user-controlled self-hosted runtime; do not put them in Render, Supabase, shared task records, browser storage, source control, logs, or prompts. Requests must be for this connected Jarvis application and originate from the user's activity or an automation the user expressly authorized. Do not expose this provider as a general-purpose API for other users or unrelated tools.

The plan-usage grant is separate from identity sign-in. Jarvis requires both `resource.invoke` and `chatgpt.tokens.use.direct`; a valid identity token alone is insufficient. OpenAI's Help Center currently says supported open-source integrations are available to all ChatGPT users, while its developer quickstart describes plan inference for eligible Plus/Pro users. Treat Free-tier plan inference as account/flow-dependent until the OAuth token response actually grants the required scopes; do not infer eligibility from successful identity sign-in. Model access and usage limits remain controlled by OpenAI and the account plan. Usage is shared with the applicable plan allowance, not a separate unlimited quota.

## Local setup

From the Jarvis repository root on the device that will run the provider:

```bash
PYTHONPATH="$PWD" python -m app.adapters.infrastructure.chatgpt_plan_auth login
```

The command opens the system browser. Sign in to ChatGPT and explicitly approve the Jarvis plan-usage permission. The first registration uses the loopback callback `http://127.0.0.1:1455/auth/callback`; later reauthorizations use a loopback port selected for that attempt. The callback listener binds only to `127.0.0.1`.

Check the local connection without printing credentials:

```bash
PYTHONPATH="$PWD" python -m app.adapters.infrastructure.chatgpt_plan_auth status
```

Send one isolated prompt:

```bash
PYTHONPATH="$PWD" python -m app.adapters.infrastructure.chatgpt_plan_auth prompt \
  --prompt "Resuma as diferenças entre TCP e UDP em cinco tópicos." \
  --model "<model-slug-from-account-catalog>"
```

If `--model` is omitted, Jarvis discovers the account's visible models and selects the first listed model. For repeatable automation, configure `JARVIS_CHATGPT_MODEL` or pass an explicit model slug.

To disconnect, attempt remote refresh-token revocation and remove local tokens:

```bash
PYTHONPATH="$PWD" python -m app.adapters.infrastructure.chatgpt_plan_auth logout
```

If `remote_revoked` is false, local tokens have still been cleared, but remote revocation was not confirmed. Disconnect Jarvis in ChatGPT Settings as a final control.

## Storage

Default local directory: `~/.config/jarvis/chatgpt/`.

- `profile.json`: validated account subject, issued client ID, OAuth tokens, scopes, and expiry.
- `registration.json`: issued client ID retained across an interrupted first token exchange and local sign-out.
- `host-id`: stable `ext_agent_host_id` for this Jarvis installation.
- `profile.json.lock`: cross-process lock used to serialize rotating refresh-token use.

On POSIX systems, the directory is set to `0700` and credential/registration/host files to `0600`. Override only the profile path with `JARVIS_CHATGPT_AUTH_FILE`; do not point it at a shared or remotely mounted location. The registration and host identifiers remain local metadata, not authentication secrets.

## Python integration

```python
from app.adapters.infrastructure.chatgpt_plan_auth import ChatGPTPlanOAuth
from app.application.ports.model_runtime import ModelInvocationRequest, ModelMessage
from app.multiagent.model_runtime_factory import create_registered_chatgpt_plan_runtime

oauth = ChatGPTPlanOAuth()
try:
    # The OAuth service refreshes near-expiry credentials and serializes refreshes.
    model_profile, bindings = create_registered_chatgpt_plan_runtime(
        oauth,
        model_id="<model-slug-from-account-catalog>",
    )
    runtime = bindings.resolve(model_profile)
    result = runtime.invoke(
        ModelInvocationRequest(
            messages=(ModelMessage("user", "Execute a tarefa de rotina aqui."),),
            max_output_tokens=1200,
        )
    )
    print(result.content)
    runtime.close()
finally:
    oauth.close()
```

For an existing bounded text-agent pipeline, inject the ChatGPT-backed handler instead of constructing a new agent type:

```python
from app.adapters.infrastructure.chatgpt_plan_auth import ChatGPTPlanOAuth
from app.multiagent.model_runtime_factory import create_registered_chatgpt_plan_handler

oauth = ChatGPTPlanOAuth()
try:
    handler = create_registered_chatgpt_plan_handler(
        oauth, model_id="<model-slug-from-account-catalog>"
    )
    # Inject `handler` into a local agent/worker that accepts FreeLLMAgentHandler.
    # Close the handler after its local worker has stopped.
    handler.close()
finally:
    oauth.close()
```

For a conversation owned by Jarvis, pass the required prior `system`/`user`/`assistant` messages in the same `ModelInvocationRequest`. This sends the supplied history as input on each call; it does **not** retrieve or modify existing ChatGPT conversations. Since this integration sets `store=false`, no server-side conversation state is used. Keep any Jarvis-side history in its own authorized local memory store.

The provider always streams and considers a request successful only after `response.completed`. The default model sampling behavior is preserved; an explicit non-default temperature is forwarded to models that support it. It rejects failed, incomplete, interrupted, malformed, or empty responses. It does not automatically retry an uncertain inference POST, avoiding accidental duplicate usage. It reports normalized token usage and sanitized error codes through `ModelRuntime`.

## Current scope

Implemented in this increment:

- OAuth authorization-code flow with PKCE, fresh state and nonce, loopback callback, dynamic client registration, and issued-client-ID reuse.
- ID-token signature/issuer/audience/expiry/nonce validation using OpenAI's JWKS.
- Local owner-only token storage, stable host ID, refresh-token rotation, cross-process refresh lock, and revocation on sign-out.
- Account model discovery and Responses API streaming with `store=false`.
- Provider-neutral `ModelRuntime` adapter and `ModelRuntimeBindings` factory.
- Android Termux MCP tools `chatgpt_plan_status` and `chatgpt_plan_prompt`; prompt execution goes through the versioned toolbox manifest, `ToolDispatcher`, session capability authorization, rate limiting, output validation and audit sink.
- The MCP prompt requires a separate local session created with `--profile termux_communication`. This grants only `communication.chatgpt.prompt`; it does not grant shell execution. The `termux_developer` profile remains restricted to `android.shell.exec`.
- Unit/integration tests with mocked HTTP transports and a real loopback callback test.

Not included yet:

- Importing or synchronizing existing ChatGPT conversations.
- Multiple simultaneously selectable ChatGPT profiles in the Jarvis settings UI.
- A general-purpose or public HTTP proxy to this local provider; access is via the authenticated local MCP channel and the dedicated `termux_communication` session capability only.
- Non-text modalities, hosted tools, or ChatGPT UI-only features.
- Live authorization/inference verification against the user's account; that requires the user to complete the browser consent flow.

## Official references

- [Sign in with ChatGPT — open-source quickstart](https://developers.openai.com/siwc/quickstart)
- [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
- [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Sign in with ChatGPT Terms](https://openai.com/policies/sign-in-with-chatgpt-terms/)
