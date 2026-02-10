# Jarvis Auto-Correction Protocol

## Overview

The Jarvis Auto-Correction Protocol enables autonomous self-healing without manual intervention. When Jarvis detects an error or receives an improvement request, it creates a Pull Request with an autonomous instruction file, triggering the Jarvis Autonomous State Machine workflow.

## Architecture

```
┌─────────────────────┐
│  Error Detected or  │
│ Improvement Request │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│  GitHubAdapter.report_for_auto_correction()     │
│                                                  │
│  1. Create auto-fix/{timestamp}-{random} branch │
│  2. Create autonomous_instruction.json at root  │
│  3. Commit changes                              │
│  4. Open Pull Request to main                   │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│  GitHub Pull Request Created                    │
│  - Title: 🤖 Auto-fix: {description}            │
│  - Body: Contains "Jarvis Autonomous State      │
│          Machine" keyword                       │
│  - Branch: auto-fix/{timestamp}-{random}        │
│  - File: autonomous_instruction.json            │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│  Jarvis Autonomous State Machine Workflow       │
│  (.github/workflows/jarvis_code_fixer.yml)      │
│                                                  │
│  - Triggered by pull_request event              │
│  - Checks for autonomous_instruction.json       │
│  - If found, reads instruction and runs         │
│    auto-fixer immediately (no test run)         │
│  - Applies corrections using GitHub Copilot     │
│  - Auto-commits fixes                           │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│  Outcome:                                        │
│  ✅ SUCCESS: Tests pass, PR ready for merge     │
│  ⚠️  NEEDS_HUMAN: Manual intervention required  │
│  ❌ FAILED_LIMIT: Max attempts reached          │
└─────────────────────────────────────────────────┘
```

## Usage

### Basic Example

```python
from app.adapters.infrastructure.github_adapter import GitHubAdapter

# Initialize adapter (uses GITHUB_TOKEN from environment)
adapter = GitHubAdapter()

# Report an error for auto-correction
result = await adapter.report_for_auto_correction(
    title="Fix HUD text duplication",
    description="Duplicate text appears in the HUD display",
    error_log="DuplicateTextError: Text rendered twice at line 42",
)

if result["success"]:
    print(f"✅ Auto-correction PR created: {result['pr_url']}")
    print(f"   PR #{result['pr_number']}")
    print(f"   Branch: {result['branch']}")
else:
    print(f"❌ Failed: {result['error']}")
```

### With Improvement Context

```python
result = await adapter.report_for_auto_correction(
    title="Optimize database queries",
    description="Multiple N+1 query issues detected in user profile loading",
    improvement_context="Consider using select_related() and prefetch_related()",
)
```

### Response Format

```python
{
    "success": True,
    "pr_number": 123,
    "pr_url": "https://github.com/owner/repo/pull/123",
    "branch": "auto-fix/20260210-143045-123456-a7b2",
    "message": "Auto-correction PR created - Jarvis Autonomous State Machine will process it"
}
```

## Autonomous Instruction File Format

The `autonomous_instruction.json` file created at the repository root contains:

```json
{
  "title": "Fix HUD text duplication",
  "description": "Duplicate text appears in the HUD display",
  "error_log": "DuplicateTextError: Text rendered twice at line 42",
  "improvement_context": "Ensure text is only rendered once per frame",
  "created_at": "2026-02-10T14:30:45.123456",
  "triggered_by": "jarvis_self_correction"
}
```

## When to Use

### ✅ Use `report_for_auto_correction()` for:

- **Automatic Error Detection**: When Jarvis detects an error in runtime
- **Code Quality Issues**: Linting errors, type errors, test failures
- **Performance Problems**: Slow queries, memory leaks
- **Improvement Suggestions**: Refactoring opportunities, code smells
- **Self-Healing Scenarios**: Any scenario where autonomous correction is desired

### ❌ Do NOT use for:

- **User-Reported Issues**: Use `create_issue()` for user bug reports
- **Feature Requests**: Use `create_issue()` for new feature suggestions
- **Infrastructure Issues**: Problems that require manual investigation
- **Security Vulnerabilities**: Require careful manual review

## Differences from `create_issue()`

