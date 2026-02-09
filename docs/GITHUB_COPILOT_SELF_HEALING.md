# GitHub Copilot Self-Healing Integration

## Overview

The Jarvis self-healing system now uses **GitHub Copilot CLI** for native GitHub ecosystem integration. This eliminates the need for external API keys and provides seamless AI-powered code fixes directly within GitHub Actions.

## Key Benefits

### ✅ No External Dependencies
- **No API keys required** - Uses your GitHub Copilot subscription
- **No external services** - Everything runs within GitHub
- **Native integration** - Fully compatible with GitHub Actions

### 🔒 Enhanced Security
- **Infinite loop prevention** - Maximum 3 auto-fix attempts per issue
- **Log truncation** - Prevents terminal overflow (5000 char limit)
- **Attempt tracking** - Stores state in `.github/healing_attempts.json`

### 🚀 Improved Performance
- **Faster analysis** - Direct GitHub CLI integration
- **Better context** - Copilot understands GitHub ecosystem
- **Smarter fixes** - Leverages Copilot's code understanding

## How It Works

### 1. Issue Creation

When you create an issue with the `auto-code` label:

```markdown
Title: Fix import error in auth module
Labels: auto-code

Body:
Error in app/auth.py line 15:
ModuleNotFoundError: No module named 'bcrypt'
```

### 2. GitHub Copilot Analysis

The workflow:
1. Installs `gh copilot` extension automatically
2. Uses `gh copilot explain` to understand the error:
   ```bash
   gh copilot explain "ModuleNotFoundError: No module named 'bcrypt'"
   ```
3. Uses `gh copilot suggest` to generate a fix:
   ```bash
   gh copilot suggest "Fix the missing bcrypt module in Python"
   ```

### 3. Automatic PR Creation

The system:
1. Applies the suggested fix to your code
2. Creates a branch: `fix/issue-{number}`
3. Commits the changes
4. Opens a PR with the fix
5. Closes the original issue

### 4. Infinite Loop Prevention

The system tracks healing attempts:

| Issue | Attempt 1 | Attempt 2 | Attempt 3 | Status |
|-------|-----------|-----------|-----------|--------|
| #123  | ✅ Fixed  | -         | -         | Resolved |
| #124  | ❌ Failed | ✅ Fixed  | -         | Resolved |
| #125  | ❌ Failed | ❌ Failed | ❌ Failed | Manual intervention needed |

After 3 failed attempts, the system stops to prevent infinite loops.

## Configuration

### Prerequisites

1. **GitHub Copilot Subscription**
   - Individual, Business, or Enterprise
   - Free trial available at https://github.com/features/copilot

2. **Workflow Permissions**
   The workflows are already configured with:
   ```yaml
   permissions:
     contents: write
     pull-requests: write
     issues: write
   ```

3. **GitHub CLI**
   Pre-installed on GitHub Actions runners - no setup needed!

### Installation

The system is **already configured** in your repository! No additional setup required.

## Usage

### Method 1: Manual Issue Creation

Create an issue with the `auto-code` label:

```markdown
Title: Add error handling to API endpoint
Labels: auto-code

Body:
Please add try-catch error handling to app/api/users.py
The endpoint currently crashes on invalid input.
```

### Method 2: CI Failure Auto-Fix

When your CI/CD pipeline fails:
1. `ci-failure-to-issue.yml` creates an issue automatically
2. Issue is labeled with `auto-code`
3. `jarvis_code_fixer.yml` triggers and fixes the issue
4. PR is created with the fix

### Method 3: Direct CI Auto-Heal

When `Python Tests` workflow fails:
1. `auto-heal.yml` triggers directly (no issue created)
2. Downloads error logs (truncated to 5000 chars)
3. Uses Copilot to analyze and fix
4. Creates PR with the fix

## GitHub Copilot CLI Commands

### Installing the Extension (Automatic)

Workflows install the extension automatically:
```bash
gh extension install github/gh-copilot
```

### Checking Installation

Verify Copilot CLI is installed:
```bash
gh copilot --version
```

### Explaining Errors

```bash
gh copilot explain "TypeError: 'NoneType' object is not subscriptable"
```

**Output:**
```
This error occurs when you try to access an element of a None value.
Common causes:
- Accessing a dictionary key when the dictionary is None
- Indexing a list that hasn't been initialized
...
```

### Suggesting Fixes

```bash
gh copilot suggest -t shell "How to install Python dependencies from requirements.txt"
```

**Output:**
```
Suggestion:
pip install -r requirements.txt

This command installs all packages listed in requirements.txt
...
```

## Security Features

### 1. Infinite Loop Prevention

**Problem:** Auto-fixing could create an infinite loop if the fix doesn't work.

**Solution:** Maximum 3 attempts per issue
- Tracked in `.github/healing_attempts.json`
- Automatically prevents further attempts after limit
- Clear error messages when limit is reached

**Example tracking file:**
```json
{
  "123": 1,
  "124": 3,
  "125": 2
}
```

### 2. Log Truncation

**Problem:** Large error logs can exceed terminal character limits.

**Solution:** Automatic truncation to 5000 characters
- Takes the **last** 5000 characters (most recent errors)
- Adds truncation notice to output
- Prevents workflow failures due to large logs

