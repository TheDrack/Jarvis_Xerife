# Auto-Fixer Logic Enhancements - Issue #88

## Overview
This document describes the enhancements made to `scripts/auto_fixer_logic.py` to address the failures in Issue #88 and expand the auto-fixer's capabilities beyond just bug fixes.

## Problem Statement
The auto-fixer script failed on Issue #88 for two main reasons:
1. It could only extract file paths from error tracebacks, not from general issue descriptions
2. Error messages when API keys were missing were unclear
3. It was designed only for bug fixes, not documentation updates

## Solution: Three Key Enhancements

### 1. File Flexibility 🎯

**Before:** The script only worked if a file path appeared in a traceback (e.g., `File "app/main.py"`).

**After:** The script now searches for common filenames mentioned anywhere in the issue body.

#### Features:
- **Case-insensitive matching**: 'readme', 'README', 'ReadMe.md' all map to `README.md`
- **Smart fallback**: First tries traceback extraction, then falls back to common filename detection
- **Extensive file support**: Recognizes documentation, dependencies, infrastructure, and config files

#### Supported Common Files:
```python
'readme' → 'README.md'
'readme.md' → 'README.md'
'requirements' → 'requirements.txt'
'requirements.txt' → 'requirements.txt'
'setup.py' → 'setup.py'
'dockerfile' → 'Dockerfile'
'docker-compose' → 'docker-compose.yml'
'makefile' → 'Makefile'
'gitignore' → '.gitignore'
'license' → 'LICENSE'
'contributing' → 'CONTRIBUTING.md'
```

#### Example:
```bash
# Issue mentions "update the readme"
# Auto-fixer detects "readme" → maps to README.md in repository
```

### 2. API Validation ✅

**Before:** Vague warning message: `No API keys found. Set GROQ_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY`

**After:** Clear, actionable error messages that explain the auto-fixer cannot proceed without AI.

#### New Error Message:
```
❌ CRITICAL: No AI API keys found!
   The auto-fixer cannot proceed without AI capabilities.
   Please set one of the following environment variables:
   - GROQ_API_KEY: For Groq API access
   - GOOGLE_API_KEY or GEMINI_API_KEY: For Gemini API access
   Without an API key, the auto-fixer cannot generate fixes.
```

#### Benefits:
- Users immediately understand **what** is wrong
- Clear instructions on **how** to fix it
- Explains **why** it's critical (can't proceed without AI)
- Shows at initialization and when attempting API calls

### 3. Context Handling for Documentation 📚

**Before:** The script only handled bug fixes from error tracebacks.

**After:** The script detects documentation update requests and provides appropriate context to the AI.

#### Features:
- **Request Detection**: Identifies documentation update keywords
- **Bilingual Support**: Supports both English and Portuguese
- **Smart Prompting**: Different AI prompts for bug fixes vs documentation updates

#### Supported Keywords:
**Portuguese:**
- adicionar uma seção
- adicionar seção
- atualizar readme
- atualizar documentação
- adicionar ao readme
- criar seção
- documentação

**English:**
- add a section
- add section
- update readme
- update documentation
- add to readme
- create section
- documentation

#### Example Workflow:
1. User creates issue: "Please add a section about testing to README.md"
2. Auto-fixer detects: "add a section" → documentation request
3. Auto-fixer finds: README.md (mentioned in issue)
4. Auto-fixer sends to AI:
   - Current README content
   - User's request
   - Documentation update prompt (not bug fix prompt)
5. AI generates: Updated README with testing section
6. Auto-fixer creates: Pull request with the update

## Technical Implementation

### New Methods

#### `extract_common_filename(issue_body: str) -> Optional[str]`
Searches the issue body for common file mentions and maps them to actual filenames.

#### `is_documentation_request(issue_body: str) -> bool`
Detects if the issue is requesting a documentation update based on keywords.

#### `_log_missing_api_keys_error()`
Centralized method for logging clear API key error messages.

