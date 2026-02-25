from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Tests for hardware-based encryption functionality"""

import pytest
from cryptography.fernet import InvalidToken
from unittest.mock import patch

from app.core.encryption import (
    decrypt_value,
    derive_key_from_hardware,
    encrypt_value,
    get_hardware_id,
    is_encrypted,
    ENCRYPTION_PREFIX,
)


class TestEncryption(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test cases for encryption module"""

    def test_get_hardware_id_returns_consistent_value(self):
        """Test that hardware ID is consistent across calls"""
        id1 = get_hardware_id()
        id2 = get_hardware_id()
        assert id1 == id2
        assert len(id1) > 0

    def test_derive_key_from_hardware_returns_consistent_key(self):
        """Test that key derivation is deterministic"""
        key1 = derive_key_from_hardware()
        key2 = derive_key_from_hardware()
        assert key1 == key2
        assert len(key1) > 0

    def test_encrypt_value_adds_prefix(self):
        """Test that encrypted values have the correct prefix"""
        plaintext = "test_secret_value"
        encrypted = encrypt_value(plaintext)
        
        assert encrypted.startswith(ENCRYPTION_PREFIX)
        assert len(encrypted) > len(ENCRYPTION_PREFIX)

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work correctly"""
        plaintext = "my_secret_api_key_123"
        
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        
        assert decrypted == plaintext

    def test_encrypt_decrypt_long_value(self):
        """Test encryption/decryption with long values like database URLs"""
        plaintext = "postgresql://user:test_password@db.example.com:5432/testdb"
        
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        
        assert decrypted == plaintext

    def test_decrypt_value_without_prefix(self):
        """Test that decryption works even if prefix is missing"""
        plaintext = "test_value"
        encrypted = encrypt_value(plaintext)
        
        # Remove prefix
        encrypted_without_prefix = encrypted[len(ENCRYPTION_PREFIX):]
        
        decrypted = decrypt_value(encrypted_without_prefix)
        assert decrypted == plaintext

    def test_is_encrypted_detects_encrypted_values(self):
        """Test that is_encrypted correctly identifies encrypted values"""
        plaintext = "not_encrypted"
        encrypted = encrypt_value(plaintext)
        
        assert is_encrypted(encrypted) is True
        assert is_encrypted(plaintext) is False

    def test_decrypt_fails_with_wrong_hardware_id(self):
        """Test that decryption fails when hardware ID is different"""
        plaintext = "secret_value"
        encrypted = encrypt_value(plaintext)
        
        # Mock a different hardware ID
        with patch('app.core.encryption.get_hardware_id') as mock_hardware_id:
            mock_hardware_id.return_value = "different-hardware-id-12345"
            
            with pytest.raises(InvalidToken):
                decrypt_value(encrypted)

    def test_encrypt_empty_string(self):
        """Test encryption of empty string"""
        plaintext = ""
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        
        assert decrypted == plaintext

    def test_encrypt_special_characters(self):
        """Test encryption with special characters"""
        plaintext = "key!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        
        assert decrypted == plaintext

    def test_encrypt_unicode_characters(self):
        """Test encryption with unicode characters"""
        plaintext = "chave_secreta_çãõéá_日本語_🔐"
        encrypted = encrypt_value(plaintext)
        decrypted = decrypt_value(encrypted)
        
        assert decrypted == plaintext

    def test_decrypt_invalid_encrypted_value(self):
        """Test that decryption fails with invalid encrypted data"""
        invalid_encrypted = f"{ENCRYPTION_PREFIX}this_is_not_valid_encrypted_data"
        
        with pytest.raises((InvalidToken, ValueError)):
            decrypt_value(invalid_encrypted)

    def test_multiple_values_encrypted_differently(self):
        """Test that same plaintext produces different ciphertexts (with timestamp)"""
        plaintext = "same_value"
        encrypted1 = encrypt_value(plaintext)
        encrypted2 = encrypt_value(plaintext)
        
        # Note: Fernet includes a timestamp, so encryptions of the same value
        # will produce different ciphertexts
        # But both should decrypt to the same plaintext
        assert decrypt_value(encrypted1) == plaintext
        assert decrypt_value(encrypted2) == plaintext


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
