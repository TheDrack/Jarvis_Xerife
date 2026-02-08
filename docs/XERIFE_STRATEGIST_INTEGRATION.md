# Integration Guide: Xerife Strategist + ThoughtLog

This guide shows how to integrate the Xerife Strategist with the existing ThoughtLog system for complete traceability of autonomous decision-making.

## Overview

The Xerife Strategist makes autonomous improvement decisions, while ThoughtLog tracks the reasoning process. Together, they provide:

1. **Decision Traceability**: Every proposal decision is logged
2. **ROI Tracking**: Historical ROI data for learning
3. **Failure Analysis**: Understanding why proposals were rejected
4. **Continuous Improvement**: Learn from past decisions

## Basic Integration

```python
import json

from app.application.services.strategist_service import StrategistService
from app.application.services.thought_log_service import ThoughtLogService
from app.domain.models.thought_log import InteractionStatus
from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
)

# Initialize services
strategist = StrategistService(default_budget_cap=10.0)
thought_log = ThoughtLogService()  # Assumes DB connection is configured

# Session and mission IDs
session_id = "session_123"
mission_id = "strategist_proposal_001"

# Create proposal
matrix = strategist.generate_viability_matrix(
    proposal_title="Add API Rate Limiting",
    proposal_description="Implement rate limiting to prevent API abuse",
    cost=CostEstimate(api_cost_usd=0.5, development_time_hours=2.0),
    impact=ImpactEstimate(
        error_reduction_percent=30.0,
        user_utility_level=ImpactLevel.HIGH,
    ),
    risk=RiskEstimate(
        risk_level=RiskLevel.LOW,
        mitigation_strategy="Add comprehensive tests",
    ),
)

# Log the internal monologue
thought_log.add_thought(
    mission_id=mission_id,
    session_id=session_id,
    status=InteractionStatus.INTERNAL_MONOLOGUE,
    thought_process=f"Analyzing proposal: ROI={matrix.calculate_roi():.2f}",
    problem_description=matrix.proposal_description,
    solution_attempt=f"Proposal {matrix.proposal_id} with scores - "
                     f"Cost:{matrix.cost.total_cost_score():.1f}, "
                     f"Impact:{matrix.impact.total_impact_score():.1f}, "
                     f"Risk:{matrix.risk.total_risk_score():.1f}",
    success=matrix.is_viable(),
    error_message="" if matrix.is_viable() else matrix.rejection_reason,
    context_data=json.dumps(matrix.to_dict()),
)

# Archive proposal
strategist.archive_proposal(matrix)

# If approved, generate RFC and log user interaction
if matrix.is_viable():
    rfc_path = strategist.generate_rfc(matrix)
    prompt = strategist.format_decision_prompt(matrix)
    
    # Log the user interaction request
    thought_log.add_thought(
        mission_id=mission_id,
        session_id=session_id,
        status=InteractionStatus.USER_INTERACTION,
        thought_process="Requesting commander approval for implementation",
        problem_description=f"RFC generated: {rfc_path}",
        solution_attempt=prompt,
        success=True,
        context_data=json.dumps({"rfc_path": str(rfc_path), "proposal_id": matrix.proposal_id}),
    )
```

## Advanced: Budget Tracking with ThoughtLog

```python
from app.application.services.task_runner import TaskRunner

# Initialize TaskRunner with budget tracking
runner = TaskRunner(
    sandbox_mode=True,
    budget_cap_usd=50.0,
)

# Execute a mission and log costs
def execute_with_logging(mission, session_id):
    """Execute mission and log costs to ThoughtLog"""
    
    # Execute
    result = runner.execute_mission(mission)
    
    # Estimate cost (example: $0.002 per 1000 tokens)
    # In real implementation, you'd get actual token count from LLM API
    estimated_tokens = len(mission.code) * 2  # Rough estimate
    cost = (estimated_tokens / 1000) * 0.002
    
    # Track in runner
    runner.track_mission_cost(mission.mission_id, cost)
    
    # Log to ThoughtLog
    budget_status = runner.get_budget_status()
    
    thought_log.add_thought(
        mission_id=mission.mission_id,
        session_id=session_id,
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        thought_process=f"Mission executed with cost ${cost:.4f}",
        problem_description=f"Budget status: ${budget_status['total_cost_usd']:.2f} / "
                          f"${budget_status['budget_cap_usd']:.2f}",
        solution_attempt=f"Mission result: {'success' if result.success else 'failed'}",
        success=result.success and budget_status['within_budget'],
        error_message="" if budget_status['within_budget'] else "Budget cap exceeded",
        context_data=json.dumps({
            "cost_usd": cost,
            "budget_status": budget_status,
            "mission_result": result.to_dict(),
        }),
    )
    
    return result
```

## Automatic Refactoring from Error Logs

