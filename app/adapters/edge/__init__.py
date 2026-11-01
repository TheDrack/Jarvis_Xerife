"""Edge adapters with lazy exports.

Importing one network adapter must not eagerly load optional desktop, audio,
or hardware dependencies. Public adapter names remain available on demand.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "AutomationAdapter": (".automation_adapter", "AutomationAdapter"),
    "CombinedVoiceProvider": (".combined_voice_provider", "CombinedVoiceProvider"),
    "KeyboardAdapter": (".keyboard_adapter", "KeyboardAdapter"),
    "TTSAdapter": (".tts_adapter", "TTSAdapter"),
    "VoiceAdapter": (".voice_adapter", "VoiceAdapter"),
    "WebAdapter": (".web_adapter", "WebAdapter"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load a public adapter only when that adapter is explicitly requested."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
