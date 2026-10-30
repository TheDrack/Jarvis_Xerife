# Scripts – JARVIS Utilitários e Daemons

This directory contains scripts for the Jarvis Self-Healing System and the Proactive Core.

## Overview

The scripts are part of Jarvis's self-healing and proactive architecture, enabling automatic detection, analysis, and correction of code errors as well as background system monitoring.

## Scripts


### setup_chatgpt_jarvis_tunnel.ps1

Windows setup and recovery helper for OpenAI Secure MCP Tunnel. It configures the official `tunnel-client` to forward requests to the private Jarvis MCP server at `127.0.0.1:8765/mcp`.

**Usage (PowerShell, as the user who owns the tunnel):**

```powershell
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action configure
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action status
```

The script prompts for the user's own `tunnel_id` and runtime key, stores the key using Windows DPAPI, runs the official client diagnostics, and creates a per-user logon task with up to five retries at one-minute intervals. Supported actions: `configure`, `run`, `start`, `status`, `stop`, and `uninstall`.

**Important:** this script does not create the OpenAI-hosted tunnel or register the custom MCP app in ChatGPT. The user must have the appropriate Platform permissions, associate the tunnel with the target ChatGPT workspace, then add it through ChatGPT Plugins → Add custom MCP server → Connection: Tunnel. Verify the app with a safe tool call before declaring end-to-end success. See [../docs/SECURE_MCP_TUNNEL.md](../docs/SECURE_MCP_TUNNEL.md).


### overwatch_daemon.py

Background daemon that implements the **JARVIS Proactive Core** (`[PROACTIVE_CORE]`).

**Features:**
- Monitors CPU and RAM usage (alerts if > 85%)
- Detects changes in `data/context.json`
- After 30 min of user inactivity, uses `VisionAdapter` to verify presence and suggests pending calendar tasks
- Uses `nexus.resolve()` to access `vision_adapter`, `telegram_adapter` and `voice_provider`
- All proactive log lines prefixed with `[PROACTIVE_CORE]`

**Usage (standalone):**

```bash
python scripts/overwatch_daemon.py
```

**Embedded (started automatically in `main.py`):**

```python
from scripts.overwatch_daemon import OverwatchDaemon
daemon = OverwatchDaemon()
daemon.start()  # non-blocking daemon thread
```

**Environment Variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for proactive notifications |
| `GEMINI_API_KEY` | No | Required only for VisionAdapter (inactivity check) |

**Thresholds (configurable via constructor):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cpu_threshold` | 85% | CPU% above which a warning is sent |
| `ram_threshold` | 85% | RAM% above which a warning is sent |
| `inactivity_timeout` | 1800 s | Seconds before vision-based presence check |

---

### auto_fixer_logic.py

Main auto-fixer script that implements the complete self-healing workflow.

**Features:**
- Reads error messages from environment variables
- Extracts affected file paths from error messages
- Sends error and code to AI (Groq/Gemini) for analysis
- Receives corrected code from AI
- Applies fixes locally
- Creates Git branches (`fix/issue-{ID}`)
- Commits changes
- Opens Pull Requests using GitHub CLI

**Usage:**

```bash
# Set environment variables
export ISSUE_BODY="Error: NameError in file app/main.py line 42..."
export ISSUE_ID="123"

# Set API key (choose one)
export GROQ_API_KEY="your-groq-api-key"
# OR
export GOOGLE_API_KEY="your-gemini-api-key"

