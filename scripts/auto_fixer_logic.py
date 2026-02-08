#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fixer Logic Script

This script is part of the self-healing system for Jarvis Assistant.
It reads errors from GitHub issues, uses AI (Groq/Gemini) to generate fixes,
and automatically creates pull requests with the corrections.

Features:
1. Reads error from ISSUE_BODY environment variable
2. Extracts affected file path from the error message
3. Sends error and file code to Groq/Gemini API
4. Receives corrected code from AI
5. Applies the fix locally
6. Creates a Git branch fix/issue-{ID}
7. Commits the changes
8. Opens a Pull Request using GitHub CLI (gh pr create)

Usage:
    export ISSUE_BODY="Error: NameError in file app/main.py line 42..."
    export ISSUE_ID="123"
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
            logger.warning("No API keys found. Set GROQ_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY")
        
        # Validate gh CLI is available
        self._check_gh_cli()
    
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
                logger.info(f"Extracted file path: {file_path}")
                return file_path
        
        logger.warning("Could not extract file path from error message")
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
    
    def call_groq_api(self, error_message: str, code: str) -> Optional[str]:
        """
        Call Groq API to get fixed code
        
        Args:
            error_message: The error message
            code: The current code with the error
            
        Returns:
            Fixed code or None if API call fails
        """
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set, skipping Groq API")
            return None
        
        try:
            import groq
            
            client = groq.Groq(api_key=self.groq_api_key)
            
            prompt = f"""You are a code fixing assistant. Analyze the following error and code, then return ONLY the corrected code without any explanations, comments, or markdown formatting.

ERROR:
{error_message}

CURRENT CODE:
{code}

Return ONLY the corrected code, nothing else."""
            
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": "You are a code fixing assistant. Return only corrected code without explanations."},
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
            
            logger.info(f"✓ Received fixed code from Groq ({len(fixed_code)} chars)")
            return fixed_code
            
        except ImportError:
            logger.error("groq library not installed. Run: pip install groq")
            return None
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return None
    
    def call_gemini_api(self, error_message: str, code: str) -> Optional[str]:
        """
        Call Gemini API to get fixed code
        
        Args:
            error_message: The error message
            code: The current code with the error
            
        Returns:
            Fixed code or None if API call fails
        """
        if not self.gemini_api_key:
            logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set, skipping Gemini API")
            return None
        
        try:
            # Note: Install with 'pip install google-genai', import as 'from google import genai'
            from google import genai
            
            client = genai.Client(api_key=self.gemini_api_key)
            
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
            
            logger.info(f"✓ Received fixed code from Gemini ({len(fixed_code)} chars)")
            return fixed_code
            
        except ImportError:
            logger.error("google-genai library not installed. Run: pip install google-genai")
            return None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None
    
    def get_fixed_code(self, error_message: str, code: str) -> Optional[str]:
        """
        Get fixed code using available AI APIs (tries Groq first, then Gemini)
        
        Args:
            error_message: The error message
            code: The current code with the error
            
        Returns:
            Fixed code or None if all APIs fail
        """
        # Try Groq first
        fixed_code = self.call_groq_api(error_message, code)
        
        if fixed_code:
            return fixed_code
        
        # Fallback to Gemini
        logger.info("Falling back to Gemini API...")
        fixed_code = self.call_gemini_api(error_message, code)
        
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
        issue_id = os.getenv("ISSUE_ID", "unknown")
        
        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set")
            return 1
        
        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body:\n{issue_body[:200]}...")
        
        # 2. Extract affected file from error
        file_path = self.extract_file_from_error(issue_body)
        
        if not file_path:
            logger.error("Could not extract file path from error message")
            return 1
        
        # 3. Read current file content
        current_code = self.read_file_content(file_path)
        
        if not current_code:
            logger.error(f"Could not read file: {file_path}")
            return 1
        
        # 4. Get fixed code from AI
        logger.info(f"\n🤖 Requesting fix from AI...")
        fixed_code = self.get_fixed_code(issue_body, current_code)
        
        if not fixed_code:
            logger.error("Failed to get fixed code from AI")
            return 1
        
        # 5. Apply the fix
        logger.info(f"\n📝 Applying fix to {file_path}...")
        if not self.apply_fix(file_path, fixed_code):
            logger.error("Failed to apply fix")
            return 1
        
        # 6. Create Git branch
        logger.info(f"\n🌿 Creating branch fix/issue-{issue_id}...")
        if not self.create_branch(issue_id):
            logger.error("Failed to create branch")
            return 1
        
        # 7. Commit changes
        logger.info(f"\n💾 Committing changes...")
        if not self.commit_changes(file_path, issue_id):
            logger.error("Failed to commit changes")
            return 1
        
        # 8. Push branch
        logger.info(f"\n⬆️  Pushing branch to remote...")
        if not self.push_branch(issue_id):
            logger.error("Failed to push branch")
            return 1
        
        # 9. Create pull request
        logger.info(f"\n🔀 Creating pull request...")
        if not self.create_pull_request(issue_id, issue_body, file_path):
            logger.error("Failed to create pull request")
            return 1
        
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
