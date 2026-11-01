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

## Security properties

- The initial adapter is read-only.
- Process inventory is bounded to 1..500 records.
- Command lines, environment variables, open files and credentials are not
  collected.
- Per-process access-denied, vanished and zombie processes are skipped.
- No shell execution, service mutation, process termination or privilege
  elevation is exposed by this contract.

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