# Run the auto-fixer
python scripts/auto_fixer_logic.py
```

**Environment Variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `ISSUE_BODY` | Yes | The error message or issue description |
| `ISSUE_ID` | Yes | The issue/error identifier (used in branch name) |
| `GROQ_API_KEY` | No* | API key for Groq (tries first) |
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | No* | API key for Google Gemini (fallback) |
| `GROQ_MODEL` | No | Groq model to use (default: llama-3.3-70b-versatile) |
| `GEMINI_MODEL` | No | Gemini model to use (default: gemini-1.5-flash) |

*At least one AI API key is required.

**Prerequisites:**

1. **GitHub CLI (gh)** - Install from https://cli.github.com/
   ```bash
   # Install gh CLI
   # macOS
   brew install gh
   # Ubuntu/Debian
   sudo apt install gh
   # Windows
   winget install --id GitHub.cli
   
   # Authenticate
   gh auth login
   ```

2. **AI API Keys** - Get from:
   - Groq: https://console.groq.com/
   - Google Gemini: https://aistudio.google.com/apikey

3. **Python Dependencies:**
   ```bash
   # Install AI libraries
   # Note: Install with 'pip install google-genai', import as 'from google import genai'
   pip install groq google-genai
   ```

**Workflow:**

```
1. Read ISSUE_BODY from environment
2. Extract file path from error message
3. Read current file content
4. Send to AI API (Groq → Gemini fallback)
5. Receive corrected code
6. Apply fix to file
7. Create branch: fix/issue-{ISSUE_ID}
8. Commit changes
9. Push to remote
10. Create Pull Request
```

### fix_applier.py

Módulo de suporte ao self-healing — I/O de arquivos, interação com GitHub Copilot CLI e validação de correções.

**Funções principais:**

| Função | Descrição |
|---|---|
| `read_file(path)` | Lê o conteúdo de um arquivo com tratamento de erro |
| `write_file(path, content)` | Escreve conteúdo em um arquivo de forma atômica |
| `call_copilot_cli(prompt)` | Chama o GitHub Copilot CLI (`gh copilot suggest`) |
| `validate_fix_with_pytest(path)` | Executa pytest no arquivo corrigido para validar o fix |
| `parse_pytest_report(report_path)` | Lê e interpreta relatório JSON do pytest |

---

### issue_parser.py

Módulo de classificação de issues e localização de arquivos afetados.

**Funções principais:**

| Função | Descrição |
|---|---|
| `is_documentation_request(issue_body)` | Detecta se o issue é um pedido de documentação |
| `classify_issue_type(issue_body)` | Classifica em `bug`, `documentation` ou `feature` |
| `extract_file_path(issue_body)` | Extrai o caminho do arquivo afetado do traceback/issue |

---

### pr_manager.py

Módulo de operações Git e GitHub para o pipeline de self-healing.

**Funções principais:**

| Função | Descrição |
|---|---|
| `create_branch(branch_name)` | Cria e faz checkout de um novo branch Git |
| `commit_and_push(branch, files, message)` | Adiciona, comita e faz push das correções |
| `open_pull_request(branch, title, body)` | Abre um Pull Request via GitHub CLI |
| `close_issue(issue_id, comment)` | Fecha o issue com um comentário de resolução |
| `attempt_repair(issue_id, issue_body)` | Orquestrador end-to-end: parse → fix → validate → PR |

**Dependências:** `fix_applier`, `issue_parser`

---

### test_auto_fixer.py

Test script for the auto-fixer with a sample error scenario.

**Usage:**

```bash
# Run the test
python scripts/test_auto_fixer.py
```

The test will:
1. Create a test file with an intentional error
2. Run the auto-fixer on it
3. Verify the fix was applied
4. Leave files for manual review

## Integration with GitHub Actions

You can integrate the auto-fixer with GitHub Actions to automatically fix failing CI/CD builds.

**Active workflows:**

- `.github/workflows/jarvis-pr-validation.yml` runs the complete pytest suite for pull requests. It has `contents: read`, disables checkout credential persistence, references no repository secrets, and never invokes the healer.
- `.github/workflows/homeostase.yml` is the privileged recovery path. It runs only for failed/timed-out/cancelled workflow runs originating from the trusted `main` branch, or for manual dispatch from `main`. It always checks out `main` and does not process pull-request workflow runs.
- The healer may use provider keys while generating a proposal, but the final pytest execution runs after those keys are removed from the environment. Eligible changes are staged only from `app/`, `scripts/`, `tests/`, and `docs/`; workflow files are excluded. Every automatic correction is pushed to a unique branch and proposed through a PR. The workflow does not push to `main`.

The healer command remains:

```bash
uv run python scripts/jarvis_healer.py \
  --report report.json --log pytest_log.txt \
  [--production-log production_error.log] \
  [--workflow-log failed_workflow_logs.txt] [--dry-run]
```

`jarvis_healer.py` parses the reports and applies the minimal fix (use `--dry-run` to only list what it would change). `auto_fixer_logic.py` remains the issue-driven entry point: it reads `ISSUE_BODY` / `ISSUE_ID` from the environment (see the section above) and opens the corresponding PR, so it can be wired to a custom CI job as shown below.

**Example minimal workflow for custom CI auto-healing:**

```yaml
name: Auto-Heal CI Failures

on:
  workflow_run:
    workflows: ["CI"]
    types:
      - completed

