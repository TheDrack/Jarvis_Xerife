# Jarvis Self-Healing System - Complete Guide

## Overview

The Jarvis Self-Healing System is an automated issue resolution framework that uses **GitHub Copilot CLI** (native GitHub integration) to detect, analyze, and fix errors in your repository. It operates on three main triggers:

1. **Jarvis API Integration**: When Jarvis sends requests via the API (`/v1/jarvis/dispatch`)
2. **Issue-based Resolution**: When GitHub Issues are created with `auto-code` label
3. **CI/CD Failure Resolution**: When GitHub Actions workflows fail

**Key Features:**
- 🤖 Native GitHub Copilot CLI integration (no external API keys needed)
- 🔒 Infinite loop prevention (maximum 3 attempts per issue)
- 📊 Log truncation for terminal overflow protection (5000 char limit)
- 🔄 Automatic PR creation with detailed context (NOT issues!)
- 🎯 Smart file detection from error messages or keywords
- 🌐 REST API integration for external systems like Jarvis

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Repository                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Jarvis API   │  │ GitHub       │  │ GitHub       │     │
│  │ (REST)       │  │ Issues       │  │ Actions      │     │
│  │              │  │ (auto-code)  │  │ (CI/CD)      │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │              │
│         │ repository_     │ Issue Created   │ Workflow     │
│         │ dispatch        │                 │ Failed       │
│         │                 │                 │              │
│         └────────┬────────┴─────────────────┘              │
│                  │                                         │
│                  ▼                                         │
│       ┌────────────────────────┐                          │
│       │ Jarvis Self-Healing    │                          │
│       │ Workshop               │                          │
│       │ (jarvis_code_fixer.yml)│                          │
│       └──────────┬─────────────┘                          │
│                  │                                         │
│                  │ Creates Issue (if API)                  │
│                  │ Then processes                          │
│                  ▼                                         │
│       ┌────────────────────┐                              │
│       │ Auto-Fixer Logic   │                              │
│       │ (GitHub Copilot)   │                              │
│       │  • gh copilot      │                              │
│       │  • explain/suggest │                              │
│       │  • Loop prevention │                              │
│       └──────────┬─────────┘                              │
│                  │                                         │
│                  ▼                                         │
│       ┌────────────────────┐                              │
│       │ Pull Request       │ ← Always creates PR          │
│       │ Created            │   (NEVER creates issue!)     │
│       └────────────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

## Workflows

### 1. Jarvis Self-Healing Workshop (`jarvis_code_fixer.yml`)

**Triggers:**
- GitHub Issues with label `auto-code` or `jarvis-auto-report`
- Repository Dispatch events (`jarvis_order` or `auto_fix`) from Jarvis API
- Pull Request events (for testing)

**Process for API Requests:**
1. Receives `repository_dispatch` event from Jarvis API
2. Extracts payload (intent, instruction, context, triggered_by)
3. Creates a GitHub Issue with `auto-code` and `jarvis-api` labels
4. Skips pytest (not needed for API requests)
5. Runs auto-fixer in standard mode
6. Auto-fixer creates a Pull Request with the fix
7. If auto-fixer fails, adds a comment to the issue (NOT a new issue!)

**Process for Issues:**
1. Detects new issues with the `auto-code` label
2. Checks infinite loop prevention (max 3 attempts per issue)
3. Reads the issue body containing error information
4. Installs GitHub Copilot CLI extension automatically
5. Passes the error to the auto-fixer script
6. Auto-fixer uses `gh copilot explain` and `gh copilot suggest` to analyze and generate fix
7. Truncates logs if needed (max 5000 characters)
8. Creates a Pull Request with the proposed fix
9. Closes the original issue

**Configuration Required:**
- GitHub Copilot subscription (or trial) ✅
- Workflow permissions: `contents: write`, `pull-requests: write`, `issues: write` ✅
- **No external API keys needed!** 🎉

**Security Features:**
- Maximum 3 healing attempts per issue (prevents infinite loops)
- Automatic log truncation (prevents terminal overflow)
- Issue duplicate detection (prevents spam)
- Comments on issues instead of creating new ones (prevents issue spam)

### 2. CI Failure to Issue (`ci-failure-to-issue.yml`)

**Trigger:** When the "Python Tests" workflow completes with a failure