```python
# Fetch error logs from ThoughtLog
def analyze_and_propose_refactoring(session_id):
    """Analyze ThoughtLog errors and generate refactoring proposals"""
    
    # Get failed missions from ThoughtLog
    failed_thoughts = thought_log.get_failed_attempts(session_id)
    
    # Convert to error log format
    error_logs = []
    error_counts = {}
    
    for thought in failed_thoughts:
        error_key = f"{thought.error_message[:50]}"
        if error_key not in error_counts:
            error_counts[error_key] = {
                "error_message": thought.error_message,
                "error_type": "RuntimeError",  # Extract from context_data if available
                "count": 0,
            }
        error_counts[error_key]["count"] += 1
    
    error_logs = list(error_counts.values())
    
    # Analyze with Strategist
    suggestions = strategist.analyze_error_logs(error_logs)
    
    # Create proposals for high-value refactorings
    for suggestion in suggestions:
        # Extract error pattern from suggestion
        # Create a proposal for fixing it
        matrix = strategist.generate_viability_matrix(
            proposal_title=f"Fix recurring error pattern",
            proposal_description=suggestion,
            cost=CostEstimate(
                api_cost_usd=0.5,
                development_time_hours=1.5,
                code_complexity="simple",
            ),
            impact=ImpactEstimate(
                error_reduction_percent=50.0,
                user_utility_level=ImpactLevel.MEDIUM,
                technical_debt_reduction=True,
            ),
            risk=RiskEstimate(
                risk_level=RiskLevel.LOW,
                mitigation_strategy="Add unit tests for edge cases",
            ),
        )
        
        # Log the refactoring proposal
        thought_log.add_thought(
            mission_id=f"refactoring_{matrix.proposal_id}",
            session_id=session_id,
            status=InteractionStatus.INTERNAL_MONOLOGUE,
            thought_process="Automatic refactoring proposal based on error analysis",
            problem_description=suggestion,
            solution_attempt=f"ROI: {matrix.calculate_roi():.2f}",
            success=matrix.is_viable(),
            context_data=json.dumps(matrix.to_dict()),
        )
        
        if matrix.is_viable():
            strategist.archive_proposal(matrix)
            print(f"✅ Refactoring proposal approved: {matrix.proposal_title}")
```

## Periodic Analysis Task

Here's a complete example of a periodic task that analyzes errors and generates proposals:

```python
import schedule
import time

def periodic_strategist_analysis():
    """Run periodic analysis and generate improvement proposals"""
    
    # Get last 24 hours of sessions
    recent_sessions = get_recent_sessions(hours=24)
    
    for session_id in recent_sessions:
        # Analyze errors
        analyze_and_propose_refactoring(session_id)
        
        # Check budget status
        budget_status = runner.get_budget_status()
        
        if not budget_status['within_budget']:
            # Log budget exceeded
            thought_log.add_thought(
                mission_id="budget_monitor",
                session_id=session_id,
                status=InteractionStatus.INTERNAL_MONOLOGUE,
                thought_process="Budget cap exceeded, aborting new missions",
                problem_description=f"Used ${budget_status['total_cost_usd']:.2f} of "
                                  f"${budget_status['budget_cap_usd']:.2f}",
                solution_attempt="Waiting for budget reset or manual approval",
                success=False,
                requires_human=True,
                escalation_reason="Budget cap exceeded",
            )

# Schedule analysis every 6 hours
schedule.every(6).hours.do(periodic_strategist_analysis)

# Run scheduler
while True:
    schedule.run_pending()
    time.sleep(60)
```

## Query Examples

### Get all proposals with ROI > 2.0

```python
# Query ThoughtLog for high-ROI proposals
high_roi_thoughts = [
    thought for thought in thought_log.get_all_thoughts()
    if thought.status == InteractionStatus.INTERNAL_MONOLOGUE
    and "ROI=" in thought.solution_attempt
    and float(thought.solution_attempt.split("ROI=")[1].split()[0]) > 2.0
]
```

### Get budget history

```python
budget_thoughts = [
    thought for thought in thought_log.get_all_thoughts()
    if "budget_status" in thought.context_data
]

for thought in budget_thoughts:
    data = json.loads(thought.context_data)
    budget = data.get("budget_status", {})
    print(f"{thought.created_at}: ${budget.get('total_cost_usd', 0):.2f}")
```

## Best Practices

1. **Always log INTERNAL_MONOLOGUE for proposals**: This keeps user interface clean while maintaining audit trail

2. **Use context_data for detailed information**: Store complete matrix.to_dict() for future analysis

3. **Set requires_human=True for critical decisions**: Budget exceeded, high-risk proposals, etc.

4. **Track ROI over time**: Compare estimated vs actual ROI after implementation

5. **Periodic cleanup**: Archive old proposals and thoughts after 30+ days

## Integration with Existing Services

The Strategist integrates seamlessly with:

- **AssistantService**: For LLM-based proposal generation
- **TaskRunner**: For sandboxed testing and budget tracking
- **ThoughtLogService**: For decision audit trail
- **DeviceService**: For capability-based proposal routing
- **GithubWorker**: For automatic PR creation (future enhancement)

## Security Considerations

1. **Budget Cap**: Always set a reasonable budget cap
2. **Sandbox Mode**: Always use sandbox for untrusted code
3. **Human Approval**: Never auto-merge to main branch
4. **Risk Assessment**: Reject CRITICAL risk without mitigation
5. **Audit Trail**: Keep all proposals (approved + rejected) for compliance

## Future Enhancements

1. **Machine Learning**: Train on historical ROI data
2. **A/B Testing**: Compare estimated vs actual outcomes
3. **Dashboard**: Visual interface for proposal management
4. **Automatic PR Creation**: Integration with GitHub API
5. **Slack/Email Notifications**: Alert on budget exceeded or high-ROI proposals