jobs:
  auto-heal:
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install groq google-genai
      
      - name: Install GitHub CLI
        run: |
          type -p gh >/dev/null 2>&1 || {
            echo "Installing GitHub CLI..."
            sudo apt-get update
            sudo apt-get install -y gh
          }
      
      - name: Get workflow logs
        id: get-logs
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          LOGS=$(gh run view ${{ github.event.workflow_run.id }} --log 2>&1 || echo "Failed to get logs")
          echo "logs<<EOF" >> $GITHUB_OUTPUT
          echo "$LOGS" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      
      - name: Run auto-fixer
        env:
          ISSUE_BODY: ${{ steps.get-logs.outputs.logs }}
          ISSUE_ID: ${{ github.event.workflow_run.id }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python scripts/auto_fixer_logic.py
```

## Outros scripts

| Script | Descrição |
|--------|-----------|
| `jarvis_healer.py` | Auto-cura a partir de relatórios/logs de pytest (`--report`, `--log`, `--production-log`, `--workflow-log`, `--dry-run`) |
| `metabolism_analyzer.py` | Classifica a mutação (intent/impacto/estratégia) e escreve os outputs do workflow em `$GITHUB_OUTPUT` |
| `evolve_all_pending.py` | Evolui capabilities pendentes em lote via `EvolutionOrchestrator` (`--dry-run`, `--limit`, `--cap-id`, `--delay`, `--max-attempts`, `--roadmap-context`) |
| `validate_architecture.py` | Valida camadas, ports, adapters e o container DI (marca a camada edge como skip quando as dependências de hardware não estão instaladas) |
| `validate_self_awareness.py` | Valida a autoconsciência via Long Context (snapshot consolidado, serviço, registry do Nexus e consumidores) |
| `overwatch_daemon.py` | Daemon do Proactive Core (CPU/RAM, inatividade, contexto) |
| `repo_lifecycle_governance.py` | Governança do ciclo de vida do repositório |
| `autodoc.py` | Extrai assinaturas e atualiza o mapa de arquitetura |
| `cristalize_project.py` | Cristaliza o codebase no formato `.jrvs` |

## Error Message Patterns

The auto-fixer can extract file paths from various error message formats:

**Python:**
```
File "app/main.py", line 42, in function_name
  NameError: name 'variable' is not defined
```

**JavaScript/TypeScript:**
```
Error: Cannot find module './missing-file'
    at app/server.js:42:15
```

**Generic:**
```
in file app/utils.py: SyntaxError on line 10
```

The script uses regex patterns to identify file paths in these formats.

## Architecture

The auto-fixer is part of the Jarvis Self-Healing Orchestrator architecture:

```
┌─────────────────────────────────────────┐
│     GitHub Actions (CI/CD Failure)      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Auto-Fixer Trigger              │
│  (workflow_run event or manual)         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│      auto_fixer_logic.py                │
│  1. Extract error & file                │
│  2. Read code                            │
│  3. AI analysis (Groq/Gemini)           │
│  4. Apply fix                            │
│  5. Git workflow                         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Pull Request Created            │
│  Branch: fix/issue-{ID}                 │
│  Ready for review                       │
└─────────────────────────────────────────┘
```

## Safety Features

1. **Human Review**: All fixes create PRs that require review before merging
2. **AI Fallback**: Tries Groq first, falls back to Gemini
3. **Error Handling**: Comprehensive error handling and logging
4. **Branch Isolation**: Each fix is in its own branch
5. **Detailed Logging**: Full trace of actions taken

## Troubleshooting

**"GitHub CLI is not authenticated"**
```bash
gh auth login
```

**"No API keys found"**
```bash
# Set one of these
export GROQ_API_KEY="your-key"
export GOOGLE_API_KEY="your-key"
```

**"Could not extract file path from error message"**
- Ensure the error message contains a file path
- Check the error message patterns in the script
- The ISSUE_BODY should contain the actual error traceback

**"Failed to create pull request"**
- Ensure you have push access to the repository
- Check that the remote is properly configured
- Verify GitHub CLI authentication

## Future Enhancements

- [ ] Support for multi-file fixes
- [ ] Integration with ThoughtLog system for tracking
- [ ] Retry mechanism with exponential backoff
- [ ] Support for more error patterns
- [ ] Auto-merge for low-risk fixes
- [ ] Slack/Discord notifications
- [ ] Learning from successful fixes

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall architecture
- [docs/AGENT_GUIDE.md](../docs/AGENT_GUIDE.md) - Agent guide (Nexus IDs, files, artifacts)
- [app/application/services/github_worker.py](../app/application/services/github_worker.py) - GitHub integration

## License

Part of the Jarvis Assistant project. See [LICENSE](../LICENSE) for details.
