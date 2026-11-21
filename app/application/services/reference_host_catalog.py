"""Reference host declarations for the capability layer (ADR-006 C1, Ubuntu first).

This module only *declares* hosts, bindings, availability, limitations and policy
classes. It probes nothing, installs nothing and grants nothing: authorization
stays with ``ToolAuthorizationPolicy`` and the dispatcher.

The two Ubuntu hosts exist to keep the three questions apart:

- *where* (host) — server vs. desktop session;
- *how* (implementation) — ``psutil_host_adapter`` for telemetry,
  ``hardware_controller`` for screen capture;
- *whether it can run here* (availability + limitations) — a headless Ubuntu
  server has no display session, so ``capability:screen.capture`` is declared
  unavailable there and available on the desktop host.

No Android or Windows binding is declared here because this repository session
did not verify one; declaring them would be an unverified claim.
"""

from __future__ import annotations

from app.application.services.capability_binding_registry import (
    Availability,
    CapabilityBindingRegistry,
    HostState,
)

UBUNTU_SERVER = "host:ubuntu-server"
UBUNTU_DESKTOP = "host:ubuntu-desktop"

_OBSERVED_ON_UBUNTU = (
    "host.observe.identity",
    "host.observe.resources",
    "host.observe.processes",
)


def build_reference_capability_catalog() -> CapabilityBindingRegistry:
    """Return the declared Ubuntu reference catalog.

    Availability and limitations describe the implementation's preconditions;
    they are not test results and they are not authorization.
    """
    catalog = CapabilityBindingRegistry()

    catalog.declare_host(
        UBUNTU_SERVER,
        os_family="ubuntu",
        state=HostState.ONLINE,
        limitations=("no-graphical-display-session",),
    )
    catalog.declare_host(
        UBUNTU_DESKTOP,
        os_family="ubuntu",
        state=HostState.ONLINE,
        limitations=("x11-session-only",),
    )

    for capability in _OBSERVED_ON_UBUNTU:
        for host_ref in (UBUNTU_SERVER, UBUNTU_DESKTOP):
            catalog.bind(
                capability,
                host_ref=host_ref,
                adapter_id="psutil_host_adapter",
                policy_class="observe",
            )

    catalog.bind(
        "screen.capture",
        host_ref=UBUNTU_SERVER,
        adapter_id="hardware_controller",
        availability=Availability.UNAVAILABLE,
        limitations=("requires-graphical-display-session",),
        policy_class="observe",
    )
    catalog.bind(
        "screen.capture",
        host_ref=UBUNTU_DESKTOP,
        adapter_id="hardware_controller",
        limitations=("captures-only-the-current-x11-session",),
        policy_class="observe",
    )

    # Same capability ID the execution catalog uses for this adapter in
    # ``config/tool_registry.json``; two names for one adapter would split the
    # identity ADR-006 §1 keeps canonical.
    for host_ref in (UBUNTU_SERVER, UBUNTU_DESKTOP):
        catalog.bind(
            "network.discovery.passive",
            host_ref=host_ref,
            adapter_id="network_discovery_adapter",
            policy_class="observe",
        )

    catalog.bind(
        "messaging.send",
        host_ref=UBUNTU_SERVER,
        adapter_id="telegram_adapter",
        policy_class="active_bounded",
    )
    catalog.bind(
        "messaging.send",
        host_ref=UBUNTU_DESKTOP,
        adapter_id="telegram_adapter",
        policy_class="active_bounded",
    )

    return catalog


__all__ = ["UBUNTU_DESKTOP", "UBUNTU_SERVER", "build_reference_capability_catalog"]
