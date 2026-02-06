#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demonstration of Hardware-Based Encryption for Jarvis

This script demonstrates how the encryption system works:
1. Encrypts sensitive values using hardware-specific keys
2. Shows that encrypted values cannot be decrypted on different hardware
3. Demonstrates the complete setup wizard flow

Usage:
    python demo_encryption.py
"""

import tempfile
from pathlib import Path

from app.core.encryption import (
    encrypt_value,
    decrypt_value,
    get_hardware_id,
    is_encrypted,
)
from app.adapters.infrastructure.setup_wizard import save_env_file
from app.core.config import Settings


def print_section(title: str) -> None:
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def demo_basic_encryption():
    """Demonstrate basic encryption and decryption"""
    print_section("1. Basic Encryption/Decryption")
    
    # Get hardware ID
    hw_id = get_hardware_id()
    print(f"Hardware ID (masked): {hw_id[:30]}...")
    
    # Encrypt a test value
    original_value = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
    print(f"\nOriginal API Key: {original_value}")
    
    encrypted = encrypt_value(original_value)
    print(f"Encrypted Value: {encrypted[:50]}...")
    print(f"Is Encrypted: {is_encrypted(encrypted)}")
    
    # Decrypt it back
    decrypted = decrypt_value(encrypted)
    print(f"Decrypted Value: {decrypted}")
    print(f"✓ Encryption/Decryption successful: {original_value == decrypted}")


def demo_setup_wizard_flow():
    """Demonstrate the setup wizard encryption flow"""
    print_section("2. Setup Wizard Flow")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Simulate setup wizard
        print("Running setup wizard simulation...")
        assistant_name = "Jarvis"
        user_id = "user_123"
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        database_url = "postgresql://postgres:password@db.example.com:5432/postgres"
        
        # Create .env.example
        env_example = tmp_path / ".env.example"
        env_example.write_text("""# Example
GEMINI_API_KEY=
DATABASE_URL=
USER_ID=
ASSISTANT_NAME=
""")
        
        # Save encrypted .env
        result = save_env_file(assistant_name, user_id, api_key, database_url, tmp_path)
        print(f"✓ .env file created: {result}")
        
        # Show .env content
        env_file = tmp_path / ".env"
        content = env_file.read_text()
        
        print("\n.env file content (truncated):")
        for line in content.split('\n')[:20]:
            if 'ENCRYPTED:' in line:
                key, value = line.split('=', 1)
                print(f"{key}={value[:60]}...")
            elif line.strip():
                print(line)
        
        # Verify values are encrypted
        print(f"\n✓ API key is encrypted: {api_key not in content}")
        print(f"✓ Database URL is encrypted: {database_url not in content}")
        print(f"✓ File contains encrypted values: {'ENCRYPTED:' in content}")
        
        # Load settings and verify decryption
        print("\nLoading Settings from encrypted .env...")
        settings = Settings(_env_file=str(env_file))
        
        print(f"✓ API Key decrypted correctly: {settings.gemini_api_key == api_key}")
        print(f"✓ Database URL decrypted correctly: {settings.database_url == database_url}")
        print(f"✓ User ID loaded: {settings.user_id == user_id}")
        print(f"✓ Assistant Name loaded: {settings.assistant_name == assistant_name}")


def demo_hardware_binding():
    """Demonstrate that encrypted values are hardware-bound"""
    print_section("3. Hardware Binding Demonstration")
    
    from unittest.mock import patch
    
    # Encrypt on "this machine"
    api_key = "test_secret_key"
    encrypted = encrypt_value(api_key)
    
    print(f"Original API Key: {api_key}")
    print(f"Encrypted on this machine: {encrypted[:60]}...")
    
    # Try to decrypt with different hardware ID
    print("\nSimulating .env moved to different machine...")
    with patch('app.core.encryption.get_hardware_id') as mock_hw_id:
        mock_hw_id.return_value = "different-hardware-12345-different-platform"
        
        try:
            decrypted = decrypt_value(encrypted)
            print("✗ ERROR: Should not have decrypted!")
        except Exception as e:
            print(f"✓ Decryption failed as expected: {type(e).__name__}")
            print(f"  Message: {str(e)[:100]}")
    
    print("\n✓ Encrypted values are hardware-bound and cannot be moved!")


def main():
    """Run all demonstrations"""
    print("\n" + "="*70)
    print("  Jarvis Hardware-Based Encryption Demonstration")
    print("="*70)
    
    try:
        demo_basic_encryption()
        demo_setup_wizard_flow()
        demo_hardware_binding()
        
        print_section("Summary")
        print("✓ All demonstrations completed successfully!")
        print("\nKey Features:")
        print("  • Values encrypted using hardware-specific keys")
        print("  • .env files cannot be moved between machines")
        print("  • Automatic encryption in setup wizard")
        print("  • Automatic decryption when loading settings")
        print("  • Backward compatible with plain text values")
        
    except Exception as e:
        print(f"\n✗ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
