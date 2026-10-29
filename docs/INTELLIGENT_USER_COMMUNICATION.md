# Intelligent user communication

## What this adds

`UserCommunicationService` is the deterministic policy layer behind `NotificationService.communicate_user(...)`. A producer must supply a stable event key, a factual message, a priority, and (through the live `PresenceService`, when registered) presence. The policy does not invent context or invoke an LLM.

- **INFO / NORMAL:** Android notification, not speech.
- **URGENT / CRITICAL:** Android speech (`speak`) to allow interruption.
- **Presence `sleep` or `unknown`:** defer non-urgent messages. Urgent events remain eligible.
- **Reliability:** duplicate event keys are suppressed for five minutes; non-urgent delivery is throttled to four events per minute by default. Failed delivery is not marked sent.
- **Transport:** paired Android device uses the existing native WebSocket when connected; when disconnected, the existing Supabase mobile event queue is used. The Android client acknowledges queued event processing through the existing event protocol.

## Configuration and limits

Set `JARVIS_MOBILE_USER_ID` and `JARVIS_MOBILE_DEVICE_ID` in the backend runtime to the intended paired user/device. Do not put credentials in the Android app or source. The existing mobile notification endpoint's `JARVIS_MOBILE_NOTIFY_KEY` is not used by this internal dispatcher; the direct service resolves the authenticated bridge and existing server-side queue functions.

The presence integration reads `nexus.resolve("presence_service")` only if that component is actually registered. If absent or unavailable, presence is `unknown` and non-urgent messages are deferred. The rate limiter and deduplication cache are process-local, not durable across restarts or multiple workers. Durable deduplication and user-specific quiet hours require persistent policy storage and explicit user preferences before they can be claimed as supported.

## Current intelligence boundary

Implemented in this layer: event key deduplication, priority-based speech vs notification, presence-aware deferral, throttling, transport routing, and transport failure handling. Not yet connected: LLM-based message summarization/planning, calendar/task/context inference, user-specific quiet-hour schedules, cross-process durable dedupe, and adaptive learning from user feedback. Producers must pass grounded event content; the service does not manufacture facts.

## Example

```python
from app.application.services.user_communication_service import CommunicationPriority
from app.core.nexus import nexus

result = nexus.resolve("notification_service").communicate_user(
    event_key="backup:job-123:completed",
    message="O backup terminou e foi validado.",
    priority=CommunicationPriority.NORMAL,
)
```
