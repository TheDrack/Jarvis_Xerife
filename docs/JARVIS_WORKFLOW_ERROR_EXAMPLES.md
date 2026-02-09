# Jarvis Self-Healing Workflow - Error Examples

This document shows examples of the improved error messages you'll see when the `jarvis_self_healing` workflow encounters issues.

## Example 1: Workflow Triggered Incorrectly (by push event)

### Before (Without Fix)
```
❌ Workflow failed
No logs available
No clear error message
```

### After (With Fix)
```
🔍 Validating Workflow Trigger
========================================
Event name: push
Event action:

❌ ERROR: Workflow triggered incorrectly!
Expected: repository_dispatch
Got: push

This workflow should ONLY be triggered via repository_dispatch with type 'jarvis_order'.
It appears to have been triggered by a push event.
```

**Workflow Summary:**
```markdown
## 🤖 Jarvis Self-Healing Workflow Summary

### ❌ Workflow Validation Failed

**Error:** Workflow triggered incorrectly. Expected repository_dispatch, got push

#### 📋 Trigger Information
- **Event:** push
- **Ref:** refs/heads/main
- **SHA:** 182ced6b19d968ebdf82ae58d7afaa7a0ee55d50

#### ✅ Expected Trigger
This workflow should be triggered via `repository_dispatch` event with:
```json
{
  "event_type": "jarvis_order",
  "client_payload": {
    "intent": "create" or "fix",
    "instruction": "description of what to do",
    "context": "optional additional context",
    "triggered_by": "optional trigger source"
  }
}
```

#### 📖 How to Trigger
Use the GitHub API to send a repository_dispatch event:
```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.github.com/repos/TheDrack/python/dispatches \
  -d '{"event_type":"jarvis_order","client_payload":{"intent":"fix","instruction":"Your instruction here"}}'
```
```

## Example 2: Missing Required Payload Fields

### Before (Without Fix)
```
❌ Workflow failed
Error: unbound variable
```

### After (With Fix)
```
🔍 Validating Workflow Trigger
========================================
Event name: repository_dispatch
Event action: jarvis_order

❌ ERROR: Missing required payload data!
Intent: ''
Instruction: ''

The repository_dispatch event must include client_payload with:
  - intent: 'create' or 'fix'
  - instruction: description of what to do
  - context: (optional) additional context
```

**Workflow Summary:**
```markdown
## 🤖 Jarvis Self-Healing Workflow Summary

### ❌ Workflow Validation Failed

**Error:** Missing required client_payload data (intent or instruction)

(Same helpful information about how to trigger correctly)
```

## Example 3: Successful Workflow Execution

### Enhanced Logging Throughout

**Step 1: Validation**
```
🔍 Validating Workflow Trigger
========================================
Event name: repository_dispatch
Event action: jarvis_order

✅ Workflow trigger validation passed
```

**Step 2: Extract Order**
```
📋 Extracting Jarvis Order
========================================
Intent: fix
Instruction: Fix authentication bug in app/auth.py
Context: Users getting NoneType errors
Triggered by: manual

✅ Order extracted successfully
```

**Step 3: Install Copilot**
```
📦 Installing GitHub Copilot CLI
========================================
gh version 2.40.1 (2024-01-15)
Installing GitHub Copilot CLI extension...
Verifying installation...

✅ GitHub Copilot CLI installed successfully
```

**Step 4: Create Branch**
```
🌿 Creating Feature Branch
========================================
Branch name: jarvis-auto-code-1707500000

✅ Branch created successfully
```

**Step 5: Apply Changes**
```
🤖 Applying Code Changes
========================================
Intent: fix
Prompt: Fix the following: Fix authentication bug in app/auth.py. Context: Users getting NoneType errors

📝 Processing fix request: Fix authentication bug in app/auth.py
✅ Created marker file: .jarvis_order_fix_12345.txt
⚠️ NOTE: This is a placeholder implementation. Actual code changes require integration with GitHub Copilot API or LLM.
```

**Step 6: Detect Tests**
```
🔍 Detecting Test Framework
========================================
✅ Test framework: pytest (found in requirements.txt)
```

**Step 7: Install Dependencies**
```
📦 Installing Test Dependencies
========================================
Installing requirements.txt...
Installing requirements/dev.txt...
Installing pytest and pytest-cov...

✅ Test dependencies installed successfully
```

**Step 8: Run Tests**
```
🧪 Running Tests with Auto-Fix Retry Logic
========================================
Starting tests with auto-fix retry logic (max 3 attempts)

=========================================
Test Attempt 1 of 3
=========================================
pytest tests/ -v
... (test output) ...

✅ Tests passed on attempt 1
```

**Step 9: Commit**
```
💾 Committing Changes
========================================
Commit message: 🤖 Jarvis Auto-Code: fix - Fix authentication bug in app/auth.py

✅ Changes committed successfully
```

**Step 10: Push**
```
⬆️ Pushing Branch
========================================
Branch: jarvis-auto-code-1707500000

✅ Branch pushed successfully
```

**Step 11: Create PR**
```
📝 Creating Pull Request
========================================
Creating PR with title: 🤖 Jarvis: fix - Fix authentication bug in app/auth.py

✅ Pull request created successfully
```

**Final Summary:**
```markdown
## 🤖 Jarvis Self-Healing Workflow Summary

### 📋 Request Details
- **Intent:** fix
- **Instruction:** Fix authentication bug in app/auth.py
- **Context:** Users getting NoneType errors

### ✅ Status: SUCCESS
Tests passed on first attempt, PR created successfully

---
**Workflow run:** https://github.com/TheDrack/python/actions/runs/12345
```

## Benefits of Enhanced Logging

### 1. **Immediate Problem Identification**
- Clear error messages appear at the top of logs
- Visual indicators (❌, ✅, ⚠️) make scanning easy
- Section headers help locate specific steps

### 2. **Actionable Error Messages**
- Errors include examples of correct usage
- Step-by-step instructions for fixing issues
- Links to relevant documentation

### 3. **Better Debugging**
- Each step logs what it's doing and the result
- Failed steps show why they failed
- Success indicators confirm each step completed

### 4. **Improved User Experience**
- Users know exactly what went wrong
- No more mysterious failures with no logs
- Clear guidance on how to proceed

## Common Issues and Their Error Messages

| Issue | Old Behavior | New Behavior |
|-------|-------------|--------------|
| Wrong trigger type | Silent failure | Clear error with trigger type and expected format |
| Missing payload | Unbound variable error | Specific error about which field is missing |
| No changes to commit | Unclear failure | Clear message "No changes to commit" |
| PR already exists | Generic error | Message listing existing PRs for the branch |
| Copilot not installed | Installation failure | Clear error about Copilot availability |

---

**Note**: These examples demonstrate the improvements made to the workflow's error handling and logging system. For complete usage instructions, see `JARVIS_SELF_HEALING_TRIGGER_GUIDE.md`.
