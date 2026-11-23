# Termux workers with independent model providers

The Termux queue runtime supports up to eight worker slots. Each slot has its own agent identity, worker credential, model provider and inference configuration. Global environment variables remain supported as defaults; a per-agent variable takes precedence.

## Provision each worker identity

Provision a different token for each agent and bind the provider on the server side. The provider identity is stored in the trusted `jarvis_agents` record and is not accepted from the heartbeat request body.

```bash
python scripts/manage_agent_worker_credentials.py issue \
  --agent-id jarvis-termux-mini-1 \
  --capability text_reasoning \
  --model-provider gemini

python scripts/manage_agent_worker_credentials.py issue \
  --agent-id jarvis-termux-mini-2 \
  --capability text_reasoning \
  --model-provider xai
```

The command displays each token once. Do not paste tokens or API keys into chat, logs or source control. Store them only in the Termux worker environment file, which must remain mode `600`.

## Configure the Android worker

Use a base agent ID without a trailing slot number when running multiple slots. The runtime generates `-1`, `-2`, etc. For every generated ID, configure the matching credential and provider-specific variables:

```bash
JARVIS_MINI_AGENT_ENABLED=true
JARVIS_MINI_AGENT_WORKERS=2
JARVIS_AGENT_ID=jarvis-termux-mini
JARVIS_TASK_QUEUE_API_URL=https://jarvis-api-c47i.onrender.com

JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_TERMUX_MINI_1=<token-one>
JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_TERMUX_MINI_1=false
JARVIS_AGENT_MODEL_PROVIDER_JARVIS_TERMUX_MINI_1=gemini
FREELLMAPI_API_KEY_JARVIS_TERMUX_MINI_1=<gemini-api-key>
FREELLMAPI_BASE_URL_JARVIS_TERMUX_MINI_1=https://generativelanguage.googleapis.com/v1beta
FREELLMAPI_MODEL_JARVIS_TERMUX_MINI_1=<gemini-model-id>

JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_TERMUX_MINI_2=<token-two>
JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_TERMUX_MINI_2=false
JARVIS_AGENT_MODEL_PROVIDER_JARVIS_TERMUX_MINI_2=xai
FREELLMAPI_API_KEY_JARVIS_TERMUX_MINI_2=<xai-api-key>
FREELLMAPI_BASE_URL_JARVIS_TERMUX_MINI_2=https://api.x.ai/v1
FREELLMAPI_MODEL_JARVIS_TERMUX_MINI_2=<grok-model-id>
```

Then restart the supervised service:

```bash
jarvis-worker restart
jarvis-worker status
python scripts/check_multiagent_env.py
```

The read-only checker reports queue authentication and inference readiness per worker without printing API keys or tokens. A `ready` result does not prove that the queue contains an eligible task or that the worker has claimed one.

For a single worker, the existing global variables and `jarvis-worker configure` flow remain valid. A worker using server-side inference keeps `JARVIS_AGENT_REMOTE_INFERENCE=true`; its trusted provider metadata must match the provider configured on Render.

## Supported local API providers

The current worker uses an OpenAI-compatible Chat Completions client. Supported provider IDs are `groq`, `venice`, `freellmapi`, `openai`, `gemini`, `xai` and `qwen`. Generic providers require their own API key, base URL and model ID. Examples:

- Gemini: `https://generativelanguage.googleapis.com/v1beta` — [Google OpenAI-library compatibility](https://developers.googleblog.com/gemini-is-now-accessible-from-the-openai-library/)
- xAI/Grok: `https://api.x.ai/v1` — [xAI Chat Completions API](https://docs.x.ai/developers/rest-api-reference/inference/chat-completions)
- Qwen: a region/workspace-specific `.../compatible-mode/v1` endpoint — [Alibaba Cloud OpenAI compatibility](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope)

The Android ChatGPT, Claude, Gemini, Qwen and Grok apps are not themselves local inference servers. Their app sessions do not supply developer API keys. Claude's Messages API is not compatible with this Chat Completions client and requires a dedicated adapter. ChatGPT plan usage through Sign in with ChatGPT is limited to eligible paid plans; it is not available to a Free account. See [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart).

All worker slots currently advertise only `text_reasoning`. Provider selection does not grant repository, GitHub, shell, browser or production tools. The Android accessibility bridge is a separate, user-enabled route for controlled UI interaction; it must be running before any consumer-app UI adapter can be validated.

## Optional Android consumer-app sessions

A worker can use an already-authenticated consumer app session as its local text model. This does not convert the subscription into an API key and does not replace API providers. It drives the visible Android app through the Jarvis AccessibilityService and is available only to a worker running on that same Android device.

Supported provider IDs are `android_app:chatgpt`, `android_app:claude`, `android_app:gemini`, `android_app:grok` and `android_app:qwen`. Before enabling one:

1. Enable **Jarvis Accessibility** in Android Settings → Accessibility → Installed apps. The service must expose the authenticated loopback `/healthz` endpoint.
2. Run `python scripts/check_multiagent_env.py`; it must report `android_accessibility_bridge` in the inference group.
3. Bind the trusted provider to the existing server-side agent record without rotating its token:

   ```bash
   python scripts/manage_agent_worker_credentials.py set-provider \
     --agent-id jarvis-termux-mini-1 \
     --model-provider android_app:claude
   ```

4. Add the per-agent settings to the Termux worker environment and restart it:

   ```bash
   JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_TERMUX_MINI_1=false
   JARVIS_AGENT_MODEL_PROVIDER_JARVIS_TERMUX_MINI_1=android_app:claude
   jarvis-worker restart
   ```

5. Run one controlled text-only smoke test and verify the result in the objective journal before using the provider for recurring work.

The adapter allows only the five installed package IDs, refuses login/password screens and unknown editable fields, requires an accessible send control, serializes all app sessions with a worker-process-wide lock, and never grants shell, browser, repository, or production tools. Only one foreground app conversation can execute at a time. If the service is disabled, the selected app is signed out, or its UI changes, inference fails closed and the queue attempt is released; the worker does not silently claim a fabricated answer.

Do not switch the active production Termux worker from its API provider until the Android service is enabled and the real device smoke test passes. API-backed providers remain the default and fallback route.
