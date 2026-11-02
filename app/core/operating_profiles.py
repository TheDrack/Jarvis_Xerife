# Declarative operating-profile contracts for the portable Jarvis harness.
# This module intentionally imports only the Python standard library. Selecting a
# profile is configuration, not authorization and not proof that host/OS services
# are installed, enabled, or safe to execute.
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class OperatingProfile(str, Enum):
    """Supported Jarvis operating profiles, in stable report order."""

    HARNESS = "harness"
    AUTONOMY = "autonomy"
    HOST = "host"
    JARVIS_OS = "jarvis-os"


def _coerce_profile(value: OperatingProfile | str) -> OperatingProfile:
    if isinstance(value, OperatingProfile):
        return value
    if not isinstance(value, str):
        raise TypeError("operating profile must be a string or OperatingProfile")

    try:
        return OperatingProfile(value)
    except ValueError as exc:
        allowed = ", ".join(profile.value for profile in OperatingProfile)
        raise ValueError(
            f"unsupported operating profile {value!r}; expected one of: {allowed}"
        ) from exc


def _normalize_profiles(
    values: Iterable[OperatingProfile | str] | None,
    field_name: str,
) -> frozenset[OperatingProfile]:
    if values is None:
        return frozenset()
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of profiles, not a string")

    try:
        iterator = iter(values)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of profiles") from exc

    return frozenset(_coerce_profile(value) for value in iterator)


@dataclass(frozen=True, slots=True)
class OperatingProfileStatus:
    """Independent evidence flags for one operating profile."""

    profile: OperatingProfile
    requested: bool
    available: bool
    enabled: bool
    authorized: bool
    tested: bool

    def __post_init__(self) -> None:
        if not isinstance(self.profile, OperatingProfile):
            raise TypeError("profile must be an OperatingProfile")
        for field_name in ("requested", "available", "enabled", "authorized", "tested"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")

    def to_dict(self) -> dict[str, str | bool]:
        """Return a deterministic, secret-free representation."""
        return {
            "profile": self.profile.value,
            "requested": self.requested,
            "available": self.available,
            "enabled": self.enabled,
            "authorized": self.authorized,
            "tested": self.tested,
        }


@dataclass(frozen=True, slots=True)
class OperatingProfileReport:
    """Versioned profile-state report with deterministic profile ordering."""

    selected_profile: OperatingProfile
    profiles: tuple[OperatingProfileStatus, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.selected_profile, OperatingProfile):
            raise TypeError("selected_profile must be an OperatingProfile")
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise TypeError("schema_version must be an integer")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        if not isinstance(self.profiles, tuple) or any(
            not isinstance(status, OperatingProfileStatus) for status in self.profiles
        ):
            raise TypeError("profiles must be a tuple of OperatingProfileStatus values")

        expected_order = tuple(OperatingProfile)
        actual_order = tuple(status.profile for status in self.profiles)
        if actual_order != expected_order:
            raise ValueError("profiles must contain every operating profile in canonical order")

        requested = tuple(
            status.profile for status in self.profiles if status.requested
        )
        if requested != (self.selected_profile,):
            raise ValueError("exactly the selected profile must be marked requested")

    def status_for(self, profile: OperatingProfile | str) -> OperatingProfileStatus:
        """Return the status for a profile or raise KeyError when absent."""
        target = _coerce_profile(profile)
        for status in self.profiles:
            if status.profile is target:
                return status
        raise KeyError(target.value)

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, secret-free report suitable for JSON encoding."""
        return {
            "schema_version": self.schema_version,
            "selected_profile": self.selected_profile.value,
            "profiles": [status.to_dict() for status in self.profiles],
        }


def build_operating_profile_report(
    selected_profile: OperatingProfile | str = OperatingProfile.HARNESS,
    *,
    enabled: bool = False,
    available_profiles: Iterable[OperatingProfile | str] | None = None,
    authorized_profiles: Iterable[OperatingProfile | str] = (),
    tested_profiles: Iterable[OperatingProfile | str] = (),
) -> OperatingProfileReport:
    """Build a profile report without probing the host or granting permissions.

    requested comes from the selected profile. enabled is the explicit opt-in
    flag for non-harness profiles; the portable harness is enabled by definition.
    Availability, authorization and test evidence must be supplied by their
    respective runtime/policy/validation sources. By default only the portable
    harness is available and no profile is implicitly authorized or marked tested.

    An enabled profile may still be unavailable, unauthorized, or untested.
    Consumers must keep these states separate and must not treat this report as
    an authorization decision or as permission to execute host operations.
    """
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a bool")

    selected = _coerce_profile(selected_profile)
    available = (
        frozenset({OperatingProfile.HARNESS})
        if available_profiles is None
        else _normalize_profiles(available_profiles, "available_profiles")
    )
    authorized = _normalize_profiles(authorized_profiles, "authorized_profiles")
    tested = _normalize_profiles(tested_profiles, "tested_profiles")

    statuses = tuple(
        OperatingProfileStatus(
            profile=profile,
            requested=profile is selected,
            available=profile in available,
            enabled=(
                profile is selected
                and (profile is OperatingProfile.HARNESS or enabled)
            ),
            authorized=profile in authorized,
            tested=profile in tested,
        )
        for profile in OperatingProfile
    )
    return OperatingProfileReport(selected_profile=selected, profiles=statuses)
