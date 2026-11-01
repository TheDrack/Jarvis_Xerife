# Jarvis OS — Host Foundation 0.1

## Scope

This milestone adds a read-only, opt-in Host integration boundary to the existing
Jarvis harness. It does not change the default harness startup path or grant
privileged access.

## Contracts

app/domain/ports/host_port.py defines immutable, OS-neutral snapshots for host
identity, CPU, memory and mounted-disk telemetry, and a bounded process inventory
without command-line arguments or environment data.

HostPort is the only interface the application layer should consume. The
PsutilHostAdapter is an optional Windows/Linux implementation isolated under
app/adapters/edge/host/.

## Dependency and activation

Install the optional dependency with:

    python -m pip install -r requirements/host.txt

The adapter is not imported by the portable Harness by default. Do not make
psutil a mandatory dependency of requirements/core.txt.

## Security and resource properties

- The initial adapter is read-only.
- The returned process inventory is limited to 1..500 records.
- Process selection traverses the process table but retains only O(limit)
  intermediate records using top-N selection; scan time still depends on the
  total number of processes visible to the host.
- Command lines, environment variables, open files and credentials are not
  collected.
- Per-process access-denied, vanished and zombie processes are skipped.
- No shell execution, service mutation, process termination or privilege
  elevation is exposed by this contract.

## Sampling and integration constraints

- psutil's first `Process.cpu_percent(interval=None)` sample for a process is
  documented as an unusable `0.0` warm-up value. The first process inventory
  may therefore be ranked primarily by RSS; callers should collect a later
  snapshot before treating CPU ranking as meaningful.
- `get_resources()` currently calls `psutil.cpu_percent(interval=0.1)`, which
  blocks the calling thread for the sampling interval. Do not call this
  synchronous adapter directly from an async event loop; the future Host
  application service must offload blocking telemetry to a worker thread or
  expose an asynchronous facade.
- Host integration is not connected to the composition root/API in this
  milestone, so these constraints do not currently block the portable Harness.

## Next increments

1. Add explicit Host profile registration and permission checks.
2. Add typed device discovery contracts and adapters.
3. Add a separate privileged-operation broker with policy evaluation and audit.
4. Add service lifecycle supervision and recovery.
5. Validate the complete Host profile in clean Linux and Windows environments.
6. Build the Ubuntu Server LTS + XFCE image only after the Host profile and
   recovery path pass VM acceptance tests.

## Evidence status

The contracts and adapter implementation are code-level deliverables. They
must not be described as runtime-integrated until the test suite passes and
the Host profile is explicitly wired into the application composition root.
