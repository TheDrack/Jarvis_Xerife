#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fixer Logic Script

This script is part of the self-healing system for Jarvis Assistant.
It reads errors from GitHub issues, uses AI (Groq/Gemini) to generate fixes,
and automatically creates pull requests with the corrections.

Features:
1. Reads error from ISSUE_BODY environment variable
2. Extracts affected file path from the error message or detects common files
3. Handles both code bug fixes and documentation updates
4. Sends error/request and file code to Groq/Gemini API
5. Receives corrected/updated content from AI
6. Applies the fix locally
7. Creates a Git branch fix/issue-{ID}
8. Commits the changes
9. Opens a Pull Request using GitHub CLI (gh pr create)
10. Closes the original issue using GitHub CLI (gh issue close)

Key Capabilities:
- File Flexibility: If no file path in traceback, searches for common files
  (README.md, requirements.txt, etc.) in issue body with case-insensitive matching
- Keyword-Based Suggestions: If no file found, searches for keywords like 'interface',
  'api', or 'frontend' and suggests probable files (app/main.py, README.md, etc.)
- API Validation: Clear error messages when GROQ_API_KEY or GOOGLE_API_KEY missing
- Context Handling: Detects documentation requests (e.g., "add a section") and
  provides current file content to AI instead of treating it as a bug

Usage:
    # For bug fixes:
    export ISSUE_BODY="Error: NameError in file app/main.py line 42..."
    export ISSUE_ID="123"
    python scripts/auto_fixer_logic.py
    
    # For documentation updates:
    export ISSUE_BODY="Please add a section about installation to README.md"
    export ISSUE_ID="124"
    python scripts/auto_fixer_logic.py
    
    # With keyword-based suggestion:
    export ISSUE_BODY="The interface needs improvement"
    export ISSUE_ID="125"
    python scripts/auto_fixer_logic.py
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AutoFixerError(Exception):
    """Base exception for auto-fixer errors"""
    pass


