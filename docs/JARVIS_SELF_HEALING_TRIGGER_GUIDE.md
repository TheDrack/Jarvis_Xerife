# Jarvis Self-Healing Workflow - Trigger Guide

## Overview

The `jarvis_self_healing.yml` workflow is designed to be triggered **only** via the GitHub API using `repository_dispatch` events. This guide explains how to properly trigger the workflow and what to expect.

## Important: How NOT to Trigger

❌ **DO NOT** trigger this workflow by:
- Pushing commits to any branch
- Creating pull requests
- Manual workflow dispatch
- Any other GitHub event

If triggered incorrectly, the workflow will now:
1. Validate the trigger type
2. Display a clear error message
3. Provide instructions on how to trigger it correctly
4. Exit gracefully with detailed logs

## How to Trigger Correctly

### Using the GitHub CLI

```bash
gh api repos/TheDrack/python/dispatches \
  -f event_type=jarvis_order \
  -f client_payload[intent]=fix \
  -f client_payload[instruction]="Your instruction here" \
  -f client_payload[context]="Optional context" \
  -f client_payload[triggered_by]="manual"
```

### Using curl

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/TheDrack/python/dispatches \
  -d '{
    "event_type": "jarvis_order",
    "client_payload": {
      "intent": "fix",
      "instruction": "Fix the authentication bug in app/auth.py",
      "context": "Users are getting NoneType errors when logging in",
      "triggered_by": "jarvis-api"
    }
  }'
```

### Using Python

```python
import requests
import os

def trigger_jarvis_workflow(intent, instruction, context="", triggered_by="api"):
    """
    Trigger the Jarvis Self-Healing workflow via GitHub API
    
    Args:
        intent (str): Either "create" or "fix"
        instruction (str): Description of what to do
        context (str): Optional additional context
        triggered_by (str): Source that triggered this workflow
    """
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is required")
    
    url = "https://api.github.com/repos/TheDrack/python/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {
        "event_type": "jarvis_order",
        "client_payload": {
            "intent": intent,
            "instruction": instruction,
            "context": context,
            "triggered_by": triggered_by
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    print(f"✅ Workflow triggered successfully!")
    print(f"Intent: {intent}")
    print(f"Instruction: {instruction}")
    return response

# Example usage
if __name__ == "__main__":
    trigger_jarvis_workflow(
        intent="fix",
        instruction="Fix the database connection timeout in db/connection.py",
        context="Production servers are experiencing connection timeouts after 30 seconds",
        triggered_by="monitoring-alert"
    )
```

## Required Payload Fields

### `intent` (required)
- **Type**: string
- **Values**: `"create"` or `"fix"`
- **Description**: Specifies whether to create new code or fix existing code

### `instruction` (required)
- **Type**: string
- **Description**: Clear description of what needs to be done
- **Examples**:
  - `"Fix the NoneType error in user authentication"`
  - `"Add unit tests for the payment processing module"`
  - `"Update README with installation instructions"`

### `context` (optional)
- **Type**: string
- **Description**: Additional context to help with the task
- **Examples**:
  - `"Error occurs when user has no profile picture"`
  - `"Tests should cover edge cases for negative amounts"`

### `triggered_by` (optional)
- **Type**: string
- **Description**: Source that triggered this workflow
- **Examples**: `"jarvis-api"`, `"manual"`, `"monitoring-alert"`, `"ci-failure"`

## What Happens When Triggered

1. **Validation** (NEW) ✨
   - Workflow validates it was triggered correctly
   - Checks that all required payload fields are present
   - Provides clear error messages if validation fails

2. **Checkout & Setup**
   - Checks out the repository code
   - Sets up Python environment
   - Installs dependencies

3. **GitHub Copilot Integration**
   - Installs GitHub Copilot CLI
   - Processes the instruction
   - Generates code changes (placeholder implementation currently)

4. **Testing**
   - Auto-detects test framework
   - Runs tests with auto-fix retry logic
   - Attempts up to 3 times to fix test failures

5. **Pull Request Creation**
   - Creates a feature branch
   - Commits changes
   - Opens a PR with detailed description
   - Includes test results and workflow links

6. **Workflow Summary** (IMPROVED) ✨
   - Provides detailed summary of execution
   - Shows clear status indicators
   - Includes troubleshooting information if needed

## Troubleshooting

### Workflow fails immediately with "Workflow triggered incorrectly"

**Cause**: The workflow was not triggered via `repository_dispatch` event with type `jarvis_order`.

**Solution**: Use one of the trigger methods described above in the "How to Trigger Correctly" section.

### Workflow fails with "Missing required payload data"

**Cause**: The `client_payload` is missing the `intent` or `instruction` fields.

**Solution**: Ensure your API call includes both required fields:
```json
{
  "event_type": "jarvis_order",
  "client_payload": {
    "intent": "fix",        // Required
    "instruction": "...",   // Required
    "context": "...",       // Optional
    "triggered_by": "..."   // Optional
  }
}
```

### How to view detailed error logs

1. Go to the **Actions** tab in GitHub
2. Find the failed workflow run
3. Click on it to view the full logs
4. Check the **Workflow Summary** at the bottom for a clear error explanation

## Monitoring Workflow Runs

View all workflow runs:
```bash
gh run list --workflow=jarvis_self_healing.yml
```

View logs for a specific run:
```bash
gh run view RUN_ID --log
```

## Current Limitations

⚠️ **Note**: The current implementation uses a placeholder for code generation. It creates a marker file instead of actual code changes. Full integration with GitHub Copilot API or LLM is planned for future releases.

To see the full implementation roadmap, check:
- `JARVIS_SELF_HEALING_GUIDE.md` - Complete system documentation
- `JARVIS_AUTO_CODE_INTEGRATION.md` - Integration details

## Support

If you encounter issues:
1. Check the workflow logs in GitHub Actions
2. Review the Workflow Summary for detailed error information
3. Consult the main documentation in `JARVIS_SELF_HEALING_GUIDE.md`
4. Create an issue with the `bug` label (not `auto-code` or `jarvis-auto-report`)

---

**Last Updated**: 2026-02-09
**Workflow Version**: 2.0 (with validation and enhanced logging)