**Process:**
1. Detects when Python Tests workflow fails
2. Extracts error logs from the failed run (truncated to 5000 chars)
3. Creates a GitHub Issue with:
   - Workflow name and run ID
   - Branch and commit SHA
   - Error logs (truncated to 5000 chars)
   - Automatic `auto-code` label
4. This issue then triggers the Jarvis Self-Healing Workshop (workflow #1)

**Configuration Required:**
- Workflow permissions: `contents: read`, `issues: write` ✅

**Smart Features:**
- Checks for duplicate issues (same workflow, same branch)
- If duplicate exists, adds a comment instead of creating new issue
- Includes direct link to failed workflow run
- Log truncation prevents overwhelming the issue body

## CI Failure Auto-Healing Flow

When a CI workflow fails, the system follows this path:
1. **Python Tests fail** → triggers `ci-failure-to-issue.yml`
2. **Issue created** with `auto-code` label → triggers `jarvis_code_fixer.yml`
3. **Auto-fix applied** → Pull Request created
4. **Original issue closed** → Clean resolution

This approach provides full visibility and traceability through GitHub Issues.

### 3. (Removed) Auto-Heal CI Failures

**Note:** The `auto-heal.yml` workflow has been removed to simplify the auto-healing system.
Previously, it attempted to fix CI failures directly without creating issues, which was redundant
with the ci-failure-to-issue → jarvis_code_fixer flow. The issue-based approach provides better
visibility and audit trails.

**Trigger:** When the "Python Tests" workflow completes with a failure

**Process:**
1. Detects when Python Tests workflow fails
2. Extracts error logs from the failed run (truncated to 5000 chars)
3. Creates a GitHub Issue with:
   - Workflow name and run ID
   - Branch and commit SHA
   - Error logs (truncated to 5000 chars)
   - Automatic `auto-code` label
4. This issue then triggers the Jarvis Self-Healing Workshop

**Smart Features:**
- Checks for duplicate issues (same workflow, same branch)
- If duplicate exists, adds a comment instead of creating new issue
- Includes direct link to failed workflow run
- Log truncation prevents overwhelming the issue body

## Auto-Fixer Logic (`scripts/auto_fixer_logic.py`)

The core intelligence of the self-healing system.

### Capabilities

1. **Error Detection**
   - Extracts file paths from Python tracebacks
   - Identifies common files (README.md, requirements.txt, etc.)
   - Suggests files based on keywords in error messages

2. **Request Type Detection**
   - **Bug Fix**: Analyzes code errors and generates fixes
   - **Documentation Request**: Updates documentation files
   - **Feature Request**: Implements new functionality

3. **GitHub Copilot CLI Integration**
   - Uses `gh copilot explain` to understand errors
   - Uses `gh copilot suggest` to generate fixes
   - Native GitHub ecosystem integration (no external APIs)
   - Automatic extension installation in workflows

4. **Security & Resilience**
   - **Infinite Loop Prevention**: Tracks attempts in `.github/healing_attempts.json`
   - **Maximum 3 attempts** per issue
   - **Log Truncation**: Limits logs to 5000 characters to prevent terminal overflow
   - **Duplicate Prevention**: Avoids creating duplicate issues/PRs

5. **Git Operations**
   - Creates feature branch: `fix/issue-{ID}`
   - Commits changes with descriptive message
   - Pushes to remote repository
   - Creates Pull Request with detailed description
   - Closes original issue automatically

### Supported File Types

- **Python files** (`.py`)
- **Documentation** (`.md`, `.rst`)
- **Configuration** (`.txt`, `.yml`, `.yaml`, `.json`)
- **Any text-based file**

### GitHub Copilot CLI Integration

The system uses GitHub Copilot CLI commands for AI-powered analysis:

**For Error Explanation:**
```bash
gh copilot explain "<error message>"
```

**For Code Suggestions:**
```bash
gh copilot suggest -t shell "<prompt describing the fix needed>"
```

The system automatically:
- Installs the `github/gh-copilot` extension in workflows
- Truncates input to prevent terminal overflow (5000 char max)
- Parses Copilot output to extract code fixes
- Handles both code blocks and plain text responses

### Infinite Loop Prevention

To prevent continuous failing workflows, the system:

1. **Tracks Attempts**: Stores healing attempts in `.github/healing_attempts.json`
   ```json
   {
     "123": 1,  // Issue #123 has been attempted once
     "124": 3   // Issue #124 has reached maximum attempts
   }
   ```

2. **Enforces Limit**: Maximum 3 attempts per issue
   - Attempt 1: Initial auto-fix
   - Attempt 2: If first fix fails
   - Attempt 3: Final attempt
   - After 3: Manual intervention required

3. **Clear Messaging**: When limit is reached:
   ```
   ⚠️ Maximum healing attempts (3) reached for issue #124.
   Stopping to prevent infinite loop.
   Manual intervention required.
   ```

### Log Truncation

Large error logs are automatically truncated:

**For Feature Requests:**
```
You are a senior software developer. The user has requested a new 
feature or enhancement.

FEATURE REQUEST: {request}
CURRENT FILE CONTENT: {content}

Please implement the requested feature. Return ONLY the complete 
updated file content.
```

## Setup Instructions

### 1. Configure API Keys

Add the following secrets to your GitHub repository:

1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Add new repository secrets:
   - `GROQ_API_KEY`: Your Groq API key (required)
     - Get it from: https://console.groq.com/
   - `GOOGLE_API_KEY`: Your Google API key (optional, fallback)
     - Get it from: https://aistudio.google.com/apikey

### 2. Enable Workflows

All workflows are already configured and will activate automatically when:
- An issue is created with `jarvis-auto-report` label
- A workflow monitored by auto-heal fails

### 3. Test the System

#### Test with Jarvis API

The recommended way to trigger auto-fixes is through the Jarvis API:

1. Make a POST request to `/v1/jarvis/dispatch`:
```bash
curl -X POST "https://your-api-url/v1/jarvis/dispatch" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Fix authentication bug",
    "instruction": "Fix the NoneType error in app/auth.py line 15",
    "context": "Users cannot log in, getting NoneType error when accessing user object"
  }'
```

2. The API will trigger a `repository_dispatch` event
3. The workflow will create an issue with `auto-code` and `jarvis-api` labels
4. The auto-fixer will process the request and create a Pull Request
5. Monitor the workflow run in the Actions tab

**What happens:**
- ✅ Issue created automatically with context
- ✅ Pull Request created with the fix
- ✅ Original issue closed when PR is created
- ✅ If auto-fix fails, comment added to issue (NOT a new issue)

#### Test with a Manual Issue

1. Create a new issue with this content:
```
Error: NameError in file app/main.py line 42
The variable 'user_id' is not defined.

File "app/main.py", line 42, in process_user
  return user_id
NameError: name 'user_id' is not defined
```

2. Add the label: `jarvis-auto-report` or `auto-code`

3. Watch the Jarvis Self-Healing Workshop workflow run

4. A Pull Request will be created automatically

#### Test with a CI Failure

1. Create a failing test or introduce a bug
2. Push to main branch or create a PR
3. Wait for Python Tests to fail
4. CI Failure to Issue workflow will create an issue
5. Jarvis Self-Healing Workshop will attempt to fix it
6. A Pull Request will be created

## Usage Examples

### Example 1: Bug Fix from Jarvis API

**API Request:**
```json
POST /v1/jarvis/dispatch
{
  "intent": "Fix authentication bug",
  "instruction": "Fix the NoneType error in app/auth.py line 15",
  "context": "Users cannot log in due to NoneType error"
}
```

**Result:**
- Issue #123 created automatically with `auto-code` and `jarvis-api` labels
- Auto-fixer identifies `app/auth.py`
- GitHub Copilot analyzes and adds null check
- **Pull Request #124 created** with the fix (NOT another issue!)
- Issue #123 closed with comment linking to PR
- If auto-fix fails, comment added to issue #123 (NOT a new issue!)

### Example 2: Bug Fix from Issue

**Issue Created:**
```
Title: Bug in user authentication
Body: 
Error in app/auth.py line 15:
TypeError: 'NoneType' object is not subscriptable

File "app/auth.py", line 15, in authenticate
  return user['id']
TypeError: 'NoneType' object is not subscriptable
```

**Result:**
- Auto-fixer identifies `app/auth.py`
- LLM analyzes and adds null check
- **Pull Request created** with fix
- Issue closed automatically

### Example 3: Documentation Update

**Issue Created:**
```
Title: Add installation section to README
Body:
Please add a section about installation to README.md
Include pip install instructions and Python version requirements
```

**Result:**
- Auto-fixer identifies README.md
- LLM generates installation section
- **Pull Request created** with updated README
- Issue closed automatically

### Example 4: CI Failure Auto-Healing

**Scenario:**
- Python Tests workflow fails with import error
- CI Failure to Issue creates issue with logs
- Auto-fixer identifies missing package
- Updates requirements.txt
- **Pull Request created** with fix

## Configuration Options

### Environment Variables

The auto-fixer script supports these environment variables:

- `ISSUE_BODY`: The error message or request (required)
- `ISSUE_NUMBER`: The GitHub issue number (required)
- `ISSUE_ID`: Alternative to ISSUE_NUMBER for workflow runs
- `GROQ_API_KEY`: Groq API key for LLM access
- `GOOGLE_API_KEY` or `GEMINI_API_KEY`: Google API key
- `GROQ_MODEL`: Groq model to use (default: llama-3.3-70b-versatile)
- `GEMINI_MODEL`: Gemini model to use (default: gemini-1.5-flash)
- `GITHUB_TOKEN`: GitHub token for API access (auto-provided in workflows)

### Workflow Customization

You can customize which workflows to monitor in `ci-failure-to-issue.yml`:

```yaml
on:
  workflow_run:
    workflows: ["Python Tests", "Your Other Workflow"]
    types:
      - completed
```

## Limitations and Best Practices

### Current Limitations

1. **Single File Fixes**: Auto-fixer works on one file at a time
2. **LLM Accuracy**: AI-generated fixes may not always be perfect
3. **Complex Refactoring**: May struggle with architectural changes
4. **Test Generation**: Does not automatically create tests

### Best Practices

1. **Review PRs Carefully**: Always review auto-generated PRs before merging
2. **Clear Error Messages**: Provide detailed error logs in issues
3. **File Paths**: Include file paths in error reports when possible
4. **API Costs**: Monitor LLM API usage and costs
5. **Label Management**: Use `jarvis-auto-report` label selectively

### When to Use Manual Intervention

Auto-fixer is best for:
- ✅ Simple bug fixes
- ✅ Documentation updates
- ✅ Configuration changes
- ✅ Import errors
- ✅ Syntax errors

Use manual fixing for:
- ❌ Complex architectural changes
- ❌ Security vulnerabilities
- ❌ Performance optimizations
- ❌ Multi-file refactoring
- ❌ Database migrations

## Monitoring and Debugging

### Check Workflow Runs

View all workflow runs:
1. Go to **Actions** tab in GitHub
2. Select workflow name (Jarvis Self-Healing Workshop, Auto-Heal, etc.)
3. Check status and logs

### Debug Auto-Fixer

If auto-fixer fails, check:
1. **API Keys**: Verify GROQ_API_KEY or GOOGLE_API_KEY are set
2. **Logs**: Check workflow logs for error messages
3. **File Paths**: Ensure file mentioned in issue exists
4. **Permissions**: Verify workflow has correct permissions

### Common Issues

**"Could not extract or identify target file"**
- Solution: Include file path explicitly in issue body

**"Failed to get updated content from AI"**
- Solution: Check API key validity and API service status

**"Failed to create branch"**
- Solution: Check if branch already exists, may need manual cleanup

## Future Enhancements

Potential improvements to the system:

1. **Multi-file fixes**: Support changes across multiple files
2. **Test generation**: Automatically create tests for fixes
3. **Learning system**: Track successful fixes to improve prompts
4. **Retry mechanism**: Automatic retry with different strategies
5. **Human-in-the-loop**: Request human approval for certain changes
6. **Metrics dashboard**: Track auto-fix success rate

## Contributing

To improve the self-healing system:

1. Enhance `scripts/auto_fixer_logic.py` with better error detection
2. Add new file type support
3. Improve LLM prompts for better fixes
4. Add more sophisticated error parsing
5. Implement retry mechanisms

## License

This self-healing system is part of the Jarvis project and follows the same license.

## Support

For issues with the self-healing system:
1. Check this documentation
2. Review workflow logs
3. Create an issue (without `jarvis-auto-report` label for meta-issues)
4. Contact the maintainer

---

**Last Updated:** 2026-02-09
**Version:** 1.0
