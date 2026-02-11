#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fixer Logic Script - GitHub Copilot Native Integration

This script is part of the self-healing system for Jarvis Assistant.
It reads errors from GitHub issues, uses GitHub Copilot CLI to generate fixes,
and automatically creates pull requests with the corrections.

IMPORTANT: This script uses GitHub's native Copilot CLI integration instead of external APIs.
When errors/issues come directly from GitHub Actions or GitHub Issues, they are processed
using 'gh copilot' commands for native GitHub ecosystem integration.

Features:
1. Reads error from ISSUE_BODY environment variable
2. Extracts affected file path from the error message or detects common files
3. Handles both code bug fixes and documentation updates
4. Uses GitHub Copilot CLI (gh copilot) for AI-powered analysis and suggestions
5. Receives corrected/updated content from Copilot
6. Applies the fix locally
7. Creates a Git branch fix/issue-{ID}
8. Commits the changes
9. Opens a Pull Request using GitHub CLI (gh pr create)
10. Closes the original issue using GitHub CLI (gh issue close)
11. Prevents infinite loops with run tracking and retry limits

Key Capabilities:
- Native GitHub Integration: Uses gh copilot extension for AI capabilities
- Log Handling: Truncates logs to prevent terminal character limit issues
- Infinite Loop Prevention: Tracks workflow runs and implements retry limits
- File Flexibility: If no file path in traceback, searches for common files
  (README.md, requirements.txt, etc.) in issue body with case-insensitive matching
- Keyword-Based Suggestions: If no file found, searches for keywords like 'interface',
  'api', or 'frontend' and suggests probable files (app/main.py, README.md, etc.)
- Context Handling: Detects documentation requests (e.g., "add a section") and
  provides current file content to AI instead of treating it as a bug

Usage:
    # For bug fixes (GitHub Actions direct):
    export ISSUE_BODY="Error: NameError in file app/main.py line 42..."
    export ISSUE_ID="123"
    python scripts/auto_fixer_logic.py
    
    # For documentation updates (GitHub Issues direct):
    export ISSUE_BODY="Please add a section about installation to README.md"
    export ISSUE_ID="124"
    python scripts/auto_fixer_logic.py
    
    # With keyword-based suggestion:
    export ISSUE_BODY="The interface needs improvement"
    export ISSUE_ID="125"
    python scripts/auto_fixer_logic.py
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

# Import the state machine
try:
    # Try relative import first (when run as module)
    from .state_machine import SelfHealingStateMachine, State
except ImportError:
    # Fall back to direct import (when run as script)
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from state_machine import SelfHealingStateMachine, State

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Maximum log size to prevent terminal overflow (5000 characters)
MAX_LOG_SIZE = 5000
# Maximum prompt size for code suggestions (allows more context)
MAX_PROMPT_SIZE = MAX_LOG_SIZE * 2  # 10000 characters
# Maximum size for error message in fix prompts
MAX_ERROR_SIZE_IN_FIX = 1000  # Keep error concise in fix prompts
# Minimum valid code length for sanity check
MIN_VALID_CODE_LENGTH = 50  # Code should be at least 50 chars to be valid
# Maximum number of auto-healing attempts to prevent infinite loops
MAX_HEALING_ATTEMPTS = 3


class AutoFixerError(Exception):
    """Base exception for auto-fixer errors"""
    pass


