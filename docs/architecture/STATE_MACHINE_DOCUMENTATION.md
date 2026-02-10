# Self-Healing State Machine - Documentation

## Overview

The Self-Healing State Machine is an autonomous error-fixing system that follows strict rules for identifying, categorizing, and attempting to repair errors in the codebase.

## Architecture

### States

The state machine has four possible states:

1. **CHANGE_REQUESTED** - Error identified and can be auto-fixed
2. **NEEDS_HUMAN** - Error requires human intervention
3. **SUCCESS** - Fix applied successfully (pytest passed)
4. **FAILED_LIMIT** - Maximum repair attempts reached (3 attempts)

### State Diagram

```
                     ┌──────────────────┐
                     │  Error Detected  │
                     └────────┬─────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Identify Error     │
                    │  (State Machine)    │
                    └──────┬───────┬──────┘
                           │       │
          Auto-fixable     │       │     Infrastructure/Unknown
          (AssertionError, │       │     (Timeout, HTTP 429/500/503,
           ImportError,    │       │      ConnectionError, Unknown)
           NameError,      │       │
           SyntaxError,    │       │
           LogicError)     │       │
                           │       │
                           ▼       ▼
              ┌──────────────┐  ┌──────────────┐
              │CHANGE_       │  │NEEDS_HUMAN   │
              │REQUESTED     │  │              │
              └──────┬───────┘  └──────────────┘
                     │                 │
                     │                 └──> Human notification
                     │
                     ▼
         ┌──────────────────────────┐
         │  Repair Cycle            │
         │  (Counter: 0-3)          │
         └──┬───────────────────┬───┘
            │                   │
            │  Success          │  Failure
            ▼                   ▼
    ┌──────────────┐    ┌──────────────┐
    │  SUCCESS     │    │ Increment    │
    │              │    │ Counter      │
    └──────────────┘    └──────┬───────┘
                                │
                                ▼
                        Counter == Limit?
                                │
                    Yes ────────┼──────── No
                    │                    │
                    ▼                    │
            ┌──────────────┐             │
            │FAILED_LIMIT  │             │
            └──────────────┘             │
                    │                    │
                    └────────────────────┘
                           │
                           └──> Retry repair
```

## Error Identification Rules

### Auto-Fixable Errors → CHANGE_REQUESTED

The following error types are considered auto-fixable:
- `AssertionError` - Test assertion failures
- `ImportError` - Missing or incorrect imports
- `NameError` - Undefined variables or functions
- `SyntaxError` - Python syntax errors
- `LogicError` - Application logic errors

### Infrastructure Errors → NEEDS_HUMAN (Falha de Infra)

The following error patterns indicate infrastructure issues:
- `Timeout` / `TimeoutError` - Connection or operation timeouts
- `ConnectionError` / `ConnectTimeout` / `ReadTimeout` - Network connectivity issues
- `HTTP 429` - Too Many Requests (rate limiting)
- `HTTP 500` - Internal Server Error
- `HTTP 503` - Service Unavailable

### Unknown Errors → NEEDS_HUMAN (Erro não identificado)

Any error that doesn't match the above patterns is classified as unidentified and requires human review.

## Repair Cycle

The repair cycle follows these rules:

1. **Counter** starts at 0
2. **Limit** is set to 3 (configurable)
3. **While** state is `CHANGE_REQUESTED` and counter < limit:
   - Generate minimal patch (1 file, 1 fix at a time)
   - Apply patch to the file
   - Run pytest to validate the fix
   - **If** pytest passes → state = `SUCCESS`
   - **If** pytest fails → increment counter
   - **If** counter == limit → state = `FAILED_LIMIT`

### Code Restrictions

- **Prohibited**: Refactoring files not mentioned in the traceback
- **Prohibited**: Creating logic outside the scope of the failed test
- **Required**: Minimal changes (1 file, 1 fix per attempt)

## Usage

### Standard Mode (Original Behavior)

```bash
export ISSUE_BODY="Error: NameError in file app/main.py..."
export ISSUE_NUMBER="123"
python scripts/auto_fixer_logic.py
```

### State Machine Mode (With Pytest Report)

```bash
# Run tests with JSON report
pytest --json-report --json-report-file=report.json

# Run auto-fixer with state machine
python scripts/auto_fixer_logic.py --state report.json
```

### GitHub Actions Workflow

The workflow is configured in `.github/workflows/jarvis_code_fixer.yml`:

```yaml
- name: Run Pytest (The Judge)
  run: |
    pytest --json-report --json-report-file=report.json || echo "TESTS_FAILED=true" >> $GITHUB_ENV

- name: Self-Healing Logic
  if: env.TESTS_FAILED == 'true'
  run: python scripts/auto_fixer_logic.py --state report.json
```

## API Reference

### SelfHealingStateMachine Class

#### Constructor

```python
SelfHealingStateMachine(limit: int = 3)
```

**Parameters:**
- `limit` (int): Maximum number of repair attempts (default: 3)

#### Methods

##### identify_error(error_message: str, traceback: Optional[str] = None) -> State

Identifies the error type and sets the appropriate state.

**Parameters:**
- `error_message` (str): The error message
- `traceback` (Optional[str]): Optional traceback information

**Returns:**
- `State`: The new state (CHANGE_REQUESTED, NEEDS_HUMAN)

