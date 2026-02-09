# Jarvis Self-Healing Quick Reference

## 🚀 Quick Setup (2 minutes)

### 1. Prerequisites (Automatically Configured)

The self-healing system now uses **GitHub Copilot CLI** - no external API keys needed!

**Requirements:**
- GitHub repository with Actions enabled
- GitHub Copilot subscription (or trial)
- Workflows have `contents: write` and `pull-requests: write` permissions ✅

**GitHub Copilot CLI Extension:**
The workflows automatically install the `github/gh-copilot` extension - no manual setup required!

### 2. Enable Workflows

Workflows are already configured and active! They will trigger automatically when:
- A test workflow fails (auto-heal.yml)
- An issue is created with label `auto-code` (jarvis_code_fixer.yml)

### 3. Test the System

Create an issue with the label `auto-code`:

```
Title: Test Auto-Fix

Body:
Error in app/main.py line 10:
NameError: name 'undefined_var' is not defined
```

Watch Jarvis create a PR automatically using GitHub Copilot! 🎉

---

## 📋 How It Works

### Scenario 1: Manual Issue Report

```
User creates issue with 'auto-code' label → Copilot analyzes → Creates PR → Closes issue
```

### Scenario 2: CI Failure (Automatic)

```
CI fails → Issue created with 'auto-code' label → Copilot analyzes → Creates PR → Closes issue
```

### 🔒 Infinite Loop Prevention

The system tracks healing attempts and stops after **3 attempts** per issue to prevent infinite loops.
Tracking is stored in `.github/healing_attempts.json` (automatically managed).

---

## 🎯 Usage Examples

### Example 1: Bug Fix

```markdown
Title: Fix authentication error
Label: auto-code

Error in app/auth.py line 25:
TypeError: 'NoneType' object is not subscriptable

File "app/auth.py", line 25
  return user['id']
```

**Result:** Copilot adds null check and creates PR

### Example 2: Documentation Update

```markdown
Title: Add installation guide
Label: auto-code

Please add a section about installation to README.md
Include pip install instructions and Python version requirements
```

**Result:** Copilot generates installation section and creates PR

### Example 3: Feature Request

```markdown
Title: Add user validation
Label: auto-code

Please implement user input validation in app/forms.py
Check for empty strings and invalid email formats
```

**Result:** Copilot implements validation logic and creates PR

---

## 🔍 Monitoring

### Check Workflow Status

1. Go to **Actions** tab
2. Select workflow:
   - "Jarvis Self-Healing Workshop" (for issues)
   - "Auto-Heal CI Failures" (for CI failures)
   - "CI Failure to Issue" (monitors CI)
3. View logs and status

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "Could not extract file" | Include file path in issue body |
| "Copilot extension not installed" | Workflow auto-installs it - check logs for errors |
| "Failed to create PR" | Check workflow has write permissions |
| Workflow not triggering | Ensure `auto-code` label is added |
| "Maximum healing attempts reached" | System prevented infinite loop - manual fix needed |

---

## ⚙️ Advanced Configuration

### Monitor Additional Workflows

Edit `.github/workflows/auto-heal.yml`:

```yaml
on:
  workflow_run:
    workflows: ["Python Tests", "Build", "Deploy"]  # Add your workflows
    types:
      - completed
```

### Change Issue Label

Edit `.github/workflows/jarvis_code_fixer.yml`:

```yaml
if: contains(github.event.issue.labels.*.name, 'your-custom-label')
```

### Adjust Maximum Healing Attempts

Edit `scripts/auto_fixer_logic.py`:

```python
# Maximum number of auto-healing attempts to prevent infinite loops
MAX_HEALING_ATTEMPTS = 3  # Change this value
```

### Adjust Log Size Limit

Edit `scripts/auto_fixer_logic.py`:

```python
# Maximum log size to prevent terminal overflow (5000 characters)
MAX_LOG_SIZE = 5000  # Change this value
```

---

## 📊 System Capabilities

✅ **Supported Operations:**
- Fix Python bugs (syntax, runtime, imports)
- Update documentation files
- Modify configuration files
- Implement simple features
- Fix CI/CD failures
- **NEW:** Automatic infinite loop prevention
- **NEW:** Log truncation for large error outputs

❌ **Not Suitable For:**
- Complex architectural changes
- Multi-file refactoring
- Database migrations
- Security vulnerabilities (requires manual review)
- Issues exceeding 3 auto-fix attempts (manual intervention required)

---

## 🆘 Getting Help

1. **Review Documentation:** [JARVIS_SELF_HEALING_GUIDE.md](JARVIS_SELF_HEALING_GUIDE.md)
2. **Check Workflow Logs:** Actions → Select workflow → View logs
3. **Create Issue:** Use title "Help with Self-Healing" (without `auto-code` label)

---

## 🎓 Best Practices

1. ✅ **Always review** PRs before merging
2. ✅ **Include file paths** in error reports
3. ✅ **Use clear error messages** for better Copilot analysis
4. ✅ **Test in non-production** branches first
5. ✅ **Monitor healing attempts** - system stops after 3 tries
6. ✅ **Keep logs concise** - system truncates to 5000 chars
7. ✅ **Use 'auto-code' label** for issues you want auto-fixed

---

## 📈 Success Metrics

Track your auto-fix success:
- Number of issues auto-resolved
- Time saved on bug fixes
- PR creation rate
- Merge rate of auto-generated PRs
- Infinite loop prevention triggers (indicates complex issues)

---

## 🔐 Security Features

- **Infinite Loop Prevention:** Maximum 3 attempts per issue
- **Log Truncation:** Prevents terminal overflow with large logs (5000 char limit)
- **Duplicate Issue Detection:** Prevents creating duplicate issues for same failure
- **Permissions Control:** Workflows use least-privilege permissions
- **Native GitHub Integration:** No external API keys required

---

**Questions?** See full documentation: [JARVIS_SELF_HEALING_GUIDE.md](JARVIS_SELF_HEALING_GUIDE.md)