class AutoFixer:
    """
    Auto-Fixer for self-healing system.
    
    Uses GitHub Copilot CLI to analyze errors and generate code fixes.
    """
    
    # Prefixes that Copilot might use in output (may need updates based on CLI changes)
    COPILOT_OUTPUT_PREFIXES = ["Suggestion:", "Here's the fix:", "Fixed code:", "Solution:"]
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the auto-fixer
        
        Args:
            repo_path: Path to the git repository (defaults to current directory)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        
        # Validate gh CLI and Copilot extension are available
        self._check_gh_cli()
        self._check_gh_copilot_extension()
    
    def _check_gh_copilot_extension(self) -> bool:
        """Check if GitHub Copilot CLI extension is installed"""
        try:
            result = subprocess.run(
                ["gh", "copilot", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                logger.info("✓ GitHub Copilot CLI extension is installed")
                return True
            else:
                logger.error(
                    "✗ GitHub Copilot CLI extension not installed or not working.\n"
                    "   Install with: gh extension install github/gh-copilot\n"
                    "   The auto-fixer requires the Copilot extension to function."
                )
                return False
                
        except Exception as e:
            logger.error(f"Error checking gh copilot extension: {e}")
            logger.error("Install with: gh extension install github/gh-copilot")
            return False
    
    def _check_healing_attempt_limit(self, issue_id: str) -> bool:
        """
        Check if we've exceeded the maximum number of healing attempts for this issue
        to prevent infinite loops.
        
        Args:
            issue_id: The issue ID
            
        Returns:
            True if we can proceed, False if limit exceeded
        """
        tracking_file = self.repo_path / ".github" / "healing_attempts.json"
        
        try:
            # Load or create tracking data
            if tracking_file.exists():
                with open(tracking_file, 'r') as f:
                    attempts = json.load(f)
            else:
                attempts = {}
            
            # Get current attempt count
            current_attempts = attempts.get(str(issue_id), 0)
            
            if current_attempts >= MAX_HEALING_ATTEMPTS:
                logger.warning(
                    f"⚠️  Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for issue #{issue_id}.\n"
                    f"   Stopping to prevent infinite loop.\n"
                    f"   Manual intervention required."
                )
                return False
            
            # Increment attempt count
            attempts[str(issue_id)] = current_attempts + 1
            
            # Save tracking data
            tracking_file.parent.mkdir(parents=True, exist_ok=True)
            with open(tracking_file, 'w') as f:
                json.dump(attempts, f, indent=2)
            
            logger.info(f"✓ Healing attempt {current_attempts + 1}/{MAX_HEALING_ATTEMPTS} for issue #{issue_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Could not check healing attempt limit: {e}")
            # Allow to proceed if tracking fails (better than blocking legitimate fixes)
            return True
    
    def _truncate_log(self, log_text: str, max_size: int = MAX_LOG_SIZE) -> str:
        """
        Truncate log text to prevent terminal character limit issues.
        
        Args:
            log_text: The full log text
            max_size: Maximum size in characters
            
        Returns:
            Truncated log text
        """
        if len(log_text) <= max_size:
            return log_text
        
        # Take the last max_size characters (most recent errors are usually at the end)
        truncated = log_text[-max_size:]
        
        # Add a note about truncation
        return f"[Log truncated - showing last {max_size} characters]\n...\n{truncated}"
    
    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize prompt text for gh copilot CLI commands.
        Removes problematic characters that could break shell commands.
        
        Args:
            prompt: The raw prompt text
            
        Returns:
            Sanitized prompt safe for command line usage
        """
        # Replace newlines with spaces to create a single-line prompt
        sanitized = prompt.replace('\n', ' ').replace('\r', ' ')
        
        # Replace multiple spaces with single space (this also normalizes tabs)
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        # Remove control characters, keep only printable ASCII characters (32-126)
        # This removes Unicode to prevent shell issues in automation environments
        # ASCII 32 is space (first printable character), 127 is DEL (control character)
        # Trade-off: May strip non-English characters, but ensures reliable CLI execution
        sanitized = re.sub(r'[^\x20-\x7E]', '', sanitized)
        
        # Strip leading/trailing whitespace
        sanitized = sanitized.strip()
        
        return sanitized
    
    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is installed and authenticated"""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                logger.info("✓ GitHub CLI is authenticated")
                return True
            else:
                logger.warning("⚠ GitHub CLI is not authenticated. Run: gh auth login")
                return False
                
        except FileNotFoundError:
            logger.error("✗ GitHub CLI (gh) not installed. Install from: https://cli.github.com/")
            return False
        except Exception as e:
            logger.error(f"Error checking gh CLI: {e}")
            return False
    
    def is_documentation_request(self, issue_body: str) -> bool:
        """
        Detect if the issue is requesting a documentation update
        
        Args:
            issue_body: The issue body text
            
        Returns:
            True if this appears to be a documentation request, False otherwise
        """
        # Keywords that suggest documentation updates
        doc_keywords = [
            'adicionar uma seção',  # add a section (Portuguese)
            'adicionar seção',
            'add a section',
            'add section',
            'update readme',
            'atualizar readme',
            'update documentation',
            'atualizar documentação',
            'add to readme',
            'adicionar ao readme',
            'create section',
            'criar seção',
            'documentation',
            'documentação',
        ]
        
        issue_lower = issue_body.lower()
        
        for keyword in doc_keywords:
            if keyword in issue_lower:
                logger.info(f"Detected documentation request: '{keyword}' found in issue")
                return True
        
        return False
    
    def is_feature_request(self, issue_body: str) -> bool:
        """
        Detect if the issue is requesting a new feature
        
        Args:
            issue_body: The issue body text
            
        Returns:
            True if this appears to be a feature request, False otherwise
        """
        # Keywords that suggest feature requests (English and Portuguese)
        feature_keywords = [
            'implementar',  # implement (Portuguese)
            'implement',
            'adicionar',  # add (Portuguese)
            'add',
            'criar',  # create (Portuguese)
            'create',
            'new feature',
            'nova funcionalidade',
            'feature request',
            'solicitação de recurso',
            'enhance',
            'melhorar',  # improve (Portuguese)
            'improvement',
            'melhoria',  # improvement (Portuguese)
            'facilitar',  # facilitate/make easier (Portuguese)
            'facilitate',
        ]
        
        issue_lower = issue_body.lower()
        
        # Check if any feature keyword is present
        for keyword in feature_keywords:
            if keyword in issue_lower:
                logger.info(f"Detected feature request: '{keyword}' found in issue")
                return True
        
        return False
    
    def extract_common_filename(self, issue_body: str) -> Optional[str]:
        """
        Extract common file names from issue body when no traceback is found
        
        Args:
            issue_body: The issue body text
            
        Returns:
            File path if a common file is mentioned, None otherwise
        """
        # Common files to look for (case-insensitive)
        common_files = {
            'readme': 'README.md',
            'readme.md': 'README.md',
            'requirements': 'requirements.txt',
            'requirements.txt': 'requirements.txt',
            'setup.py': 'setup.py',
            'setup': 'setup.py',
            'dockerfile': 'Dockerfile',
            'docker-compose': 'docker-compose.yml',
            'docker-compose.yml': 'docker-compose.yml',
            'makefile': 'Makefile',
            '.gitignore': '.gitignore',
            'gitignore': '.gitignore',
            'license': 'LICENSE',
            'license.md': 'LICENSE',
            'contributing': 'CONTRIBUTING.md',
            'contributing.md': 'CONTRIBUTING.md',
        }
        
        # Convert issue body to lowercase for case-insensitive matching
        issue_lower = issue_body.lower()
        
        # Look for common file mentions
        for key, actual_filename in common_files.items():
            # Check if the file is mentioned in the issue
            if key in issue_lower:
                # Verify the file exists in the repository
                full_path = self.repo_path / actual_filename
                if full_path.exists():
                    logger.info(f"Found common file mentioned: {key} → {actual_filename}")
                    return actual_filename
        
        return None
    
    def suggest_file_by_keywords(self, issue_body: str) -> Optional[str]:
        """
        Suggest probable files based on keywords in the issue body
        
        Args:
            issue_body: The issue body text
            
        Returns:
            File path suggestion if keywords match, None otherwise
        """
        # First, check for specific phrase combinations for better context awareness
        # This handles cases where multiple keywords are present and we need to prioritize
        
        # Convert issue body to lowercase for case-insensitive matching
        issue_lower = issue_body.lower()
        
        # Check for issue creation/formatting context
        if ('issue' in issue_lower or 'issues' in issue_lower) and \
           any(word in issue_lower for word in ['escrita', 'format', 'estrutura', 'criação', 'creation', 'writing']):
            logger.info("Detected issue creation/formatting context")
            file_path = 'app/adapters/infrastructure/github_adapter.py'
            if (self.repo_path / file_path).exists():
                logger.info(f"Suggesting file for issue formatting: {file_path}")
                return file_path
        
        # Keyword to file mapping
        # Note: This mapping can be extended with more keywords and files as needed
        keyword_suggestions = {
            # GitHub Actions and workflow keywords - high priority
            'github actions': ['.github/workflows/jarvis_code_fixer.yml', '.github/workflows/ci-failure-to-issue.yml'],
            'workflow': ['.github/workflows/jarvis_code_fixer.yml', '.github/workflows/ci-failure-to-issue.yml'],
            # Issue-related keywords
            'issue': ['app/adapters/infrastructure/github_adapter.py', 'scripts/auto_fixer_logic.py'],
            'issues': ['app/adapters/infrastructure/github_adapter.py', 'scripts/auto_fixer_logic.py'],
            # Self-healing and auto-fixer keywords (English and Portuguese)
            'self-healing': ['scripts/auto_fixer_logic.py', 'app/adapters/infrastructure/github_adapter.py', '.github/workflows/jarvis_code_fixer.yml'],
            'self healing': ['scripts/auto_fixer_logic.py', 'app/adapters/infrastructure/github_adapter.py', '.github/workflows/jarvis_code_fixer.yml'],
            'auto-fixer': ['scripts/auto_fixer_logic.py', '.github/workflows/jarvis_code_fixer.yml'],
            'auto fixer': ['scripts/auto_fixer_logic.py', '.github/workflows/jarvis_code_fixer.yml'],
            'jarvis': ['app/application/services/assistant_service.py', 'app/adapters/infrastructure/github_adapter.py'],
            # API and interface keywords (English and Portuguese)
            'api': ['app/adapters/infrastructure/api_server.py', 'app/adapters/infrastructure/api_models.py', 'app/main.py', 'main.py'],
            'payload': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
            'mensagem': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],  # Portuguese for 'message'
            'envio': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],  # Portuguese for 'send/sending'
            'json': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
            # Interface keyword - prioritizes API files when combined with API-related terms
            'interface': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py', 'app/main.py', 'main.py'],
            'frontend': ['app/main.py', 'main.py', 'README.md'],
            # UI and HUD keywords (English and Portuguese)
            'hud': ['app/adapters/infrastructure/api_server.py'],
            'chat': ['app/adapters/infrastructure/api_server.py'],
            'botão': ['app/adapters/infrastructure/api_server.py'],  # Portuguese for 'button'
            'button': ['app/adapters/infrastructure/api_server.py'],
            'transcrição': ['app/adapters/infrastructure/api_server.py'],  # Portuguese for 'transcription'
            'transcription': ['app/adapters/infrastructure/api_server.py'],
            'voice': ['app/adapters/infrastructure/api_server.py'],
            'voz': ['app/adapters/infrastructure/api_server.py'],  # Portuguese for 'voice'
            'input': ['app/adapters/infrastructure/api_server.py'],
            # Documentation keywords
            'documentation': ['README.md', 'docs/README.md'],
            'documentação': ['README.md', 'docs/README.md'],  # Portuguese
            'readme': ['README.md'],
        }
        
        # Search for keywords and suggest files
        for keyword, file_suggestions in keyword_suggestions.items():
            if keyword in issue_lower:
                logger.info(f"Detected keyword '{keyword}' in issue body")
                
                # Try each suggested file in order
                for suggested_file in file_suggestions:
                    full_path = self.repo_path / suggested_file
                    if full_path.exists():
                        logger.info(f"Suggesting file based on keyword '{keyword}': {suggested_file}")
                        return suggested_file
        
        return None
    
    def extract_file_from_error(self, error_message: str) -> Optional[str]:
        """
        Extract the affected file path from an error message
        
        Args:
            error_message: The error message text
            
        Returns:
            File path if found, None otherwise
        """
        # Common patterns for file paths in error messages
        patterns = [
            r'File "([^"]+)"',  # Python traceback: File "path/to/file.py"
            r'in file ([^\s]+)',  # Generic: in file path/to/file.py
            r'at ([^\s:]+):',  # JavaScript/TypeScript: at path/to/file.js:
            r'([^\s]+\.py):\d+:',  # Python with line number: file.py:42:
            r'([^\s]+\.js):\d+:',  # JavaScript with line number: file.js:42:
            r'([^\s]+\.ts):\d+:',  # TypeScript with line number: file.ts:42:
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_message)
            if match:
                file_path = match.group(1)
                logger.info(f"Extracted file path from traceback: {file_path}")
                return file_path
        
        logger.warning("Could not extract file path from traceback")
        return None
    
    def read_file_content(self, file_path: str) -> Optional[str]:
        """
        Read content from a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content or None if file doesn't exist
        """
        try:
            full_path = self.repo_path / file_path
            
            if not full_path.exists():
                logger.error(f"File not found: {full_path}")
                return None
            
            content = full_path.read_text(encoding='utf-8')
            logger.info(f"Read {len(content)} characters from {file_path}")
            return content
            
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def call_gh_copilot_explain(self, error_message: str) -> Optional[str]:
        """
        Use GitHub Copilot CLI to explain an error
        
        Args:
            error_message: The error message to explain
            
        Returns:
            Explanation from Copilot or None if call fails
        """
        try:
            # Truncate error message to prevent terminal overflow
            truncated_error = self._truncate_log(error_message)
            
            # Sanitize the error message for command line usage
            sanitized_error = self._sanitize_prompt(truncated_error)
            
            # Use gh copilot explain command with -p flag for non-interactive mode
            # The -p flag allows the prompt to be passed as an argument, avoiding interactive
            # prompts and stdin requirements, which is essential for automation environments
            # Note: subprocess.run with list form safely handles arguments without shell interpretation
            result = subprocess.run(
                ["gh", "copilot", "explain", "-p", sanitized_error],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.repo_path,
            )
            
            if result.returncode == 0:
                explanation = result.stdout.strip()
                logger.info(f"✓ Received explanation from GitHub Copilot ({len(explanation)} chars)")
                return explanation
            else:
                logger.error(f"GitHub Copilot explain failed: {result.stderr}")
                return None
                    
        except Exception as e:
            logger.error(f"Error calling gh copilot explain: {e}")
            return None
    
    def call_gh_copilot_suggest(self, prompt: str) -> Optional[str]:
        """
        Use GitHub Copilot CLI to get code suggestions
        
        Args:
            prompt: The prompt describing what code is needed
            
        Returns:
            Suggested code from Copilot or None if call fails
        """
        try:
            # Truncate prompt to prevent terminal overflow (allows more context than logs)
            truncated_prompt = self._truncate_log(prompt, max_size=MAX_PROMPT_SIZE)
            
            # Sanitize the prompt for command line usage
            sanitized_prompt = self._sanitize_prompt(truncated_prompt)
            
            # Use gh copilot suggest command with -p flag for non-interactive mode
            # The -p flag allows the prompt to be passed as an argument, avoiding interactive
            # prompts and stdin requirements, which is essential for automation environments
            # Note: subprocess.run with list form safely handles arguments without shell interpretation
            result = subprocess.run(
                ["gh", "copilot", "suggest", "-t", "shell", "-p", sanitized_prompt],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.repo_path,
            )
            
            if result.returncode == 0:
                suggestion = result.stdout.strip()
                logger.info(f"✓ Received suggestion from GitHub Copilot ({len(suggestion)} chars)")
                return suggestion
            else:
                logger.error(f"GitHub Copilot suggest failed: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling gh copilot suggest: {e}")
            return None
    
    def get_fixed_code_with_copilot(self, error_message: str, code: str, file_path: str, is_doc_request: bool = False, is_feature: bool = False) -> Optional[str]:
        """
        Get fixed code using GitHub Copilot CLI
        
        Args:
            error_message: The error message or user request
            code: The current code with the error or current file content
            file_path: The path to the file being fixed
            is_doc_request: Whether this is a documentation update request
            is_feature: Whether this is a feature request
            
        Returns:
            Fixed code or None if operation fails
        """
        try:
            # Create a comprehensive prompt for Copilot
            if is_doc_request:
                prompt = f"""Documentation Update Request:
{error_message}

Current file: {file_path}
Current content:
{code}

Please provide the complete updated file content with the requested documentation changes."""
            elif is_feature:
                prompt = f"""Feature Implementation Request:
{error_message}

Current file: {file_path}
Current code:
{code}

Please provide the complete updated file content with the requested feature implemented."""
            else:
                prompt = f"""Bug Fix Request:
Error: {error_message}

File: {file_path}
Current code:
{code}

Please provide the complete corrected file content that fixes this error."""
            
            # First, try to get an explanation to understand the issue better
            logger.info("🤖 Getting error explanation from GitHub Copilot...")
            explanation = self.call_gh_copilot_explain(error_message)
            
            if explanation:
                logger.info(f"📝 Copilot explanation:\n{explanation[:300]}...")
            
            # Now create the actual fix using a more direct approach
            # Since gh copilot suggest is designed for shell commands, we'll use a different strategy
            # We'll create a temporary Python script that uses the code as input
            logger.info("🤖 Generating fix with GitHub Copilot...")
            
            # Create a temp file with the current code
            with tempfile.NamedTemporaryFile(mode='w', suffix=Path(file_path).suffix, delete=False) as f:
                f.write(code)
                temp_code_file = f.name
            
            try:
                # For now, we'll use a workaround: create a detailed prompt and ask Copilot
                # to suggest a fix. Since direct code generation via CLI is limited,
                # we'll need to parse the output carefully
                
                fix_prompt = f"""Fix this code error:

Error: {self._truncate_log(error_message, MAX_ERROR_SIZE_IN_FIX)}

File: {file_path}

Show me the corrected version of this file: {temp_code_file}"""
                
                # Use suggest to get the fix
                result = subprocess.run(
                    ["gh", "copilot", "suggest", fix_prompt],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    cwd=self.repo_path,
                )
                
                if result.returncode == 0:
                    # Parse the output - this may need adjustment based on actual Copilot output format
                    output = result.stdout.strip()
                    
                    # Extract code blocks from the output if present
                    code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', output, re.DOTALL)
                    
                    if code_blocks:
                        # Use the first code block found
                        fixed_code = code_blocks[0].strip()
                        logger.info(f"✓ Extracted fixed code from Copilot output ({len(fixed_code)} chars)")
                        return fixed_code
                    else:
                        # If no code blocks, try to use the entire output
                        # but clean it up first by removing common Copilot output prefixes
                        logger.warning("No code blocks found in Copilot output, using full output")
                        cleaned_output = output
                        
                        # Remove common prefixes from suggestions (may need updates based on CLI changes)
                        for prefix in self.COPILOT_OUTPUT_PREFIXES:
                            if prefix in cleaned_output:
                                cleaned_output = cleaned_output.split(prefix, 1)[1].strip()
                        
                        # Sanity check: code should be reasonably long
                        if len(cleaned_output) > MIN_VALID_CODE_LENGTH:
                            return cleaned_output
                        else:
                            logger.error(f"Copilot output too short ({len(cleaned_output)} chars, min {MIN_VALID_CODE_LENGTH})")
                            return None
                else:
                    logger.error(f"GitHub Copilot suggest for fix failed: {result.stderr}")
                    return None
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_code_file)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error getting fixed code from Copilot: {e}")
            return None
    
    def apply_fix(self, file_path: str, fixed_code: str) -> bool:
        """
        Apply the fixed code to the file
        
        Args:
            file_path: Path to the file
            fixed_code: The corrected code
            
        Returns:
            True if successful, False otherwise
        """
        try:
            full_path = self.repo_path / file_path
            
            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write the fixed code
            full_path.write_text(fixed_code, encoding='utf-8')
            
            logger.info(f"✓ Applied fix to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying fix to {file_path}: {e}")
            return False
    
    def create_branch(self, issue_id: str) -> bool:
        """
        Create a new Git branch for the fix
        
        Args:
            issue_id: The issue ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            branch_name = f"fix/issue-{issue_id}"
            
            # Create and checkout the branch
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Created branch: {branch_name}")
                return True
            else:
                # Branch might already exist, try to check it out
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                if result.returncode == 0:
                    logger.info(f"✓ Checked out existing branch: {branch_name}")
                    return True
                else:
                    logger.error(f"Failed to create/checkout branch: {result.stderr}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return False
    
    def commit_changes(self, file_path: str, issue_id: str) -> bool:
        """
        Commit the changes
        
        Args:
            file_path: Path to the fixed file
            issue_id: The issue ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add the file
            subprocess.run(
                ["git", "add", file_path],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Commit
            commit_message = f"Auto-fix: Resolve issue #{issue_id}\n\n[Auto-generated by Jarvis Self-Healing System]"
            
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                first_line = commit_message.splitlines()[0]
                logger.info(f"✓ Committed changes: {first_line}")
                return True
            else:
                logger.error(f"Failed to commit: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error committing changes: {e}")
            return False
    
    def push_branch(self, issue_id: str) -> bool:
        """
        Push the branch to remote
        
        Args:
            issue_id: The issue ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            branch_name = f"fix/issue-{issue_id}"
            
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Pushed branch {branch_name} to remote")
                return True
            else:
                logger.error(f"Failed to push branch: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error pushing branch: {e}")
            return False
    
    def create_pull_request(self, issue_id: str, error_message: str, file_path: str) -> bool:
        """
        Create a pull request using GitHub CLI
        
        Args:
            issue_id: The issue ID
            error_message: The original error message
            file_path: Path to the fixed file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            title = f"Auto-fix: Resolve issue #{issue_id}"
            
            # Truncate error message for PR body
            error_preview = self._truncate_log(error_message, 500)
            
            body = f"""## 🤖 Auto-Generated Fix

This PR was automatically generated by the Jarvis Self-Healing System using GitHub Copilot CLI.

### Issue
Fixes #{issue_id}

### Error
```
{error_preview}
```

### Changes
- Fixed error in `{file_path}`
- Applied AI-generated correction using GitHub Copilot CLI (`gh copilot`)

### Verification
⚠️ **Important:** Please review the changes carefully before merging.
This PR was automatically generated and should be tested before deployment.

---
_Generated by Jarvis Self-Healing Orchestrator with GitHub Copilot_
"""
            
            result = subprocess.run(
                ["gh", "pr", "create", "--title", title, "--body", body],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                pr_url = result.stdout.strip()
                logger.info(f"✓ Created pull request: {pr_url}")
                return True
            else:
                logger.error(f"Failed to create PR: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating pull request: {e}")
            return False
    
    def close_issue(self, issue_id: str) -> bool:
        """
        Close the original issue using GitHub CLI
        
        Args:
            issue_id: The issue ID to close
            
        Returns:
            True if successful, False otherwise
        """
        try:
            comment = 'Correção aplicada automaticamente via Jarvis Self-Healing. Pull Request criado.'
            
            result = subprocess.run(
                ["gh", "issue", "close", issue_id, "--comment", comment],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                logger.info(f"✓ Closed issue #{issue_id}")
                return True
            else:
                logger.error(f"Failed to close issue: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing issue: {e}")
            return False
    
    def run_with_state_machine(self, pytest_report_path: Optional[str] = None) -> int:
        """
        Main execution flow with state machine integration.
        
        Args:
            pytest_report_path: Path to pytest JSON report (optional)
        
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        logger.info("="*60)
        logger.info("JARVIS AUTO-FIXER - Self-Healing State Machine")
        logger.info("Powered by GitHub Copilot CLI")
        logger.info("="*60)
        
        # Initialize state machine
        state_machine = SelfHealingStateMachine(limit=MAX_HEALING_ATTEMPTS)
        
        # Track error details and attempted fixes for review
        error_details = ""
        attempted_fixes = []
        
        # 1. Read error from environment or pytest report
        issue_body = os.getenv("ISSUE_BODY")
        issue_id = os.getenv("ISSUE_NUMBER") or os.getenv("ISSUE_ID", "unknown")
        
        # If pytest report is provided, extract error information
        if pytest_report_path and Path(pytest_report_path).exists():
            logger.info(f"\n📊 Reading pytest report: {pytest_report_path}")
            try:
                with open(pytest_report_path, 'r') as f:
                    report = json.load(f)
                
                # Extract failed tests
                failed_tests = []
                for test in report.get('tests', []):
                    if test.get('outcome') == 'failed':
                        failed_tests.append(test)
                
                if failed_tests:
                    logger.info(f"Found {len(failed_tests)} failed test(s)")
                    # Use the first failed test for error identification
                    first_failure = failed_tests[0]
                    
                    # Extract error message - handle both string and structured formats
                    error_msg_raw = first_failure.get('call', {}).get('longrepr', '')
                    if isinstance(error_msg_raw, dict):
                        error_msg = str(error_msg_raw.get('reprcrash', {}).get('message', ''))
                    elif isinstance(error_msg_raw, list):
                        error_msg = '\n'.join(str(item) for item in error_msg_raw)
                    else:
                        error_msg = str(error_msg_raw)
                    
                    # Extract traceback - handle both string and structured formats
                    traceback_info_raw = first_failure.get('call', {}).get('crash', {}).get('message', '')
                    if isinstance(traceback_info_raw, (dict, list)):
                        traceback_info = str(traceback_info_raw)
                    else:
                        traceback_info = str(traceback_info_raw)
                    
                    # Store error details for review
                    error_details = f"Test: {first_failure.get('nodeid', 'Unknown')}\n{error_msg}\n\nTraceback:\n{traceback_info}"
                    
                    # Update issue_body with error information if it's empty or a placeholder
                    normalized_issue_body = (issue_body or "").strip().lower()
                    placeholder_issue_bodies = {"test failures detected", ""}
                    if (not issue_body) or (normalized_issue_body in placeholder_issue_bodies):
                        issue_body = f"Test failure:\n{error_msg}\n\nTraceback:\n{traceback_info}"
                    
                    # Identify error type
                    full_error = f"{error_msg}\n{traceback_info}"
                    state_machine.identify_error(full_error, traceback_info)
                else:
                    logger.info("No failed tests found in report")
                    if not issue_body:
                        logger.error("No issue body and no failed tests")
                        return 1
            except Exception as e:
                logger.warning(f"Failed to parse pytest report: {e}")
                error_details = f"Failed to parse pytest report: {str(e)}"
                if not issue_body:
                    logger.error("Could not extract error from report and no ISSUE_BODY set")
                    return 1
        
        # If we still don't have issue_body, identify from environment
        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set and no pytest report")
            return 1
        
        # Store error details if not already captured
        if not error_details:
            error_details = issue_body[:1000]  # First 1000 chars
        
        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body (preview):\n{issue_body[:200]}...")
        
        # Check infinite loop prevention (cross-run)
        logger.info(f"\n🔒 Checking healing attempt limit...")
        if not self._check_healing_attempt_limit(issue_id):
            logger.error("Exceeded maximum healing attempts - stopping to prevent infinite loop")
            self._set_github_output("final_state", State.FAILED_LIMIT.value)
            self._set_github_output("error_details", "Exceeded maximum cross-run healing attempts")
            self._set_github_output("attempted_fixes", "Maximum attempts reached across multiple workflow runs")
            return 1
        
        # Identify error if not already done
        if state_machine.state == State.CHANGE_REQUESTED and not state_machine.error_type:
            state_machine.identify_error(issue_body)
        
        # Display state machine status
        status = state_machine.get_status()
        logger.info(f"\n🤖 State Machine Status:")
        logger.info(f"   State: {status['state']}")
        logger.info(f"   Error Type: {status['error_type']}")
        logger.info(f"   Counter: {status['counter']}/{status['limit']}")
        if status['failure_reason']:
            logger.info(f"   Failure Reason: {status['failure_reason']}")
        
        # Check if human intervention is needed
        if state_machine.should_notify_human():
            logger.warning(f"\n{state_machine.get_final_message()}")
            # Set outputs for GitHub Actions review request
            self._set_github_output("final_state", state_machine.state.value)
            self._set_github_output("error_details", error_details.replace('\n', '\\n'))
            self._set_github_output("attempted_fixes", "Nenhuma tentativa realizada - erro requer intervenção humana direta")
            return 1
        
        # Repair cycle
        while state_machine.can_attempt_repair():
            logger.info(f"\n{'='*60}")
            logger.info(f"🔧 Repair Attempt {state_machine.counter + 1}/{state_machine.limit}")
            logger.info(f"{'='*60}")
            
            # Generate and apply minimal patch (1 file, 1 fix at a time)
            fix_info = self._attempt_repair(issue_body, issue_id)
            success = fix_info.get('success', False) if isinstance(fix_info, dict) else fix_info
            
            # Track attempted fix
            attempt_num = state_machine.counter + 1
            fix_description = fix_info.get('description', 'Correção automática aplicada') if isinstance(fix_info, dict) else 'Correção automática aplicada'
            file_modified = fix_info.get('file', 'Arquivo não especificado') if isinstance(fix_info, dict) else 'Arquivo não especificado'
            
            attempted_fixes.append(f"**Tentativa {attempt_num}:**\n- Arquivo: {file_modified}\n- Ação: {fix_description}\n- Resultado: {'✅ Sucesso' if success else '❌ Falhou'}")
            
            # Record the attempt
            new_state = state_machine.record_repair_attempt(success)
            
            if new_state == State.SUCCESS:
                logger.info(f"\n{state_machine.get_final_message()}")
                self._set_github_output("final_state", State.SUCCESS.value)
                self._set_github_output("error_details", error_details.replace('\n', '\\n'))
                self._set_github_output("attempted_fixes", '\n\n'.join(attempted_fixes).replace('\n', '\\n'))
                return 0
            
            elif new_state == State.FAILED_LIMIT:
                logger.warning(f"\n{state_machine.get_final_message()}")
                # Set outputs for GitHub Actions review request
                self._set_github_output("final_state", State.FAILED_LIMIT.value)
                self._set_github_output("error_details", error_details.replace('\n', '\\n'))
                self._set_github_output("attempted_fixes", '\n\n'.join(attempted_fixes).replace('\n', '\\n'))
                return 1
        
        # Should not reach here, but just in case
        logger.warning(f"\n{state_machine.get_final_message()}")
        self._set_github_output("final_state", state_machine.state.value)
        self._set_github_output("error_details", error_details.replace('\n', '\\n'))
        self._set_github_output("attempted_fixes", '\n\n'.join(attempted_fixes).replace('\n', '\\n') if attempted_fixes else "Nenhuma tentativa registrada")
        return 1
    
    def _set_github_output(self, name: str, value: str):
        """Set GitHub Actions output variable"""
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            try:
                with open(github_output, 'a') as f:
                    f.write(f"{name}={value}\n")
                logger.info(f"✓ Set GitHub output: {name}={value}")
            except Exception as e:
                logger.warning(f"Could not set GitHub output: {e}")
    
    def _attempt_repair(self, issue_body: str, issue_id: str) -> Dict[str, Any]:
        """
        Attempt to repair the issue (minimal patch: 1 file, 1 fix).
        
        Args:
            issue_body: The issue description/error
            issue_id: The issue ID
        
        Returns:
            Dictionary with repair information: {success: bool, file: str, description: str}
        """
        # This follows the existing logic but returns detailed information
        # 1. Detect request type
        is_doc_request = self.is_documentation_request(issue_body)
        is_feature = self.is_feature_request(issue_body)
        
        fix_type = "documentation update" if is_doc_request else ("feature implementation" if is_feature else "bug fix")
        
        if is_doc_request:
            logger.info("\n📚 Detected documentation update request")
        elif is_feature:
            logger.info("\n✨ Detected feature request")
        else:
            logger.info("\n🐛 Detected bug fix request")
        
        # 2. Extract affected file
        file_path = self.extract_file_from_error(issue_body)
        
        if not file_path:
            logger.info("No file path found in traceback, searching for common files...")
            file_path = self.extract_common_filename(issue_body)
        
        if not file_path:
            logger.info("No common files found, searching by keywords...")
            file_path = self.suggest_file_by_keywords(issue_body)
        
        if not file_path:
            # Special handling for meta-issues
            issue_lower = issue_body.lower()
            is_meta_selfhealing_issue = any(keyword in issue_lower for keyword in [
                'self-healing', 'self healing', 'auto-fixer', 'auto fixer', 
                'github actions', 'workflow', 'jarvis'
            ])
            
            if is_meta_selfhealing_issue:
                logger.info("Detected meta-issue about self-healing system")
                if 'github actions' in issue_lower or 'workflow' in issue_lower:
                    file_path = '.github/workflows/jarvis_code_fixer.yml'
                elif 'state machine' in issue_lower or 'state-machine' in issue_lower:
                    file_path = 'scripts/state_machine.py'
                else:
                    file_path = 'scripts/auto_fixer_logic.py'
                logger.info(f"Suggesting: {file_path}")
        
        if not file_path:
            logger.error("Could not identify target file")
            return {
                'success': False,
                'file': 'Unknown',
                'description': f'Tentativa de {fix_type} - arquivo não identificado'
            }
        
        logger.info(f"\n🎯 Target file: {file_path}")
        
        # 3. Read current file content
        current_code = self.read_file_content(file_path)
        if not current_code:
            logger.error(f"Could not read file: {file_path}")
            return {
                'success': False,
                'file': file_path,
                'description': f'Tentativa de {fix_type} - falha ao ler arquivo'
            }
        
        # 4. Get fixed code from Copilot
        logger.info(f"\n🤖 Requesting fix from GitHub Copilot...")
        fixed_code = self.get_fixed_code_with_copilot(issue_body, current_code, file_path, is_doc_request, is_feature)
        
        if not fixed_code:
            logger.error("Failed to get fix from GitHub Copilot")
            return {
                'success': False,
                'file': file_path,
                'description': f'Tentativa de {fix_type} - GitHub Copilot não gerou correção'
            }
        
        # 5. Apply the fix
        logger.info(f"\n📝 Applying changes to {file_path}...")
        if not self.apply_fix(file_path, fixed_code):
            logger.error("Failed to apply changes")
            return {
                'success': False,
                'file': file_path,
                'description': f'Tentativa de {fix_type} - falha ao aplicar correção'
            }
        
        # 6. Run pytest to validate
        logger.info(f"\n🧪 Running pytest to validate fix...")
        pytest_passed = self._run_pytest()
        
        if pytest_passed:
            logger.info("✅ Pytest passed - fix successful!")
            # 7. Commit and push changes
            if not self.create_branch(issue_id):
                logger.warning("Failed to create branch - reverting changes")
                subprocess.run(["git", "checkout", file_path], cwd=self.repo_path)
                return {
                    'success': False,
                    'file': file_path,
                    'description': f'{fix_type.capitalize()} aplicada, pytest passou, mas falha ao criar branch - alterações revertidas'
                }
            
            if not self.commit_changes(file_path, issue_id):
                logger.warning("Failed to commit changes - reverting")
                subprocess.run(["git", "checkout", file_path], cwd=self.repo_path)
                subprocess.run(["git", "checkout", "-"], cwd=self.repo_path)  # Return to previous branch
                return {
                    'success': False,
                    'file': file_path,
                    'description': f'{fix_type.capitalize()} aplicada, pytest passou, mas falha ao fazer commit - alterações revertidas'
                }
            
            if not self.push_branch(issue_id):
                logger.warning("Failed to push branch - reverting")
                subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=self.repo_path)  # Undo commit
                subprocess.run(["git", "checkout", "-"], cwd=self.repo_path)  # Return to previous branch
                return {
                    'success': False,
                    'file': file_path,
                    'description': f'{fix_type.capitalize()} aplicada, pytest passou, mas falha ao fazer push - alterações revertidas'
                }
            
            if not self.create_pull_request(issue_id, issue_body, file_path):
                logger.warning("Failed to create PR")
                # Don't fail - the fix itself worked and was pushed
            
            if not self.close_issue(issue_id):
                logger.warning("Failed to close issue")
                # Don't fail - the fix itself worked
            
            return {
                'success': True,
                'file': file_path,
                'description': f'{fix_type.capitalize()} aplicada com sucesso - pytest passou'
            }
        else:
            logger.warning("❌ Pytest failed - fix did not resolve the issue")
            # Revert changes for next attempt
            subprocess.run(["git", "checkout", file_path], cwd=self.repo_path)
            return {
                'success': False,
                'file': file_path,
                'description': f'{fix_type.capitalize()} aplicada mas pytest falhou - alterações revertidas'
            }
    
    def _run_pytest(self) -> bool:
        """
        Run pytest and return whether tests passed.
        
        Returns:
            True if all tests passed, False otherwise
        """
        try:
            result = subprocess.run(
                ["pytest", "--tb=short", "-v"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            logger.error("Pytest timed out")
            return False
        except Exception as e:
            logger.error(f"Error running pytest: {e}")
            return False
    
    def run(self) -> int:
        """
        Main execution flow
        
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        logger.info("="*60)
        logger.info("JARVIS AUTO-FIXER - Self-Healing System")
        logger.info("Powered by GitHub Copilot CLI")
        logger.info("="*60)
        
        # 1. Read error from environment
        issue_body = os.getenv("ISSUE_BODY")
        # Support both ISSUE_ID (from workflow_run) and ISSUE_NUMBER (from issues event)
        issue_id = os.getenv("ISSUE_NUMBER") or os.getenv("ISSUE_ID", "unknown")
        
        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set")
            return 1
        
        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body (preview):\n{issue_body[:200]}...")
        
        # 2. Check infinite loop prevention
        logger.info(f"\n🔒 Checking healing attempt limit...")
        if not self._check_healing_attempt_limit(issue_id):
            logger.error("Exceeded maximum healing attempts - stopping to prevent infinite loop")
            return 1
        
        # 3. Detect if this is a documentation request or feature request
        is_doc_request = self.is_documentation_request(issue_body)
        is_feature = self.is_feature_request(issue_body)
        
        if is_doc_request:
            logger.info("\n📚 Detected documentation update request")
        elif is_feature:
            logger.info("\n✨ Detected feature request")
        else:
            logger.info("\n🐛 Detected bug fix request")
        
        # 4. Extract affected file from error or find common file
        file_path = self.extract_file_from_error(issue_body)
        
        if not file_path:
            logger.info("No file path found in traceback, searching for common files...")
            file_path = self.extract_common_filename(issue_body)
        
        if not file_path:
            logger.info("No common files found, searching by keywords...")
            file_path = self.suggest_file_by_keywords(issue_body)
        
        if not file_path:
            # Special handling for meta-issues about the self-healing system
            issue_lower = issue_body.lower()
            is_meta_selfhealing_issue = any(keyword in issue_lower for keyword in [
                'self-healing', 'self healing', 'auto-fixer', 'auto fixer', 
                'github actions', 'workflow', 'jarvis'
            ])
            
            if is_meta_selfhealing_issue:
                # This is likely a request to improve the self-healing system itself
                # Suggest the most relevant files based on the context
                logger.info("Detected meta-issue about self-healing system")
                
                # Check which aspect is being discussed
                if 'github actions' in issue_lower or 'workflow' in issue_lower or 'action' in issue_lower:
                    file_path = '.github/workflows/jarvis_code_fixer.yml'
                    logger.info(f"Meta-issue appears to be about GitHub Actions, suggesting: {file_path}")
                elif 'issue' in issue_lower and ('escrita' in issue_lower or 'format' in issue_lower or 'estrutura' in issue_lower):
                    # Issue about how issues are created/formatted
                    file_path = 'app/adapters/infrastructure/github_adapter.py'
                    logger.info(f"Meta-issue appears to be about issue creation, suggesting: {file_path}")
                else:
                    # Default to auto_fixer_logic.py for general self-healing improvements
                    file_path = 'scripts/auto_fixer_logic.py'
                    logger.info(f"Meta-issue about self-healing, suggesting: {file_path}")
        
        if not file_path:
            logger.error("Could not extract or identify target file from issue")
            # Portuguese error message as per requirement for user accessibility
            logger.error("Por favor, mencione o caminho do arquivo (ex: app/main.py) para que eu possa aplicar a melhoria")
            
            # Provide helpful suggestions based on what was detected
            logger.info("\n💡 Dica: Para ajudar o auto-reparo, inclua na issue:")
            logger.info("  - O caminho do arquivo a ser modificado (ex: scripts/auto_fixer_logic.py)")
            logger.info("  - Palavras-chave relacionadas (ex: 'self-healing', 'github actions', 'api')")
            logger.info("  - Uma descrição clara do que precisa ser alterado")
            return 1
        
        logger.info(f"\n🎯 Target file: {file_path}")
        
        # 5. Read current file content
        current_code = self.read_file_content(file_path)
        
        if not current_code:
            logger.error(f"Could not read file: {file_path}")
            return 1
        
        # 6. Get fixed code from GitHub Copilot CLI
        if is_doc_request:
            logger.info(f"\n🤖 Requesting documentation update from GitHub Copilot...")
        elif is_feature:
            logger.info(f"\n🤖 Requesting feature implementation from GitHub Copilot...")
        else:
            logger.info(f"\n🤖 Requesting bug fix from GitHub Copilot...")
        
        fixed_code = self.get_fixed_code_with_copilot(issue_body, current_code, file_path, is_doc_request, is_feature)
        
        if not fixed_code:
            logger.error("Failed to get updated content from GitHub Copilot")
            logger.error("Possible reasons:")
            logger.error("  - GitHub Copilot CLI extension is not installed or not authenticated")
            logger.error("  - Network connectivity issues")
            logger.error("  - The error/request was too complex for automated fixing")
            logger.info("\nTo install GitHub Copilot CLI extension:")
            logger.info("  gh extension install github/gh-copilot")
            return 1
        
        # 7. Apply the fix
        logger.info(f"\n📝 Applying changes to {file_path}...")
        if not self.apply_fix(file_path, fixed_code):
            logger.error("Failed to apply changes")
            return 1
        
        # 8. Create Git branch
        logger.info(f"\n🌿 Creating branch fix/issue-{issue_id}...")
        if not self.create_branch(issue_id):
            logger.error("Failed to create branch")
            return 1
        
        # 9. Commit changes
        logger.info(f"\n💾 Committing changes...")
        if not self.commit_changes(file_path, issue_id):
            logger.error("Failed to commit changes")
            return 1
        
        # 10. Push branch
        logger.info(f"\n⬆️  Pushing branch to remote...")
        if not self.push_branch(issue_id):
            logger.error("Failed to push branch")
            return 1
        
        # 11. Create pull request
        logger.info(f"\n🔀 Creating pull request...")
        if not self.create_pull_request(issue_id, issue_body, file_path):
            logger.error("Failed to create pull request")
            return 1
        
        # 12. Close the original issue
        logger.info(f"\n🔒 Closing original issue #{issue_id}...")
        if not self.close_issue(issue_id):
            logger.warning("Failed to close issue (PR was created successfully)")
            # Don't fail the entire process if issue closing fails
        
        logger.info("\n" + "="*60)
        logger.info("✅ AUTO-FIX COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
        return 0


def main():
    """Entry point for the script"""
    parser = argparse.ArgumentParser(
        description="Jarvis Auto-Fixer - Self-Healing State Machine"
    )
    parser.add_argument(
        '--state',
        type=str,
        help='Path to pytest JSON report file for state machine mode'
    )
    
    args = parser.parse_args()
    
    try:
        auto_fixer = AutoFixer()
        
        # Use state machine mode if --state argument is provided
        if args.state:
            logger.info("Running in State Machine mode")
            exit_code = auto_fixer.run_with_state_machine(args.state)
        else:
            logger.info("Running in Standard mode")
            exit_code = auto_fixer.run()
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Auto-fixer interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
