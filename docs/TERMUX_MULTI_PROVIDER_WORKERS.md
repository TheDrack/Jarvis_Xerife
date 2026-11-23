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
```

For a single worker, the existing global variables and `jarvis-worker configure` flow remain valid. A worker using server-side inference keeps `JARVIS_AGENT_REMOTE_INFERENCE=true`; its trusted provider metadata must match the provider configured on Render.

## Supported local API providers

The current worker uses an OpenAI-compatible Chat Completions client. Supported provider IDs are `groq`, `venice`, `freellmapi`, `openai`, `gemini`, `xai` and `qwen`. Generic providers require their own API key, base URL and model ID. Examples:

- Gemini: `https://generativelanguage.googleapis.com/v1beta` — [Google OpenAI-library compatibility](https://developers.googleblog.com/gemini-is-now-accessible-from-the-openai-library/)
- xAI/Grok: `https://api.x.ai/v1` — [xAI Chat Completions API](https://docs.x.ai/developers/rest-api-reference/inference/chat-completions)
- Qwen: a region/workspace-specific `.../compatible-mode/v1` endpoint — [Alibaba Cloud OpenAI compatibility](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope)

The Android ChatGPT, Claude, Gemini, Qwen and Grok apps are not themselves local inference servers. Their app sessions do not supply developer API keys. Claude's Messages API is not compatible with this Chat Completions client and requires a dedicated adapter. ChatGPT plan usage through Sign in with ChatGPT is limited to eligible paid plans; it is not available to a Free account. See [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart).

All worker slots currently advertise only `text_reasoning`. Provider selection does not grant repository, GitHub, shell, browser or production tools. The Android accessibility bridge is a separate, user-enabled route for controlled UI interaction; it must be running before any consumer-app UI adapter can be validated.
