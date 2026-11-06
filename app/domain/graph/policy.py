"""Scope and sensitivity policy for the graph.

``ScopePolicy`` garante que todo nó admitido pertence ao escopo da investigação
e, opcionalmente, que pivôs sensíveis estão autorizados.

``SensitivityPolicy`` é a única porta para um CPF: valida os dígitos
verificadores, calcula HMAC-SHA256 com o *pepper* do cofre e devolve um nó
``CPF_HASH``. Um CPF em texto claro nunca é aceito.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any

from app.domain.graph.nodes import (
    SENSITIVE_NODE_TYPES,
    Node,
    NodeType,
    is_valid_cpf,
    only_digits,
)

_CPF_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORMATTED_CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")

#: Menor pepper aceito: um HMAC com segredo curto é reversível por dicionário.
MIN_PEPPER_BYTES = 16


class GraphPolicyError(Exception):
    """Base class for policy refusals raised at the graph boundary."""


class ScopeViolation(GraphPolicyError):
    """Raised when a node or capability falls outside the authorized scope."""


class SensitiveDataError(GraphPolicyError):
    """Raised when sensitive data would enter the graph improperly."""


@dataclass(frozen=True)
class ScopePolicy:
    """Authorize nodes for exactly one investigation scope."""

    scope_id: str
    allow_sensitive_pivots: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope_id, str) or not self.scope_id.strip():
            raise ScopeViolation("scope_id must be a non-empty string")

    def allows(self, node: Node) -> bool:
        """True when *node* belongs to this scope and is permitted here."""
        if node.scope_id != self.scope_id:
            return False
        return self.allow_sensitive_pivots or not node.requires_sensitive_store

    def require(self, node: Node) -> Node:
        """Return *node* or raise; use at every graph entry point."""
        if node.scope_id != self.scope_id:
            raise ScopeViolation(
                f"node scope {node.scope_id!r} is outside authorized scope "
                f"{self.scope_id!r}"
            )
        if node.requires_sensitive_store and not self.allow_sensitive_pivots:
            raise ScopeViolation(
                "sensitive nodes require allow_sensitive_pivots=True for this scope"
            )
        return node


@dataclass(frozen=True)
class SensitivityPolicy:
    """Hash CPF before it can reach the graph and audit what is sensitive."""

    pepper: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.pepper, (bytes, bytearray)):
            raise SensitiveDataError("pepper must be bytes")
        value = bytes(self.pepper)
        if len(value) < MIN_PEPPER_BYTES:
            raise SensitiveDataError(
                f"pepper must have at least {MIN_PEPPER_BYTES} bytes"
            )
        object.__setattr__(self, "pepper", value)

    def hash_cpf(self, raw_cpf: str) -> str:
        """Return ``sha256:<hex>`` HMAC of a valid CPF, never the CPF itself."""
        digits = only_digits(str(raw_cpf))
        if not is_valid_cpf(digits):
            raise SensitiveDataError("cpf is invalid; refusing to hash it")
        digest = hmac.new(self.pepper, digits.encode("ascii"), hashlib.sha256)
        return f"sha256:{digest.hexdigest()}"

    def cpf_node(
        self,
        raw_cpf: str,
        *,
        scope_id: str,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        """Build the ``CPF_HASH`` node; there is no plaintext CPF node."""
        return Node(
            type=NodeType.CPF_HASH,
            selector=self.hash_cpf(raw_cpf),
            scope_id=scope_id,
            attributes=attributes or {},
        )

    def is_sensitive(self, node: Node) -> bool:
        return node.requires_sensitive_store

    def assert_graph_safe(self, node: Node) -> None:
        """Reject nodes that would put sensitive data in the main graph."""
        if node.type in SENSITIVE_NODE_TYPES:
            if not node.sensitive:
                raise SensitiveDataError(
                    f"{node.type.value} nodes are sensitive by construction"
                )
            if not _CPF_HASH_RE.match(node.selector):
                raise SensitiveDataError(
                    "sensitive node does not carry a hashed selector"
                )
        if _FORMATTED_CPF_RE.search(node.selector) or _FORMATTED_CPF_RE.search(
            str(node.attributes)
        ):
            raise SensitiveDataError("plaintext CPF detected in graph payload")
        if node.type is NodeType.PERSON and _CPF_HASH_RE.match(node.selector):
            raise SensitiveDataError("a person node cannot be keyed by a cpf digest")
