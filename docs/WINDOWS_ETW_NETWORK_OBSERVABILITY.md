# Windows ETW network observability

## Current capability

`network_capture_etw(duration_seconds=10, keywords="0xFFFFFFFFFFFFFFFF")` is an on-demand MCP tool backed by `windows_etw_network_adapter.py`. It captures the Microsoft-Windows-TCPIP ETW provider, stops only the uniquely named session created by that invocation, converts the bounded ETL with `tracerpt`, and returns structured events.

- Duration: 1–60 seconds per call; ETL file capped at 32 MB by logman and converted XML capped at 128 MB.
- Provider: `Microsoft-Windows-TCPIP`, GUID `{2F07E2EE-15DB-40F1-90EF-9D7BA282188A}`.
- Default: broad uint64 keyword mask and ETW level 5; callers may narrow the mask.
- Preserves provider metadata, event ID/version/task/opcode, timestamp, activity ID, system PID/TID, and all named EventData fields.
- Event 1300 normalization includes local/remote endpoints, raw TCP state, normalized state name, owning PID, and ProcessStartKey.
- No packet payload capture. `events_lost` and `buffers_lost` remain null unless a future backend exposes trustworthy counters.
- Temporary ETL/XML artifacts are deleted when the call ends. This first version does not retain history or run persistently.

## Solicitation tiers

Network capabilities should distinguish passive telemetry, on-demand inspection, bounded active probes, continuous observation, and intervention. Broad acquisition is permitted where the source and host are authorized, but each consumer subscribes only to the event classes it needs. The future Sentinela worker may own scheduled/continuous capture and policy-based alerting; the main Jarvis agent should query or request summaries rather than parse every event continuously.

Active probes must retain their own scope, rate, timeout, and protocol-specific safety constraints. A broad ETW keyword mask does not authorize broad network scanning, credential attempts, packet injection, or firewall/configuration changes.

## Validation evidence

On the development Windows host, a 2-second live capture completed successfully: 1,804 TCPIP events, 245,760-byte ETL, 2,709,287-byte XML, and no reported stop/conversion error. Event 1300 records included LocalAddress, RemoteAddress, State, Pid, and ProcessStartKey. ETW loss counters were unavailable in this output and are reported as unknown, not zero. This validates the local Windows capture path; it is not a claim of compatibility with every Windows build or every network workload.

## TCP state mapping

The numeric values are decoded using Microsoft's `MIB_TCP_STATE` enumeration: 1 CLOSED, 2 LISTEN, 3 SYN_SENT, 4 SYN_RECEIVED, 5 ESTABLISHED, 6 FIN_WAIT_1, 7 FIN_WAIT_2, 8 CLOSE_WAIT, 9 CLOSING, 10 LAST_ACK, 11 TIME_WAIT, and 12 DELETE_TCB. The original raw value is retained alongside the normalized name. See [Microsoft Learn: MIB_TCP_STATE](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rrasm/882bec9c-2fb6-4acd-a9b6-dabcab1ac0d6).

## Known limitations / next iteration

- Uses `logman` + `tracerpt` file conversion; not a live streaming consumer.
- No durable event store, rotation, retention policy, process-name enrichment, or Sentinela rules yet.
- Loss counters are unknown because the current tracerpt XML output did not expose reliable values.
- Capture size is checked after the session stops; a future persistent worker needs a bounded circular ETW session and rotation/retention controls.
- Event 1300 is normalized; other TCPIP events remain generic and preserve their named fields.