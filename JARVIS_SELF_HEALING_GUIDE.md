# Jarvis Self-Healing System - Complete Guide

## Overview

The Jarvis Self-Healing System is an automated issue resolution framework that uses AI (LLMs) to detect, analyze, and fix errors in your repository. It operates on two main triggers:

1. **Issue-based Resolution**: When GitHub Issues are created with error reports
2. **CI/CD Failure Resolution**: When GitHub Actions workflows fail

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Repository                         │
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                │
│  │ GitHub       │         │ GitHub       │                │
│  │ Issues       │         │ Actions      │                │
│  │              │         │ (CI/CD)      │                │
│  └──────┬───────┘         └──────┬───────┘                │
│         │                        │                         │
│         │ Issue Created          │ Workflow Failed         │
│         │                        │                         │
│         ▼                        ▼                         │
│  ┌──────────────────────────────────────────┐             │
│  │   Jarvis Self-Healing Workshop           │             │
│  │   (jarvis_code_fixer.yml)                │             │
│  └──────────────┬───────────────────────────┘             │
│                 │                                          │
│                 │                                          │
│         ┌───────┴────────┐                                │
│         │                │                                 │
│         ▼                ▼                                 │
│  ┌─────────────┐  ┌─────────────┐                        │
│  │ Auto-Heal   │  │ CI Failure  │                        │
│  │ Workflow    │  │ to Issue    │                        │
│  │ (CI Fixes)  │  │ (Monitor)   │                        │
│  └─────┬───────┘  └─────┬───────┘                        │
│        │                 │                                 │
│        │                 └─────────┐                       │
│        │                           │                       │
│        └──────────┬────────────────┘                       │
│                   │                                        │
│                   ▼                                        │
│        ┌────────────────────┐                             │
│        │ Auto-Fixer Logic   │                             │
│        │ (AI-Powered)       │                             │
│        │  • Groq API        │                             │
│        │  • Gemini API      │                             │
│        └────────┬───────────┘                             │
│                 │                                          │
│                 ▼                                          │
│        ┌────────────────────┐                             │
│        │ Pull Request       │                             │
│        │ Created            │                             │
│        └────────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

## Workflows

### 1. Jarvis Self-Healing Workshop (`jarvis_code_fixer.yml`)

**Trigger:** When a GitHub Issue is created with the label `jarvis-auto-report`

**Process:**
1. Detects new issues with the `jarvis-auto-report` label
2. Reads the issue body containing error information
3. Passes the error to the auto-fixer script
4. Auto-fixer uses LLM to analyze and generate fix
5. Creates a Pull Request with the proposed fix
6. Closes the original issue

**Configuration Required:**
- `GROQ_API_KEY` secret (for Groq LLM API)
- `GOOGLE_API_KEY` secret (for Google Gemini API, optional fallback)

### 2. Auto-Heal CI Failures (`auto-heal.yml`)

**Trigger:** When the "Python Tests" workflow completes with a failure

**Process:**
1. Detects when Python Tests workflow fails
2. Downloads the error logs from the failed workflow
3. Passes logs to auto-fixer script as if they were an issue
4. Auto-fixer analyzes logs using LLM
5. Generates and applies fix
6. Creates a Pull Request with the fix

**Configuration Required:**
- `GROQ_API_KEY` secret (for Groq LLM API)
- `GOOGLE_API_KEY` secret (for Google Gemini API, optional fallback)

### 3. CI Failure to Issue (`ci-failure-to-issue.yml`)

**Trigger:** When the "Python Tests" workflow completes with a failure

**Process:**
1. Detects when Python Tests workflow fails
2. Extracts error logs from the failed run
3. Creates a GitHub Issue with:
   - Workflow name and run ID
   - Branch and commit SHA
   - Error logs
   - Automatic `jarvis-auto-report` label
4. This issue then triggers the Jarvis Self-Healing Workshop

**Smart Features:**
- Checks for duplicate issues (same workflow, same branch)
- If duplicate exists, adds a comment instead of creating new issue
- Includes direct link to failed workflow run

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

3. **AI-Powered Analysis**
   - Uses Groq API (llama-3.3-70b-versatile) as primary LLM
   - Falls back to Google Gemini (gemini-1.5-flash) if Groq unavailable
   - Generates contextual prompts based on error type

4. **Git Operations**
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

### LLM Prompt Generation

The system generates specialized prompts based on the request type:

**For Bug Fixes:**
```
You are a code fixing assistant. Analyze the following error and code, 
then return ONLY the corrected code without any explanations.

ERROR: {error_message}
CURRENT CODE: {code}

Return ONLY the corrected code, nothing else.
```

**For Documentation Updates:**
```
You are a documentation assistant. The user has requested an update 
to a documentation file.

USER REQUEST: {request}
CURRENT FILE CONTENT: {content}

Please update the file according to the user's request. Return ONLY 
the complete updated file content.
```

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

#### Test with a Manual Issue

1. Create a new issue with this content:
```
Error: NameError in file app/main.py line 42
The variable 'user_id' is not defined.

File "app/main.py", line 42, in process_user
  return user_id
NameError: name 'user_id' is not defined
```

2. Add the label: `jarvis-auto-report`

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

### Example 1: Bug Fix from Issue

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
- PR created with fix
- Issue closed automatically

### Example 2: Documentation Update

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
- PR created with updated README
- Issue closed automatically

### Example 3: CI Failure Auto-Healing

**Scenario:**
- Python Tests workflow fails with import error
- CI Failure to Issue creates issue with logs
- Auto-fixer identifies missing package
- Updates requirements.txt
- PR created with fix

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

You can customize which workflows to monitor in `auto-heal.yml`:

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