class AutoFixer:
    """
    Auto-Fixer for self-healing system.
    
    Uses AI (Groq/Gemini) to analyze errors and generate code fixes.
    """
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the auto-fixer
        
        Args:
            repo_path: Path to the git repository (defaults to current directory)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        
        # Get API keys from environment
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.groq_api_key and not self.gemini_api_key:
            self._log_missing_api_keys_error()
        
        # Validate gh CLI is available
        self._check_gh_cli()
    
    def _log_missing_api_keys_error(self):
        """Log a clear error message about missing API keys"""
        logger.error(
            "❌ CRITICAL: No AI API keys found!\n"
            "   The auto-fixer cannot proceed without AI capabilities.\n"
            "   Please set one of the following environment variables:\n"
            "   - GROQ_API_KEY: For Groq API access\n"
            "   - GOOGLE_API_KEY or GEMINI_API_KEY: For Gemini API access\n"
            "   Without an API key, the auto-fixer cannot generate fixes."
        )
    
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
        # Keyword to file mapping
        # Note: This mapping can be extended with more keywords and files as needed
        keyword_suggestions = {
            # API and interface keywords (English and Portuguese)
            'api': ['app/adapters/infrastructure/api_server.py', 'app/adapters/infrastructure/api_models.py', 'app/main.py', 'main.py'],
            'payload': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
            'mensagem': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],  # Portuguese for 'message'
            'envio': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],  # Portuguese for 'send/sending'
            'json': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
            # Interface keyword - prioritizes API files when combined with API-related terms
            'interface': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py', 'app/main.py', 'main.py'],
            'frontend': ['app/main.py', 'main.py', 'README.md'],
            # Documentation keywords
            'documentation': ['README.md', 'docs/README.md'],
            'documentação': ['README.md', 'docs/README.md'],  # Portuguese
            'readme': ['README.md'],
        }
        
        # Convert issue body to lowercase for case-insensitive matching
        issue_lower = issue_body.lower()
        
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
    
    def call_groq_api(self, error_message: str, code: str, is_doc_request: bool = False, is_feature: bool = False) -> Optional[str]:
        """
        Call Groq API to get fixed code
        
        Args:
            error_message: The error message or user request
            code: The current code with the error or current file content
            is_doc_request: Whether this is a documentation update request
            is_feature: Whether this is a feature request
            
        Returns:
            Fixed code or None if API call fails
        """
        if not self.groq_api_key:
            logger.error("❌ GROQ_API_KEY not set. Cannot proceed without AI API access.")
            return None
        
        try:
            import groq
            
            client = groq.Groq(api_key=self.groq_api_key)
            
            if is_doc_request:
                # Documentation update request
                prompt = f"""You are a documentation assistant. The user has requested an update to a documentation file.

USER REQUEST:
{error_message}

CURRENT FILE CONTENT:
{code}

Please update the file according to the user's request. Return ONLY the complete updated file content without any explanations, comments, or markdown formatting."""
            elif is_feature:
                # Feature request - implement new functionality
                prompt = f"""You are a senior software developer. The user has requested a new feature or enhancement.

FEATURE REQUEST:
{error_message}

CURRENT FILE CONTENT:
{code}

Please implement the requested feature by modifying the existing code. Make minimal, focused changes that add the requested functionality while preserving all existing features. Return ONLY the complete updated file content without any explanations, comments, or markdown formatting."""
            else:
                # Code bug fix request
                prompt = f"""You are a code fixing assistant. Analyze the following error and code, then return ONLY the corrected code without any explanations, comments, or markdown formatting.

ERROR:
{error_message}

CURRENT CODE:
{code}

Return ONLY the corrected code, nothing else."""
            
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Return only the requested content without explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4000,
            )
            
            fixed_code = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if fixed_code.startswith("```"):
                lines = fixed_code.split("\n")
                # Remove first and last line (```language and ```)
                fixed_code = "\n".join(lines[1:-1])
            
            logger.info(f"✓ Received updated content from Groq ({len(fixed_code)} chars)")
            return fixed_code
            
        except ImportError:
            logger.error("groq library not installed. Run: pip install groq")
            return None
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return None
    
    def call_gemini_api(self, error_message: str, code: str, is_doc_request: bool = False, is_feature: bool = False) -> Optional[str]:
        """
        Call Gemini API to get fixed code
        
        Args:
            error_message: The error message or user request
            code: The current code with the error or current file content
            is_doc_request: Whether this is a documentation update request
            is_feature: Whether this is a feature request
            
        Returns:
            Fixed code or None if API call fails
        """
        if not self.gemini_api_key:
            logger.error("❌ GOOGLE_API_KEY/GEMINI_API_KEY not set. Cannot proceed without AI API access.")
            return None
        
        try:
            # Note: Install with 'pip install google-genai', import as 'from google import genai'
            from google import genai
            
            client = genai.Client(api_key=self.gemini_api_key)
            
            if is_doc_request:
                # Documentation update request
                prompt = f"""You are a documentation assistant. The user has requested an update to a documentation file.

USER REQUEST:
{error_message}

CURRENT FILE CONTENT:
{code}

Please update the file according to the user's request. Return ONLY the complete updated file content without any explanations, comments, or markdown formatting."""
            elif is_feature:
                # Feature request - implement new functionality
                prompt = f"""You are a senior software developer. The user has requested a new feature or enhancement.

FEATURE REQUEST:
{error_message}

CURRENT FILE CONTENT:
{code}

Please implement the requested feature by modifying the existing code. Make minimal, focused changes that add the requested functionality while preserving all existing features. Return ONLY the complete updated file content without any explanations, comments, or markdown formatting."""
            else:
                # Code bug fix request
                prompt = f"""You are a code fixing assistant. Analyze the following error and code, then return ONLY the corrected code without any explanations, comments, or markdown formatting.

ERROR:
{error_message}

CURRENT CODE:
{code}

Return ONLY the corrected code, nothing else."""
            
            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
                contents=prompt,
            )
            
            fixed_code = response.text.strip()
            
            # Remove markdown code blocks if present
            if fixed_code.startswith("```"):
                lines = fixed_code.split("\n")
                # Remove first and last line (```language and ```)
                fixed_code = "\n".join(lines[1:-1])
            
            logger.info(f"✓ Received updated content from Gemini ({len(fixed_code)} chars)")
            return fixed_code
            
        except ImportError:
            logger.error("google-genai library not installed. Run: pip install google-genai")
            return None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None
    
    def get_fixed_code(self, error_message: str, code: str, is_doc_request: bool = False, is_feature: bool = False) -> Optional[str]:
        """
        Get fixed code using available AI APIs (tries Groq first, then Gemini)
        
        Args:
            error_message: The error message or user request
            code: The current code with the error or current file content
            is_doc_request: Whether this is a documentation update request
            is_feature: Whether this is a feature request
            
        Returns:
            Fixed code or None if all APIs fail
        """
        # Try Groq first
        fixed_code = self.call_groq_api(error_message, code, is_doc_request, is_feature)
        
        if fixed_code:
            return fixed_code
        
        # Fallback to Gemini
        logger.info("Falling back to Gemini API...")
        fixed_code = self.call_gemini_api(error_message, code, is_doc_request, is_feature)
        
        return fixed_code
    
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
            error_preview = error_message[:500] + "..." if len(error_message) > 500 else error_message
            
            body = f"""## 🤖 Auto-Generated Fix

This PR was automatically generated by the Jarvis Self-Healing System.

### Issue
Fixes #{issue_id}

### Error
```
{error_preview}
```

### Changes
- Fixed error in `{file_path}`
- Applied AI-generated correction using Groq/Gemini

### Verification
Please review the changes carefully before merging.

---
_Generated by Jarvis Self-Healing Orchestrator_
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
    
    def run(self) -> int:
        """
        Main execution flow
        
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        logger.info("="*60)
        logger.info("JARVIS AUTO-FIXER - Self-Healing System")
        logger.info("="*60)
        
        # 1. Read error from environment
        issue_body = os.getenv("ISSUE_BODY")
        # Support both ISSUE_ID (from workflow_run) and ISSUE_NUMBER (from issues event)
        issue_id = os.getenv("ISSUE_NUMBER") or os.getenv("ISSUE_ID", "unknown")
        
        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set")
            return 1
        
        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body:\n{issue_body[:200]}...")
        
        # Check if we have API keys
        if not self.groq_api_key and not self.gemini_api_key:
            logger.error("\n" + "="*60)
            self._log_missing_api_keys_error()
            logger.error("="*60)
            return 1
        
        # 2. Detect if this is a documentation request or feature request
        is_doc_request = self.is_documentation_request(issue_body)
        is_feature = self.is_feature_request(issue_body)
        
        if is_doc_request:
            logger.info("\n📚 Detected documentation update request")
        elif is_feature:
            logger.info("\n✨ Detected feature request")
        else:
            logger.info("\n🐛 Detected bug fix request")
        
        # 3. Extract affected file from error or find common file
        file_path = self.extract_file_from_error(issue_body)
        
        if not file_path:
            logger.info("No file path found in traceback, searching for common files...")
            file_path = self.extract_common_filename(issue_body)
        
        if not file_path:
            logger.info("No common files found, searching by keywords...")
            file_path = self.suggest_file_by_keywords(issue_body)
        
        if not file_path:
            logger.error("Could not extract or identify target file from issue")
            # Portuguese error message as per requirement for user accessibility
            logger.error("Por favor, mencione o caminho do arquivo (ex: app/main.py) para que eu possa aplicar a melhoria")
            return 1
        
        logger.info(f"\n🎯 Target file: {file_path}")
        
        # 4. Read current file content
        current_code = self.read_file_content(file_path)
        
        if not current_code:
            logger.error(f"Could not read file: {file_path}")
            return 1
        
        # 5. Get fixed code from AI
        if is_doc_request:
            logger.info(f"\n🤖 Requesting documentation update from AI...")
        elif is_feature:
            logger.info(f"\n🤖 Requesting feature implementation from AI...")
        else:
            logger.info(f"\n🤖 Requesting bug fix from AI...")
        
        fixed_code = self.get_fixed_code(issue_body, current_code, is_doc_request, is_feature)
        
        if not fixed_code:
            logger.error("Failed to get updated content from AI")
            logger.error("Possible reasons:")
            logger.error("  - API key is invalid or expired")
            logger.error("  - API service is unavailable")
            logger.error("  - Network connectivity issues")
            return 1
        
        # 6. Apply the fix
        logger.info(f"\n📝 Applying changes to {file_path}...")
        if not self.apply_fix(file_path, fixed_code):
            logger.error("Failed to apply changes")
            return 1
        
        # 7. Create Git branch
        logger.info(f"\n🌿 Creating branch fix/issue-{issue_id}...")
        if not self.create_branch(issue_id):
            logger.error("Failed to create branch")
            return 1
        
        # 8. Commit changes
        logger.info(f"\n💾 Committing changes...")
        if not self.commit_changes(file_path, issue_id):
            logger.error("Failed to commit changes")
            return 1
        
        # 9. Push branch
        logger.info(f"\n⬆️  Pushing branch to remote...")
        if not self.push_branch(issue_id):
            logger.error("Failed to push branch")
            return 1
        
        # 10. Create pull request
        logger.info(f"\n🔀 Creating pull request...")
        if not self.create_pull_request(issue_id, issue_body, file_path):
            logger.error("Failed to create pull request")
            return 1
        
        # 11. Close the original issue
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
    try:
        auto_fixer = AutoFixer()
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