### Modified Methods

#### `call_groq_api(error_message, code, is_doc_request=False)`
- Added `is_doc_request` parameter
- Different prompts for documentation vs bug fixes
- Clearer error messages

#### `call_gemini_api(error_message, code, is_doc_request=False)`
- Added `is_doc_request` parameter
- Different prompts for documentation vs bug fixes
- Clearer error messages

#### `get_fixed_code(error_message, code, is_doc_request=False)`
- Passes `is_doc_request` to API methods

#### `run()`
- Checks for API keys early and exits with clear error
- Detects documentation requests
- Falls back to common filename detection
- More informative logging

## Usage Examples

### Example 1: Bug Fix (Original Functionality)
```bash
export ISSUE_BODY="Error in File 'app/main.py', line 42: NameError"
export ISSUE_ID="123"
python scripts/auto_fixer_logic.py
```
→ Extracts file path from traceback → Fixes bug → Creates PR

### Example 2: Documentation Update (NEW!)
```bash
export ISSUE_BODY="Please add a section about installation to README.md"
export ISSUE_ID="124"
python scripts/auto_fixer_logic.py
```
→ Detects documentation request → Finds README.md → AI adds section → Creates PR

### Example 3: Case-Insensitive File Detection (NEW!)
```bash
export ISSUE_BODY="Update the readme with deployment instructions"
export ISSUE_ID="125"
python scripts/auto_fixer_logic.py
```
→ Detects 'readme' (lowercase) → Maps to README.md → AI updates → Creates PR

### Example 4: Portuguese Documentation Request (NEW!)
```bash
export ISSUE_BODY="Por favor, adicionar uma seção sobre testes ao README"
export ISSUE_ID="126"
python scripts/auto_fixer_logic.py
```
→ Detects Portuguese keywords → Finds README → AI adds section → Creates PR

## Testing

A comprehensive test suite was created that validates:

1. **Common Filename Detection**
   - Lowercase 'readme.md' → README.md ✓
   - 'requirements' mention → requirements.txt ✓
   - Uppercase 'README' → README.md ✓
   - No common file → None ✓

2. **Documentation Request Detection**
   - Portuguese "adicionar uma seção" → True ✓
   - English "add section" → True ✓
   - "update readme" → True ✓
   - Bug fix message → False ✓

3. **File Extraction with Fallback**
   - No traceback → Uses common filename ✓
   - Has traceback → Uses traceback ✓

4. **API Key Validation**
   - Missing keys → Clear error messages ✓
   - API calls without keys → Return None ✓

All tests pass successfully.

## Security

The changes were scanned with CodeQL and **no security alerts** were found.

## Benefits

✅ **Expanded Capabilities**: Jarvis can now update documentation, not just fix code bugs

✅ **Natural Language**: Users can request file updates in natural language without exact paths

✅ **Better UX**: Clear error messages when configuration is missing

✅ **Bilingual Support**: Works with both English and Portuguese requests

✅ **Backwards Compatible**: All original functionality still works

✅ **Tested**: Comprehensive test suite validates all new features

✅ **Secure**: No security vulnerabilities introduced

## Files Changed

1. `scripts/auto_fixer_logic.py` - Main implementation
2. Test suite in `tests/` directory

## Future Enhancements

Potential future improvements:
- Support for more languages (Spanish, French, etc.)
- More sophisticated file detection (fuzzy matching)
- Support for creating new files (not just updating existing ones)
- Integration with GitHub Issues API to extract file attachments
- Support for multi-file updates in a single PR

## Conclusion

These enhancements transform the auto-fixer from a bug-fixing tool into a comprehensive documentation and code maintenance assistant. The system is now capable of:

1. Understanding natural language requests
2. Working with documentation files
3. Providing clear feedback to users
4. Supporting multiple languages

This addresses all requirements from Issue #88 and enables Jarvis to be a more versatile assistant for repository maintenance.