##### can_attempt_repair() -> bool

Checks if a repair attempt can be made.

**Returns:**
- `bool`: True if state is CHANGE_REQUESTED and counter < limit

##### record_repair_attempt(success: bool) -> State

Records a repair attempt and updates the state.

**Parameters:**
- `success` (bool): Whether the repair was successful (pytest passed)

**Returns:**
- `State`: The new state (SUCCESS, CHANGE_REQUESTED, or FAILED_LIMIT)

##### get_status() -> Dict[str, any]

Gets the current status of the state machine.

**Returns:**
- `dict`: Dictionary containing:
  - `state` (str): Current state value
  - `counter` (int): Current attempt counter
  - `limit` (int): Maximum attempts
  - `failure_reason` (str|None): Reason for NEEDS_HUMAN state
  - `error_type` (str|None): Identified error type
  - `can_repair` (bool): Whether repair can be attempted

##### should_notify_human() -> bool

Checks if human notification is needed.

**Returns:**
- `bool`: True if state is NEEDS_HUMAN or FAILED_LIMIT

##### get_final_message() -> str

Gets a human-readable message describing the final state.

**Returns:**
- `str`: Formatted message in Portuguese

## Examples

### Example 1: Successful Auto-Fix

```python
from scripts.state_machine import SelfHealingStateMachine

# Initialize
machine = SelfHealingStateMachine()

# Identify error
machine.identify_error("NameError: name 'user_id' is not defined")
# State: CHANGE_REQUESTED

# Attempt 1: Fix applied
machine.record_repair_attempt(success=True)
# State: SUCCESS

print(machine.get_final_message())
# Output: "✅ Auto-reparo concluído com sucesso após 1 tentativa(s)"
```

### Example 2: Infrastructure Error

```python
from scripts.state_machine import SelfHealingStateMachine

# Initialize
machine = SelfHealingStateMachine()

# Identify error
machine.identify_error("TimeoutError: Connection timed out after 30s")
# State: NEEDS_HUMAN

print(machine.should_notify_human())
# Output: True

print(machine.get_final_message())
# Output: "⚠ Intervenção humana necessária.\n   Motivo: Falha de Infra..."
```

### Example 3: Failed Limit

```python
from scripts.state_machine import SelfHealingStateMachine

# Initialize
machine = SelfHealingStateMachine(limit=3)

# Identify error
machine.identify_error("AssertionError: Expected 5 but got 3")
# State: CHANGE_REQUESTED

# Three failed attempts
machine.record_repair_attempt(success=False)  # Attempt 1
machine.record_repair_attempt(success=False)  # Attempt 2
machine.record_repair_attempt(success=False)  # Attempt 3
# State: FAILED_LIMIT

print(machine.get_final_message())
# Output: "❌ Limite de tentativas atingido (3).\n   Intervenção manual necessária..."
```

## Testing

Run the state machine tests:

```bash
pytest tests/test_state_machine.py -v
```

Test coverage includes:
- ✅ Error identification (11 tests)
- ✅ Repair cycle logic (9 tests)
- ✅ State status and reporting (8 tests)

**Total: 28 tests, all passing**

## Integration with Existing System

The state machine integrates seamlessly with the existing auto-fixer:

1. **Backward Compatibility**: Standard mode (without `--state`) works as before
2. **New Mode**: State machine mode (with `--state`) adds intelligent error handling
3. **GitHub Actions**: Updated workflow uses state machine for pull requests and issues
4. **Error Tracking**: Existing healing attempt tracking still works
5. **GitHub Copilot**: Still uses GitHub Copilot CLI for generating fixes

## Monitoring and Debugging

### GitHub Actions Outputs

The workflow sets the `final_state` output variable:

```yaml
- name: Check Final State
  run: |
    echo "Final State: ${{ steps.healing_engine.outputs.final_state }}"
```

Possible values:
- `SUCCESS` - Auto-fix completed successfully
- `FAILED_LIMIT` - Maximum attempts reached
- `NEEDS_HUMAN` - Human intervention required

### Logs

The state machine provides detailed logging:

```
🤖 State Machine Status:
   State: CHANGE_REQUESTED
   Error Type: AssertionError
   Counter: 0/3
   
🔧 Repair Attempt 1/3
...
✅ Auto-reparo concluído com sucesso após 1 tentativa(s)
```

## Security Considerations

- **Infinite Loop Prevention**: Hard limit of 3 attempts
- **Minimal Changes**: Only modifies files mentioned in traceback
- **Test Validation**: Every fix must pass pytest before being committed
- **Human Escalation**: Infrastructure and unknown errors escalate to humans

## Future Enhancements

Potential improvements to consider:

1. **Machine Learning**: Learn from successful fixes to improve future attempts
2. **Parallel Testing**: Test multiple fix strategies in parallel
3. **Rollback**: Automatic rollback if fix causes new failures
4. **Metrics**: Track success rates by error type
5. **Custom Error Patterns**: Allow users to define custom auto-fixable patterns

## Support

For issues or questions:
1. Check the logs in GitHub Actions
2. Review the test failures in `report.json`
3. Open an issue with label `manual-intervention-required`
4. Include the `final_state` and error details

## License

This implementation is part of the Jarvis Assistant project.
