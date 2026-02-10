# Jarvis Self-Healing and Auto-Code Integration

This document describes the integration between Jarvis API and GitHub Actions for automated code creation, fixes, and self-healing workflows.

## Overview

The Jarvis Self-Healing system enables automatic code generation and fixes through a seamless integration between:

1. **Jarvis API** - Receives intent (create/fix) and instructions
2. **GitHub Actions** - Executes automated workflows with quality checks and auto-fix retry logic
3. **GitHub Copilot** - Provides native intelligence for code changes
4. **Automated Testing** - Quality barrier with up to 3 auto-fix attempts
5. **Pull Request Creation** - Always creates PR (success or needs review status)

## Architecture

```
┌─────────────┐       ┌──────────────────────┐       ┌────────────────────┐
│             │       │                      │       │                    │
│  Jarvis API │──────▶│  GitHub Actions      │──────▶│  Pull Request      │
│             │       │  (Self-Healing)      │       │  (Always Created)  │
└─────────────┘       └──────────────────────┘       └────────────────────┘
      │                        │                               │
      │                        │                               │
      ▼                        ▼                               ▼
┌─────────────┐       ┌──────────────────────┐       ┌────────────────────┐
│  Validates  │       │  Applies Changes     │       │  ✅ Tests Passed   │
│  Intent &   │       │  Runs Tests          │       │  OR                │
│  Instruction│       │  Auto-Fix (max 3x)   │       │  ⚠️ Needs Review   │
└─────────────┘       └──────────────────────┘       └────────────────────┘
                               │
                               │
                               ▼
                      ┌──────────────────────┐
                      │  Test Failed?        │
                      │  Attempt < 3?        │
                      │  → Analyze & Fix     │
                      │  → Retry Tests       │
                      └──────────────────────┘
```

## Components

### 1. API Endpoint: `/v1/jarvis/dispatch`

**Purpose**: Trigger repository_dispatch events to GitHub Actions

**Authentication**: Requires Bearer token authentication

**Request Model**:
```json
{
  "intent": "create",  // or "fix"
  "instruction": "Add logging to all API endpoints",
  "context": "Use structured logging with timestamps"  // optional
}
```

**Response Model**:
```json
{
  "success": true,
  "message": "Repository dispatch event 'jarvis_order' triggered successfully",
  "workflow_url": "https://github.com/user/repo/actions"
}
```

**Environment Requirements**:
- `GITHUB_PAT`: Personal Access Token with `repo` permissions for triggering workflows

### 2. GitHub Actions Workflow: `jarvis_self_healing.yml`

**Trigger**: `repository_dispatch` event with type `jarvis_order`

**Workflow Steps**:

1. **Checkout Code** - Fetches repository with full history
2. **Configure Git** - Sets up bot user for commits
3. **Extract Order** - Reads intent, instruction, and context from payload
4. **Setup Python** - Installs Python 3.11 with pip caching
5. **Cache Dependencies** - Caches pip/uv packages for faster runs
6. **Install GitHub Copilot CLI** - Sets up gh copilot extension
7. **Create Feature Branch** - Creates timestamped branch for changes
8. **Apply Changes** - Uses Copilot to generate and apply code changes
9. **Detect Tests** - Auto-detects pytest, npm test, or make test
10. **Install Dependencies** - Installs project and test dependencies
11. **Run Tests with Auto-Fix Retry** - Executes tests with up to 3 auto-fix attempts:
    - Attempt 1: Run tests
    - If failed → Analyze failures, apply fixes, retry
    - Attempt 2: Run tests again
    - If failed → Analyze failures, apply fixes, retry
    - Attempt 3: Run tests final time
12. **Commit & Push** - Always commits changes (success or needs review)
13. **Create PR** - Always creates PR with appropriate status:
    - ✅ "Tests passed" if successful
    - ⚠️ "Needs Review" if tests still failing after 3 attempts

**Key Features**:

- **Auto-Fix Retry Logic**: Up to 3 attempts to fix test failures automatically
  ```yaml
  MAX_RETRIES=3
  # Try to fix and retest automatically
  ```

- **Dependency Caching**: Speeds up workflow by caching Python packages
  ```yaml
  cache: 'pip'  # Automatic pip caching
  ```

- **Smart Test Detection**: Automatically finds and runs tests
  ```bash
  # Checks for: pytest.ini, package.json, Makefile
  # Searches requirements files for pytest
  ```