| Feature | `create_issue()` | `report_for_auto_correction()` |
|---------|------------------|--------------------------------|
| Output | GitHub Issue | GitHub Pull Request |
| Workflow Triggered | Manual intervention required | Jarvis Autonomous State Machine |
| Autonomous Fix | No | Yes (automatic) |
| File Created | None | `autonomous_instruction.json` |
| Branch Created | No | Yes (`auto-fix/{timestamp}`) |
| Use Case | User reports, features | Self-healing, auto-fixes |

## Workflow Integration

The Pull Request created by `report_for_auto_correction()` automatically triggers the **Jarvis Autonomous State Machine** workflow (`jarvis_code_fixer.yml`), which:

1. **Checks out the code** from the auto-fix branch
2. **Sets up Python environment** and dependencies
3. **Reads `autonomous_instruction.json`** to understand the issue
4. **Uses GitHub Copilot** to apply corrections
5. **Runs tests** to validate the fix
6. **Auto-commits improvements** if tests pass
7. **Requests human review** if fixes fail after 3 attempts

## Best Practices

### 1. Provide Clear Descriptions

```python
# ❌ Bad - Too vague
await adapter.report_for_auto_correction(
    title="Fix bug",
    description="Something is broken",
)

# ✅ Good - Specific and actionable
await adapter.report_for_auto_correction(
    title="Fix IndexError in user_service.get_profile()",
    description="IndexError occurs when accessing user.preferences[0] without checking list length",
    error_log="IndexError: list index out of range\n  File 'user_service.py', line 42",
)
```

### 2. Include Error Context

```python
# ✅ Include full error traceback
result = await adapter.report_for_auto_correction(
    title="Fix KeyError in payment processor",
    description="KeyError when accessing 'amount' in payment data",
    error_log=traceback.format_exc(),  # Full traceback
)
```

### 3. Add Improvement Context

```python
# ✅ Provide guidance for improvements
result = await adapter.report_for_auto_correction(
    title="Optimize slow API endpoint",
    description="GET /api/users takes 5+ seconds with 1000+ users",
    improvement_context="Add pagination, limit to 50 users per page. Consider caching user list.",
)
```

## Monitoring

After creating an auto-correction PR:

1. **View PR**: Navigate to the PR URL returned in the response
2. **Check Workflow**: Go to Actions tab → "Jarvis Autonomous State Machine"
3. **Review Changes**: Examine the commits made by the workflow
4. **Validate Tests**: Check if tests passed or failed
5. **Merge or Iterate**: Merge if successful, or review if human intervention needed

## Environment Variables

```bash
# Required for auto-correction
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"  # GitHub Personal Access Token

# Repository info (optional, auto-detected from git)
export GITHUB_REPOSITORY="owner/repo"
export GITHUB_REPOSITORY_OWNER="owner"
export GITHUB_REPOSITORY_NAME="repo"
```

## Error Handling

```python
try:
    result = await adapter.report_for_auto_correction(
        title="Fix critical bug",
        description="Application crashes on startup",
    )
    
    if not result["success"]:
        # Log error and fallback to manual issue creation
        logger.error(f"Auto-correction failed: {result['error']}")
        
        # Fallback: Create manual issue
        fallback = await adapter.create_issue(
            title="[AUTO-CORRECTION FAILED] Fix critical bug",
            description="Application crashes on startup",
        )
        
except Exception as e:
    logger.error(f"Unexpected error in auto-correction: {e}")
    # Handle exception
```

## Testing

Run the test suite to validate the auto-correction functionality:

```bash
# Test auto-correction method
pytest tests/adapters/infrastructure/test_github_adapter.py::TestGitHubAdapter::test_report_for_auto_correction_success -v

# Run all GitHub adapter tests
pytest tests/adapters/infrastructure/test_github_adapter.py -v
```

## Conclusion

The Jarvis Auto-Correction Protocol enables truly autonomous self-healing by:

- ✅ Creating Pull Requests instead of Issues for auto-fixable problems
- ✅ Triggering the Jarvis Autonomous State Machine workflow
- ✅ Providing structured instructions via `autonomous_instruction.json`
- ✅ Enabling zero-touch error resolution
- ✅ Maintaining human oversight through PR review process

This closes the self-healing cycle without manual intervention, while still providing transparency and control through the PR process.
