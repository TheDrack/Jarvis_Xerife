# Hardware-Based Encryption for Jarvis

## Overview

This security layer protects sensitive environment variables (API keys and database URLs) using hardware-based encryption. The encrypted values are bound to the specific machine where they were created, preventing unauthorized use if the `.env` file is copied to another computer.

## Features

- ✅ **Hardware-Bound Encryption**: Values are encrypted using a key derived from unique hardware identifiers (MAC address + platform info)
- ✅ **Automatic Encryption**: The setup wizard automatically encrypts sensitive values when saving the `.env` file
- ✅ **Automatic Decryption**: Settings are automatically decrypted when the application loads
- ✅ **Machine Portability Protection**: If the `.env` file is moved to a different machine, decryption fails and forces a new setup
- ✅ **Backward Compatible**: The system supports both encrypted and plain-text values

## How It Works

### 1. Hardware ID Generation

The system generates a unique hardware identifier by combining:
- MAC address (from `uuid.getnode()`)
- Platform information (OS and hostname)

This creates a fingerprint unique to each machine.

### 2. Key Derivation

A cryptographic key is derived from the hardware ID using PBKDF2-HMAC-SHA256 with:
- 600,000 iterations (OWASP 2023 recommendation)
- Fixed salt for deterministic key generation
- 32-byte key length

### 3. Encryption/Decryption

Values are encrypted using Fernet (symmetric encryption) from the `cryptography` library:
- Provides authenticated encryption
- Includes timestamp in ciphertext
- Base64-encoded output with `ENCRYPTED:` prefix

## Usage

### Setup Wizard

When running the setup wizard, sensitive values are automatically encrypted:

```bash
python -m app.adapters.infrastructure.setup_wizard
```

The wizard will:
1. Collect your API key and database URL
2. Encrypt these values using the hardware-based key
3. Save them to `.env` with the `ENCRYPTED:` prefix
4. Display a warning that the file is machine-specific

### Manual Encryption

You can also use the encryption utilities directly:

```python
from app.core.encryption import encrypt_value, decrypt_value

# Encrypt a value
api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
encrypted = encrypt_value(api_key)
# Returns: "ENCRYPTED:Z0FBQUFBQnBo..."

# Decrypt a value
decrypted = decrypt_value(encrypted)
# Returns: "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
```

### Loading Configuration

The Settings class automatically decrypts values when loading:

```python
from app.core.config import settings

# These values are automatically decrypted if encrypted
api_key = settings.gemini_api_key
database_url = settings.database_url
```

## .env File Format

After running the setup wizard, your `.env` file will look like:

```env
# Jarvis Assistant Configuration
# IMPORTANT: Sensitive values are encrypted with hardware-based key
# This .env file will only work on this machine

USER_ID=user_123
ASSISTANT_NAME=Jarvis

# LLM Settings (ENCRYPTED)
GEMINI_API_KEY=ENCRYPTED:Z0FBQUFBQnBoazJBdWUyOXdfTU9GdUxJQkRieXl4...

# Database Settings (ENCRYPTED)
DATABASE_URL=ENCRYPTED:Z0FBQUFBQnBoazJBVlZ6enhURl8tdVQ2TmZIWnUz...
```

## Security Considerations

### What is Protected

- ✅ **GEMINI_API_KEY**: Your Google Gemini API key
- ✅ **DATABASE_URL**: Your database connection string (may contain passwords)

### What is NOT Protected

- ❌ **USER_ID**: Not sensitive, stored in plain text
- ❌ **ASSISTANT_NAME**: Not sensitive, stored in plain text
- ❌ **Other configuration values**: Stored in plain text

### Threat Model

This security layer protects against:
- ✅ Accidental sharing of `.env` files (e.g., committing to Git)
- ✅ Unauthorized access if someone copies your `.env` file
- ✅ Use of stolen `.env` files on different machines

This does NOT protect against:
- ❌ Attackers with access to the same machine (they can derive the same key)
- ❌ Memory dumps while the application is running (decrypted values are in memory)
- ❌ Key loggers or malware on the same machine

### Best Practices

1. **Never commit `.env` files to version control** - Even though values are encrypted, it's still bad practice
2. **Use `.gitignore`** - Ensure `.env` is in your `.gitignore` file
3. **Rotate API keys regularly** - Encryption doesn't eliminate the need for key rotation
4. **Secure your machine** - The encryption is only as secure as the machine it runs on
5. **Use different API keys per environment** - Development, staging, and production should have separate keys

## Moving to a Different Machine

If you need to move Jarvis to a different machine:

1. **Do NOT copy the `.env` file** - The encrypted values won't work
2. **Run the setup wizard on the new machine**:
   ```bash
   python -m app.adapters.infrastructure.setup_wizard
   ```
3. **Enter your API key and database URL again** - They will be encrypted for the new machine

If you accidentally copy an encrypted `.env` file to a different machine, you'll see an error:
```
ValueError: Failed to decrypt GEMINI_API_KEY. 
The .env file may have been moved to a different machine. 
Please run the setup wizard again.
```

## Testing

Run the encryption tests:

```bash
# All encryption tests
pytest tests/test_encryption.py tests/test_encryption_integration.py tests/test_config_encryption.py -v

# Run the demonstration
python demo_encryption.py
```

## Technical Details

### Dependencies

- `cryptography >= 41.0.0` - For Fernet encryption and PBKDF2 key derivation

### Files

- `app/core/encryption.py` - Encryption utilities
- `app/core/config.py` - Settings with automatic decryption
- `app/adapters/infrastructure/setup_wizard.py` - Setup wizard with encryption
- `tests/test_encryption.py` - Encryption unit tests
- `tests/test_encryption_integration.py` - Integration tests
- `tests/test_config_encryption.py` - Configuration decryption tests
- `demo_encryption.py` - Interactive demonstration

### Algorithm Details

- **Key Derivation**: PBKDF2-HMAC-SHA256
- **Encryption**: Fernet (AES-128 in CBC mode + HMAC-SHA256)
- **Iterations**: 600,000 (OWASP 2023 recommendation)
- **Salt**: Fixed per application (`jarvis-hardware-encryption-v1`)
- **Hardware ID**: MAC address + platform info

## Troubleshooting

### Error: "Failed to decrypt GEMINI_API_KEY"

**Cause**: The `.env` file was created on a different machine or the hardware ID has changed.

**Solution**: Run the setup wizard again:
```bash
python -m app.adapters.infrastructure.setup_wizard
```

### Error: "ImportError: cannot import name 'PBKDF2'"

**Cause**: Incorrect cryptography library version.

**Solution**: Upgrade cryptography:
```bash
pip install --upgrade cryptography>=41.0.0
```

### Hardware ID Changed After System Update

**Cause**: Some system updates may change the MAC address or hostname.

**Solution**: Run the setup wizard again to regenerate the encrypted values.

## License

This security feature is part of the Jarvis Assistant project and follows the same license.
