# Examples and Demos

This directory contains example scripts and demonstrations of Jarvis features.

## Demo Scripts

### AI and LLM Features
- **demo_ai_gateway.py** - Demonstrates the AI Gateway with Gears System (multi-tier LLM fallback)
- **demo_gears_system.py** - Shows the Gears System in action (High Gear, Low Gear, Cannon Shot)
- **DEMO_AUTO_FIXER_ENHANCEMENTS.py** - Demonstrates auto-fixer enhancements for self-healing

### Self-Healing and GitHub Integration
- **demo_self_healing.py** - Demonstrates the self-healing workflow system
- Demo of auto-fixing CI failures and GitHub issue resolution

### System Features
- **demo_task_executor.py** - Example of the task executor and runner system
- **demo_extension_manager.py** - Shows dynamic package installation and management
- **demo_dependency_manager.py** - Demonstrates dependency management features
- **demo_xerife_strategist.py** - Shows the Xerife Strategist autonomous proposal system

### Security
- **demo_encryption.py** - Demonstrates the hardware-based encryption for sensitive configuration

## Running Examples

All demo scripts can be run directly from this directory:

```bash
# From the repository root
python docs/examples/demo_ai_gateway.py
python docs/examples/demo_self_healing.py
# etc.
```

Most demos will require proper environment setup (API keys, configuration, etc.).
Refer to the main [README.md](../../README.md) for setup instructions.

## Note

These are demonstration scripts intended for learning and testing.
For production usage, refer to the main application code in the `app/` directory
and the comprehensive test suite in `tests/`.
