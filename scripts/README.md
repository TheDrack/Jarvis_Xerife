# Auto-Fixer Scripts

This directory contains scripts for the Jarvis Self-Healing System.

## Overview

The auto-fixer system is part of Jarvis's self-healing architecture, enabling automatic detection, analysis, and correction of code errors using AI.

## Scripts

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

**Active workflow (`.github/workflows/ci-failure-to-issue.yml`):**

The repository uses a two-step approach for CI auto-healing:
1. `ci-failure-to-issue.yml` - Creates GitHub issues from CI failures
2. `jarvis_code_fixer.yml` - Automatically fixes issues labeled with `auto-code`

This approach provides better visibility and audit trails. See the actual workflow files in `.github/workflows/` for implementation details.

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

- [SELF_HEALING_ARCHITECTURE.md](../SELF_HEALING_ARCHITECTURE.md) - Overall architecture
- [demo_self_healing.py](../demo_self_healing.py) - Demo of the system
- [app/application/services/github_worker.py](../app/application/services/github_worker.py) - GitHub integration

## License

Part of the Jarvis Assistant project. See [LICENSE](../LICENSE) for details.