- **Always Creates PR**: Never discards changes - always creates PR for review
  ```yaml
  # If tests pass: Create PR with success status
  # If tests fail after 3 attempts: Create PR with "Needs Review" status
  ```

- **Test Failure Logs**: Captures test output for each attempt
  ```bash
  # Saved as test_output_attempt_1.log, test_output_attempt_2.log, etc.
  ```

- **Dynamic Branch**: Uses repository's default branch
  ```yaml
  --base "${{ github.event.repository.default_branch }}"
  ```

### 3. GitHubWorker Service

**Method**: `trigger_repository_dispatch()`

**Purpose**: Send repository_dispatch events to GitHub API

**Parameters**:
- `event_type` (str): Type of event (e.g., "jarvis_order")
- `client_payload` (dict): Data to send to workflow
- `github_token` (str, optional): GitHub PAT (defaults to env GITHUB_PAT)

**Returns**:
```python
{
    "success": True,
    "message": "Repository dispatch event triggered successfully",
    "workflow_url": "https://github.com/user/repo/actions",
    "event_type": "jarvis_order",
    "payload": {...}
}
```

## Usage Examples

### Example 1: Create New Feature

```bash
# Using curl
curl -X POST https://your-jarvis-api.com/v1/jarvis/dispatch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "create",
    "instruction": "Add user authentication endpoints",
    "context": "Use JWT tokens with 24h expiration"
  }'
```

```python
# Using Python requests
import requests

response = requests.post(
    "https://your-jarvis-api.com/v1/jarvis/dispatch",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "intent": "create",
        "instruction": "Add user authentication endpoints",
        "context": "Use JWT tokens with 24h expiration"
    }
)

print(response.json())
# Output: {"success": true, "workflow_url": "..."}
```

### Example 2: Fix Bug

```bash
curl -X POST https://your-jarvis-api.com/v1/jarvis/dispatch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "fix",
    "instruction": "Fix timeout issue in database connections",
    "context": "Connection pool is exhausting. Increase pool size to 20"
  }'
```

## Configuration

### Required Environment Variables

**Jarvis API** (render.yaml or .env):
```bash
GITHUB_PAT=ghp_your_personal_access_token_here
```

**GitHub Actions** (automatically available):
```yaml
GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### GitHub PAT Permissions

The `GITHUB_PAT` token requires:
- ✅ `repo` - Full control of private repositories
- ✅ `workflow` - Update GitHub Action workflows

### API Authentication

Get token from Jarvis API:
```bash
curl -X POST https://your-jarvis-api.com/token \
  -d "username=admin&password=admin123"

# Returns: {"access_token": "eyJ...", "token_type": "bearer"}
```

## Workflow Behavior

### Successful Flow (Tests Pass on First Attempt)
1. ✅ Jarvis receives request
2. ✅ API triggers repository_dispatch
3. ✅ Workflow applies changes
4. ✅ Tests pass on first attempt
5. ✅ PR created with "All tests passed" status
6. 👤 Human reviews PR
7. 🚀 Merge when approved

### Auto-Fix Flow (Tests Fail, But Fixed Within 3 Attempts)
1. ✅ Jarvis receives request
2. ✅ API triggers repository_dispatch
3. ✅ Workflow applies changes
4. ❌ Tests fail on attempt 1
5. 🔧 Auto-fix attempt 1 (analyze failures, apply fixes)
6. ❌ Tests fail on attempt 2
7. 🔧 Auto-fix attempt 2 (analyze failures, apply fixes)
8. ✅ Tests pass on attempt 3
9. ✅ PR created with "Tests passed after 2 auto-fix attempts" status
10. 👤 Human reviews PR
11. 🚀 Merge when approved

### Manual Review Flow (Tests Still Fail After 3 Attempts)
1. ✅ Jarvis receives request
2. ✅ API triggers repository_dispatch
3. ✅ Workflow applies changes
4. ❌ Tests fail on attempt 1
5. 🔧 Auto-fix attempt 1 (analyze failures, apply fixes)
6. ❌ Tests fail on attempt 2
7. 🔧 Auto-fix attempt 2 (analyze failures, apply fixes)
8. ❌ Tests fail on attempt 3
9. ⚠️ PR created with "Needs Review" status and test failure report
10. 👤 Human reviews PR and test logs
11. 🔧 Human applies manual fixes or provides additional context
12. 🔄 Re-trigger workflow or manually fix

**Key Points**:
- ✅ No changes are discarded - all attempts create a PR
- 🔧 Up to 3 automatic fix attempts before requesting human review
- 📊 Test failure logs are captured for each attempt
- ⚠️ PRs marked differently based on test status (success vs needs review)

## Testing

### Running Tests Locally

```bash
# Test GitHubWorker
pytest tests/application/test_github_worker.py::test_trigger_repository_dispatch_success -v

