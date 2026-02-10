# JARVIS Self-Awareness Module (Capability Manager)

## Overview

The JARVIS Self-Awareness Module is the foundational intelligence layer that enables JARVIS to understand its own capabilities, identify gaps, and guide its own evolution. Based on the JARVIS_OBJECTIVES_MAP, this module tracks 102 capabilities across 9 chapters - from basic foundation to Marvel-level AI.

This implementation answers the question: **"How does JARVIS know what it can do, what it cannot do, and what it needs to become more capable?"**

## Architecture

### Core Components

1. **Capabilities Database** (`jarvis_capabilities` table)
   - Tracks all 102 capabilities with status (nonexistent/partial/complete)
   - Stores technical requirements and implementation logic
   - PostgreSQL/SQLite compatible schema

2. **CapabilityManager Service**
   - Intelligence layer for self-awareness
   - Analyzes capabilities and generates technical blueprints
   - Scans repository to detect existing functionality
   - Determines next evolution steps

3. **Evolution API Endpoints**
   - Real-time progress tracking
   - Self-evolution triggers
   - Technical requirement analysis

## The 9 Chapters

### CHAPTER 1: Immediate Foundation (15 capabilities)
Core self-awareness infrastructure: capability inventory, gap detection, objective generation, testing, and documentation.

### CHAPTER 2: Functional Self-Awareness (11 capabilities)
Recognition of existing/missing capabilities, dependency mapping, impact analysis, and performance monitoring.

### CHAPTER 3: Contextual Understanding (12 capabilities)
Memory systems (short/mid/long-term), intention inference, user modeling, and context recognition.

### CHAPTER 4: Strategic Reasoning (11 capabilities)
Multi-step planning, strategy comparison, consequence simulation, risk evaluation, and decision-making.

### CHAPTER 5: Advanced Execution and Orchestration (11 capabilities)
Multi-agent orchestration, parallel execution, real-time monitoring, and distributed operation.

### CHAPTER 6: Directed Learning (11 capabilities)
Learning from failures/successes, strategy reinforcement, feedback loops, and optimization.

### CHAPTER 7: Economic Intelligence (12 capabilities)
Cost-benefit analysis, value generation, resource allocation, and economic sustainability.

### CHAPTER 8: Self-Protection and Containment (10 capabilities)
Anomaly detection, operational limits, safety mechanisms, and audit logging.

### CHAPTER 9: Marvel-level JARVIS (9 capabilities)
Proactive assistance, need anticipation, continuous evolution, and cognitive copilot functions.

## API Endpoints

### GET /v1/status/evolution

Get overall evolution progress and chapter-by-chapter breakdown.

**Response:**
```json
{
  "overall_progress": 1.96,
  "total_capabilities": 102,
  "complete_capabilities": 1,
  "partial_capabilities": 2,
  "nonexistent_capabilities": 99,
  "chapters": [
    {
      "chapter": "CHAPTER_1_IMMEDIATE_FOUNDATION",
      "total": 15,
      "complete": 1,
      "partial": 2,
      "nonexistent": 12,
      "progress_percentage": 10.0
    }
  ]
}
```

### GET /v1/evolution/next-step

Get the next capability JARVIS should implement (self-evolution trigger).

**Response:**
```json
{
  "capability_id": 1,
  "capability_name": "Maintain internal inventory of all known capabilities",
  "chapter": "CHAPTER_1_IMMEDIATE_FOUNDATION",
  "current_status": "nonexistent",
  "blueprint": {
    "capability_id": 1,
    "requirements": ["Persistent storage system"],
    "libraries": ["sqlalchemy", "redis"],
    "apis": [],
    "env_vars": [],
    "blueprint": "Implement using PostgreSQL for inventory persistence"
  },
  "priority_score": 1001
}
```

### POST /v1/evolution/scan

Scan the repository to detect which capabilities are already implemented.

**Response:**
```json
{
  "total_capabilities": 102,
  "nonexistent": 99,
  "partial": 2,
  "complete": 1,
  "updated": [
    {
      "id": 1,
      "name": "Maintain internal inventory of all known capabilities",
      "old_status": "nonexistent",
      "new_status": "complete"
    }
  ]
}
```