**Example:**
```python
def _truncate_log(self, log_text: str, max_size: int = 5000) -> str:
    if len(log_text) <= max_size:
        return log_text
    
    truncated = log_text[-max_size:]
    return f"[Log truncated - showing last {max_size} characters]\n...\n{truncated}"
```

### 3. Duplicate Issue Prevention

**Problem:** Multiple CI failures could create duplicate issues.

**Solution:** Smart duplicate detection
- Checks for existing issues (same workflow, same branch)
- Adds comment to existing issue instead of creating new one
- Prevents issue spam

## Troubleshooting

### "Copilot extension not installed"

**Cause:** Extension installation failed in workflow.

**Solution:** Check workflow logs for:
```
Failed to install GitHub Copilot CLI extension
This might be due to permissions or network issues
```

Verify your GitHub Copilot subscription is active.

### "Maximum healing attempts reached"

**Cause:** Issue has been auto-fixed 3 times without success.

**Solution:** Manual intervention required:
1. Review the 3 previous PRs created for this issue
2. Identify why the fixes didn't work
3. Create a manual fix
4. The tracking will reset after issue is closed

### "Could not extract file"

**Cause:** System couldn't identify which file to fix.

**Solution:** Include the file path in your issue:
```markdown
Error in app/main.py line 42:
NameError: name 'undefined_var' is not defined
```

### "Failed to create PR"

**Cause:** Workflow lacks necessary permissions.

**Solution:** Verify permissions in workflow file:
```yaml
permissions:
  contents: write
  pull-requests: write
```

## Advanced Configuration

### Changing Maximum Attempts

Edit `scripts/auto_fixer_logic.py`:
```python
# Maximum number of auto-healing attempts to prevent infinite loops
MAX_HEALING_ATTEMPTS = 3  # Change this value (default: 3)
```

### Changing Log Size Limit

Edit `scripts/auto_fixer_logic.py`:
```python
# Maximum log size to prevent terminal overflow (5000 characters)
MAX_LOG_SIZE = 5000  # Change this value (default: 5000)
```

### Monitoring Additional Workflows

Edit `.github/workflows/auto-heal.yml`:
```yaml
on:
  workflow_run:
    workflows: ["Python Tests", "Build", "Deploy", "Lint"]  # Add workflows here
    types:
      - completed
```

### Custom Issue Labels

Edit `.github/workflows/jarvis_code_fixer.yml`:
```yaml
if: contains(github.event.issue.labels.*.name, 'auto-code') || contains(github.event.issue.labels.*.name, 'auto-fix')
```

## Migration from External APIs

If you were using the old system with Groq/Gemini APIs:

### What Changed
- ❌ No longer need `GROQ_API_KEY` secret
- ❌ No longer need `GOOGLE_API_KEY` secret
- ❌ No longer install `groq` or `google-genai` packages
- ✅ Now use GitHub Copilot CLI (`gh copilot`)
- ✅ Native GitHub integration
- ✅ Better security with loop prevention

### What Stayed the Same
- Issue label system (now `auto-code` instead of `jarvis-auto-report`)
- PR creation workflow
- File detection logic
- Git operations

### Migration Steps
1. ✅ Update workflows (already done in this PR)
2. ✅ Update auto-fixer script (already done in this PR)
3. ✅ Add infinite loop prevention (already done in this PR)
4. ❌ Remove old API keys from secrets (optional - they're just ignored)

## Best Practices

### 1. Always Review PRs
Auto-generated PRs should be reviewed before merging:
- Check the changes make sense
- Verify tests pass
- Ensure no unintended side effects

### 2. Include File Paths
Help the system identify files to fix:
```markdown
❌ Bad: "There's an import error"
✅ Good: "Import error in app/auth.py line 15"
```

### 3. Be Specific
Provide clear, specific descriptions:
```markdown
❌ Bad: "The API doesn't work"
✅ Good: "API returns 500 error when user_id is None"
```

### 4. Monitor Attempt Counts
If an issue hits 3 attempts:
- Review what went wrong
- Consider if the issue is too complex for auto-fixing
- Fix manually if needed

### 5. Test in Non-Production
- Test auto-healing in development branches first
- Review multiple PRs before enabling on main
- Monitor success rates

## FAQ

**Q: Do I need a GitHub Copilot subscription?**
A: Yes, either Individual, Business, or Enterprise. Free trial available.

**Q: Will this work without GitHub Copilot?**
A: No, the system requires the `gh copilot` CLI extension.

**Q: What happens if Copilot gives a bad fix?**
A: Review the PR before merging. After 3 failed attempts, the system stops.

**Q: Can I use both old API system and new Copilot system?**
A: No, the new system replaces the old one completely.

**Q: How do I reset the attempt counter for an issue?**
A: Close the issue. The tracking resets when issues are closed.

**Q: Can I customize the Copilot prompts?**
A: Yes, edit the `get_fixed_code_with_copilot()` function in `auto_fixer_logic.py`.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review workflow logs in Actions tab
3. Create an issue (without `auto-code` label to avoid triggering auto-fix)
4. See [JARVIS_SELF_HEALING_GUIDE.md](../JARVIS_SELF_HEALING_GUIDE.md) for complete documentation

---

**Last Updated:** 2026-02-09
**System Version:** 2.0 (GitHub Copilot CLI Integration)