# Test API Endpoint
pytest tests/adapters/infrastructure/test_api_server.py::TestJarvisDispatchEndpoint -v

# Run all related tests
pytest tests/ -k "jarvis_dispatch or repository_dispatch" -v
```

### Test Coverage

- ✅ GitHubWorker.trigger_repository_dispatch()
  - Success case with valid token
  - Missing GITHUB_PAT
  - Repository info fetch failure
  - API call failure
  - Custom token usage

- ✅ /v1/jarvis/dispatch endpoint
  - Create intent success
  - Fix intent success
  - Invalid intent validation
  - Missing instruction validation
  - Authentication required
  - GitHub worker failure handling
  - Context payload verification

## Security Considerations

### Token Security
- ✅ GITHUB_PAT stored in environment variables (not in code)
- ✅ API requires authentication for dispatch endpoint
- ✅ Workflow uses GITHUB_TOKEN (scoped to repository)
- ✅ No secrets exposed in logs or PR descriptions

### Code Quality
- ✅ Automatic test execution before PR creation
- ✅ Failed tests prevent PR creation
- ✅ CodeQL security scanning (no vulnerabilities found)
- ✅ Input validation on API requests

### Audit Trail
- ✅ Workflow runs logged in GitHub Actions
- ✅ PR includes triggering user information
- ✅ All changes tracked in git history

## Troubleshooting

### Issue: Workflow Not Triggered

**Symptoms**: API returns success but no workflow runs

**Solutions**:
1. Check GITHUB_PAT has correct permissions
2. Verify workflow file is on default branch
3. Check repository_dispatch event type matches ("jarvis_order")

### Issue: Tests Always Fail

**Symptoms**: PR created with "Needs Review" status after 3 attempts

**Solutions**:
1. Review test failure logs in workflow run (test_output_attempt_*.log)
2. Check if failures are related to:
   - Missing test dependencies
   - Environment configuration issues
   - Actual code logic problems
3. If placeholder auto-fix is active, consider implementing real LLM integration
4. Apply manual fixes and re-trigger workflow

### Issue: Auto-Fix Not Working

**Symptoms**: Tests fail 3 times without improvements

**Solutions**:
1. Verify auto-fix logic is implemented (currently placeholder)
2. Check test output logs for actionable error messages
3. Ensure LLM/Copilot integration is configured if implemented
4. Review workflow logs for auto-fix attempt details

### Issue: Too Many Failed PRs

**Symptoms**: Multiple PRs with "Needs Review" status

**Solutions**:
1. Improve instruction clarity in Jarvis requests
2. Add more context to help auto-fix logic
3. Review test suite for flaky tests
4. Consider adjusting MAX_RETRIES if needed

### Issue: No Changes Applied

**Symptoms**: Workflow runs but no code changes

**Solutions**:
1. Review "Apply Code Changes" step in workflow logs
2. Verify instruction is clear and actionable
3. Check Copilot integration (placeholder vs actual implementation)

## Future Enhancements

### Planned Features

1. **GitHub Copilot API Integration**
   - Replace placeholder with actual Copilot API calls
   - Use copilot-chat for more complex instructions

2. **LLM Integration**
   - Support for GPT-4, Claude, or other LLMs
   - Fallback mechanism if Copilot unavailable

3. **Advanced Test Strategies**
   - Parallel test execution
   - Test impact analysis
   - Incremental testing

4. **Retry Logic**
   - Automatic retry with refined prompts
   - Learning from previous failures

5. **Metrics & Analytics**
   - Success rate tracking
   - Average fix time
   - Cost analysis

## Contributing

When extending this integration:

1. ✅ Add tests for new functionality
2. ✅ Update API documentation
3. ✅ Run security scans (codeql_checker)
4. ✅ Follow existing code patterns
5. ✅ Document configuration changes

## Support

For issues or questions:
- **GitHub Issues**: [Repository Issues](https://github.com/TheDrack/python/issues)
- **Documentation**: [JARVIS_SELF_HEALING_GUIDE.md](JARVIS_SELF_HEALING_GUIDE.md)
- **Workflow Examples**: `.github/workflows/jarvis_self_healing.yml`
