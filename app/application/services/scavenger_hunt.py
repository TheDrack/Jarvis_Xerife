# -*- coding: utf-8 -*-
"""
API Key Scavenger Hunt Service

When JARVIS encounters a missing API key, this service attempts to find
instructions on how to obtain the key from official documentation or guides.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class APIKeyGuide:
    """Guide for obtaining an API key"""
    service_name: str
    key_name: str
    steps: List[str]
    documentation_url: str
    is_free: bool
    estimated_time: str  # e.g., "5 minutes"


class ScavengerHunt:
    """
    Finds instructions for obtaining missing API keys.
    
    This service maintains a knowledge base of how to obtain API keys
    for popular services. When a capability requires a missing API key,
    JARVIS can use this to guide the user (or itself) on how to get it.
    """
    
    # Knowledge base of API key acquisition guides
    API_KEY_GUIDES: Dict[str, APIKeyGuide] = {
        "OPENAI_API_KEY": APIKeyGuide(
            service_name="OpenAI",
            key_name="OPENAI_API_KEY",
            steps=[
                "1. Visit https://platform.openai.com/signup",
                "2. Create an account or sign in",
                "3. Navigate to https://platform.openai.com/api-keys",
                "4. Click 'Create new secret key'",
                "5. Copy the key and set it as environment variable OPENAI_API_KEY",
                "6. Note: Free tier available with $5 credit for new users"
            ],
            documentation_url="https://platform.openai.com/docs/quickstart",
            is_free=True,
            estimated_time="5 minutes"
        ),
        "ANTHROPIC_API_KEY": APIKeyGuide(
            service_name="Anthropic (Claude)",
            key_name="ANTHROPIC_API_KEY",
            steps=[
                "1. Visit https://console.anthropic.com/",
                "2. Create an account or sign in",
                "3. Navigate to API Keys section",
                "4. Click 'Create Key'",
                "5. Copy the key and set it as environment variable ANTHROPIC_API_KEY",
                "6. Note: Free tier with limited credits available"
            ],
            documentation_url="https://docs.anthropic.com/claude/reference/getting-started-with-the-api",
            is_free=True,
            estimated_time="5 minutes"
        ),
        "GEMINI_API_KEY": APIKeyGuide(
            service_name="Google Gemini",
            key_name="GEMINI_API_KEY",
            steps=[
                "1. Visit https://makersuite.google.com/app/apikey",
                "2. Sign in with your Google account",
                "3. Click 'Create API Key'",
                "4. Select a Google Cloud project or create a new one",
                "5. Copy the key and set it as environment variable GEMINI_API_KEY",
                "6. Note: Free tier available with generous limits"
            ],
            documentation_url="https://ai.google.dev/tutorials/get_started_web",
            is_free=True,
            estimated_time="3 minutes"
        ),
        "GROQ_API_KEY": APIKeyGuide(
            service_name="Groq",
            key_name="GROQ_API_KEY",
            steps=[
                "1. Visit https://console.groq.com/",
                "2. Create an account or sign in",
                "3. Navigate to API Keys section",
                "4. Click 'Create API Key'",
                "5. Copy the key and set it as environment variable GROQ_API_KEY",
                "6. Note: Free tier available"
            ],
            documentation_url="https://console.groq.com/docs/quickstart",
            is_free=True,
            estimated_time="5 minutes"
        ),
        "STRIPE_API_KEY": APIKeyGuide(
            service_name="Stripe",
            key_name="STRIPE_API_KEY",
            steps=[
                "1. Visit https://stripe.com/",
                "2. Create an account or sign in",
                "3. Navigate to Developers > API Keys",
                "4. Copy the 'Secret key' (starts with sk_)",
                "5. Set it as environment variable STRIPE_API_KEY",
                "6. Note: Test mode available for development (free)"
            ],
            documentation_url="https://stripe.com/docs/keys",
            is_free=True,
            estimated_time="10 minutes"
        ),
        "GITHUB_TOKEN": APIKeyGuide(
            service_name="GitHub",
            key_name="GITHUB_TOKEN",
            steps=[
                "1. Visit https://github.com/settings/tokens",
                "2. Click 'Generate new token' > 'Generate new token (classic)'",
                "3. Give it a descriptive name",
                "4. Select required scopes (repo, workflow, etc.)",
                "5. Click 'Generate token' and copy it immediately",
                "6. Set it as environment variable GITHUB_TOKEN"
            ],
            documentation_url="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token",
            is_free=True,
            estimated_time="5 minutes"
        ),
        "HUGGINGFACE_TOKEN": APIKeyGuide(
            service_name="HuggingFace",
            key_name="HUGGINGFACE_TOKEN",
            steps=[
                "1. Visit https://huggingface.co/join",
                "2. Create an account or sign in",
                "3. Navigate to Settings > Access Tokens",
                "4. Click 'New token'",
                "5. Give it a name and select permissions",
                "6. Copy the token and set it as environment variable HUGGINGFACE_TOKEN"
            ],
            documentation_url="https://huggingface.co/docs/hub/security-tokens",
            is_free=True,
            estimated_time="5 minutes"
        ),
    }
    
    @classmethod
    def find_guide(cls, api_key_name: str) -> Optional[APIKeyGuide]:
        """
        Find a guide for obtaining a specific API key.
        
        Args:
            api_key_name: Name of the environment variable (e.g., "OPENAI_API_KEY")
            
        Returns:
            APIKeyGuide if found, None otherwise
        """
        # Try exact match first
        if api_key_name in cls.API_KEY_GUIDES:
            return cls.API_KEY_GUIDES[api_key_name]
        
        # Try fuzzy matching
        api_key_upper = api_key_name.upper()
        for key, guide in cls.API_KEY_GUIDES.items():
            if key.upper() in api_key_upper or api_key_upper in key.upper():
                return guide
        
        return None
    
    @classmethod
    def generate_acquisition_report(cls, missing_keys: List[str]) -> str:
        """
        Generate a report on how to obtain missing API keys.
        
        Args:
            missing_keys: List of missing environment variable names
            
        Returns:
            Formatted report with step-by-step instructions
        """
        report_lines = [
            "═" * 70,
            "  🔍 JARVIS SCAVENGER HUNT: Missing API Keys",
            "═" * 70,
            "",
            f"Found {len(missing_keys)} missing API key(s). Here's how to obtain them:",
            ""
        ]
        
        for i, key_name in enumerate(missing_keys, 1):
            guide = cls.find_guide(key_name)
            
            if guide:
                report_lines.extend([
                    f"{'─' * 70}",
                    f"  {i}. {guide.service_name} ({guide.key_name})",
                    f"{'─' * 70}",
                    f"  ⏱️  Estimated Time: {guide.estimated_time}",
                    f"  💰 Free Tier: {'Yes' if guide.is_free else 'No'}",
                    f"  📚 Documentation: {guide.documentation_url}",
                    "",
                    "  Steps to obtain:",
                ])
                report_lines.extend([f"     {step}" for step in guide.steps])
                report_lines.append("")
            else:
                report_lines.extend([
                    f"{'─' * 70}",
                    f"  {i}. {key_name}",
                    f"{'─' * 70}",
                    f"  ⚠️  No automatic guide available for this key.",
                    f"  💡 Suggestion: Search for '{key_name} how to get' in your browser",
                    ""
                ])
        
        report_lines.extend([
            "═" * 70,
            "  💡 TIP: Once you have the keys, add them to your .env file or",
            "     set them as environment variables before starting JARVIS.",
            "═" * 70
        ])
        
        return "\n".join(report_lines)
    
    @classmethod
    def search_for_missing_resources(cls, missing_resources: List[Dict]) -> Dict[str, List[str]]:
        """
        Analyze missing resources and categorize them.
        
        Args:
            missing_resources: List of missing resource dictionaries from CapabilityManager
            
        Returns:
            Dictionary categorizing resources by type with acquisition guides
        """
        categorized = {
            "api_keys": [],
            "libraries": [],
            "other": []
        }
        
        for resource in missing_resources:
            res_type = resource.get("type", "")
            res_name = resource.get("name", "")
            
            if res_type == "environment_variable":
                guide = cls.find_guide(res_name)
                if guide:
                    categorized["api_keys"].append(f"{res_name} - {guide.documentation_url}")
                else:
                    categorized["api_keys"].append(f"{res_name} - Search online for acquisition guide")
            
            elif res_type == "library":
                categorized["libraries"].append(f"{res_name} - Install with: pip install {res_name}")
            
            else:
                categorized["other"].append(f"{res_name} ({res_type})")
        
        return categorized