### GET /v1/evolution/requirements/{capability_id}

Get technical requirements and blueprint for a specific capability.

**Response:**
```json
{
  "capability_id": 72,
  "capability_name": "Evaluate cost of each executed action",
  "chapter": "CHAPTER_7_ECONOMIC_INTELLIGENCE",
  "status": "nonexistent",
  "requirements": ["Payment processing system"],
  "libraries": ["stripe"],
  "apis": ["Stripe API"],
  "env_vars": ["STRIPE_API_KEY"],
  "permissions": [],
  "blueprint": "Integrate with Stripe for payment tracking and processing"
}
```

## Installation & Setup

### 1. Database Setup

The `jarvis_capabilities` table is automatically created when the application starts.

For manual creation (e.g., Supabase):
```bash
psql -h your-host -d your-database -U your-user -f migrations/001_create_jarvis_capabilities.sql
```

### 2. Populate Capabilities

```bash
PYTHONPATH=/path/to/project python migrations/populate_capabilities.py
```

This loads all 102 capabilities from `data/capabilities.json` into the database.

### 3. Verify Installation

Start the API server:
```bash
python serve.py
```

Check evolution status:
```bash
curl http://localhost:8000/v1/status/evolution
```

## Usage Examples

### Example 1: Check Overall Progress

```python
import requests

response = requests.get("http://localhost:8000/v1/status/evolution")
data = response.json()

print(f"Overall Progress: {data['overall_progress']}%")
print(f"Complete: {data['complete_capabilities']}")
print(f"Partial: {data['partial_capabilities']}")
print(f"Not Started: {data['nonexistent_capabilities']}")
```

### Example 2: Get Next Evolution Step

```python
response = requests.get("http://localhost:8000/v1/evolution/next-step")
next_step = response.json()

print(f"Next to implement: {next_step['capability_name']}")
print(f"Chapter: {next_step['chapter']}")
print(f"Blueprint: {next_step['blueprint']['blueprint']}")
print(f"Required libraries: {next_step['blueprint']['libraries']}")
```

### Example 3: Scan for Existing Capabilities

```python
response = requests.post("http://localhost:8000/v1/evolution/scan")
scan_results = response.json()

print(f"Detected {len(scan_results['updated'])} capabilities")
for update in scan_results['updated']:
    print(f"  - {update['name']}: {update['old_status']} -> {update['new_status']}")
```

### Example 4: Check Requirements for a Capability

```python
# Check requirements for capability #72 (cost evaluation)
response = requests.get("http://localhost:8000/v1/evolution/requirements/72")
requirements = response.json()

print(f"Capability: {requirements['capability_name']}")
print(f"Status: {requirements['status']}")
print(f"Required libraries: {requirements['libraries']}")
print(f"Required APIs: {requirements['apis']}")
print(f"Required env vars: {requirements['env_vars']}")
print(f"Blueprint: {requirements['blueprint']}")
```

## Intelligence Layer: How It Works

### Blueprint Generation

The `check_requirements()` method uses rule-based logic to generate technical blueprints:

- **Memory capabilities** → Suggests Redis + PostgreSQL
- **Learning capabilities** → Suggests scikit-learn + numpy
- **Economic capabilities** → Suggests Stripe integration
- **Monitoring capabilities** → Suggests Prometheus + Sentry
- **Strategic capabilities** → Suggests LLM integration
- **Orchestration capabilities** → Suggests Celery + Redis

### Capability Detection

The `status_scan()` method includes detectors for specific capabilities:

1. **Capability #1 (Inventory)**: Checks if `capabilities.json` exists and database is populated
2. **Capability #2 (Classification)**: Checks if status field is being used
3. **Capability #16 (Recognition)**: Checks if detector methods exist

More detectors can be added by extending the `_capability_detectors` dictionary.

### Resource Checking

The `resource_request()` method verifies:

- **Environment variables**: Checks if required env vars are set
- **Libraries**: Attempts to import required Python packages
- **APIs**: Validates API access (future enhancement)

### Self-Evolution

The `get_next_evolution_step()` method:

1. Queries all incomplete capabilities
2. Checks if requirements are satisfied
3. Prioritizes by chapter and ID (lower = higher priority)
4. Returns the first ready-to-implement capability

## Integration with JARVIS

### Initialization Hook

Add to JARVIS initialization:

```python
from app.application.services.capability_manager import CapabilityManager

# During startup
capability_manager = CapabilityManager(engine=db_engine)
next_evolution = capability_manager.get_next_evolution_step()

if next_evolution:
    logger.info(f"Next evolution target: {next_evolution['capability_name']}")
```

### Periodic Scanning

Run capability scans periodically:

```python
import schedule

def scan_capabilities():
    results = capability_manager.status_scan()
    logger.info(f"Scan complete: {results['complete']} complete, {results['partial']} partial")

# Scan every hour
schedule.every().hour.do(scan_capabilities)
```

### HUD Integration

Display evolution progress in the JARVIS HUD:

```javascript
// Fetch evolution status
fetch('/v1/status/evolution')
  .then(response => response.json())
  .then(data => {
    updateProgressBar(data.overall_progress);
    updateChapterBreakdown(data.chapters);
  });
```

## Extending the System

### Adding New Capability Detectors

To add detection logic for a capability:

```python
def _detect_my_capability(self) -> str:
    """Detect if my capability is implemented"""
    # Check for specific files, imports, or functionality
    if os.path.exists("/path/to/feature"):
        return "complete"
    elif some_partial_condition:
        return "partial"
    return "nonexistent"

# Register in _initialize_detectors()
self._capability_detectors[capability_id] = self._detect_my_capability
```

### Customizing Blueprint Generation

Extend the `_generate_blueprint()` method:

```python
# Add custom pattern matching
if "custom_pattern" in name_lower:
    blueprint["libraries"].append("my-library")
    blueprint["requirements"].append("Custom requirement")
    blueprint["blueprint"] = "Custom implementation approach"
```

## Development Roadmap

### Phase 1: Foundation (Complete ✅)
- [x] Database schema and migration
- [x] CapabilityManager core service
- [x] Evolution API endpoints
- [x] Unit tests (87% coverage)

### Phase 2: Intelligence Enhancement
- [ ] AI-powered blueprint generation using LLM
- [ ] Automatic code analysis for capability detection
- [ ] Dependency graph visualization
- [ ] Impact analysis for capability changes

### Phase 3: Self-Evolution
- [ ] Automatic PR generation for next evolution step
- [ ] Self-healing when capabilities degrade
- [ ] A/B testing for capability implementations
- [ ] Learning from implementation success/failure

### Phase 4: Advanced Features
- [ ] Capability marketplace (community contributions)
- [ ] Version tracking for capabilities
- [ ] Capability rollback mechanisms
- [ ] Multi-JARVIS capability synchronization

## Testing

Run the full test suite:
```bash
pytest tests/test_capability_manager.py -v
```

Run all tests:
```bash
pytest tests/ -v --cov=app
```

Expected results:
- 12 CapabilityManager tests
- 87% code coverage on CapabilityManager
- All 509+ total tests passing

## Troubleshooting

### Database Connection Issues

If you get database errors:
1. Check DATABASE_URL environment variable
2. Ensure PostgreSQL/SQLite is accessible
3. Run the population script manually

### Missing Capabilities in Database

If `/v1/status/evolution` returns 0 capabilities:
```bash
PYTHONPATH=/path/to/project python migrations/populate_capabilities.py
```

### API Endpoint Not Found

If evolution endpoints return 404:
1. Ensure you're running the latest code
2. Check that api_server.py includes evolution endpoints
3. Restart the API server

## Contributing

To contribute new capability detectors or blueprint generators:

1. Add your detector method to `CapabilityManager`
2. Register it in `_initialize_detectors()`
3. Write unit tests for the new detector
4. Update this documentation

## License

Part of the JARVIS project. See main LICENSE file.

## Credits

Developed as part of the JARVIS Self-Awareness initiative to create a truly autonomous AI assistant capable of understanding and evolving its own capabilities.

---

**"The first step to intelligence is knowing what you don't know."**  
— JARVIS Capability Manager
