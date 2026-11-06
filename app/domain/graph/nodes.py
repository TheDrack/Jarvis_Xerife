"""Canonical node contract for the OSINT knowledge graph.

Fase 0 (fundação): o grafo é o estado primário. Adapters devolvem ``Node`` e
``Edge``; nenhum outro lugar do sistema constrói identidade canônica.

Regras estruturais:

- ``Node`` é imutável e sua identidade é *derivada*:
  ``id = sha256(type, seletor normalizado, scope_id)``. O mesmo fato vindo de
  duas fontes é o mesmo nó.
- Todo nó pertence a um ``scope_id`` não vazio; ``ScopePolicy`` reforça isso
  na borda de entrada do grafo.
- ``CPF`` não existe como tipo de nó. Só ``CPF_HASH``, sempre ``sensitive``, e
  o seletor precisa já ser o digest HMAC produzido por ``SensitivityPolicy``.
  Um CPF em texto claro é rejeitado na construção do nó.

Normalização por tipo é a única forma de entrar no grafo: e-mail em lowercase,
CNPJ só dígitos (com dígitos verificadores válidos), domínio IDNA, BSSID hex
lower, coordenada com precisão fixa.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from app.domain.graph.interest import Interest


class NodeType(str, Enum):
    """Entidades que podem existir no grafo.

    ``PERSON`` e ``ORG`` aparecem aqui, mas só o ``Resolver`` (Fase 1) pode
    criá-las; adapters nunca as produzem.

    ``SIGNAL_SET`` é o agregado de sinais densos exigido pela Fase 1
    ("500 SIGNAL do mesmo Wi-Fi agregam em SIGNAL_SET").
    """

    IP = "ip"
    CIDR = "cidr"
    ASN = "asn"
    DOMAIN = "domain"
    EMAIL = "email"
    USERNAME = "username"
    PERSON = "person"
    ORG = "org"
    DOCUMENT = "document"
    SIGNAL = "signal"
    SIGNAL_SET = "signal_set"
    COORDINATE = "coordinate"
    HOST = "host"
    LEAK = "leak"
    CNPJ = "cnpj"
    CPF_HASH = "cpf_hash"
    ADDRESS = "address"
    PHONE = "phone"
    VEHICLE = "vehicle"
    LEGAL_CASE = "legal_case"
    DIGITAL_ACCOUNT = "digital_account"


#: Tipos cujo conteúdo é sensível por construção. ``CPF_HASH`` é o único hoje:
#: nunca existe um ``NodeType.CPF``.
SENSITIVE_NODE_TYPES: frozenset[NodeType] = frozenset({NodeType.CPF_HASH})

_MAX_SELECTOR = 512
_FIELD_SEPARATOR = "\x1f"
_CPF_HASH_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_UNICODE_DOTS = ("\u3002", "\uff0e", "\uff61")
_ASN_RE = re.compile(r"^(?:as)?\s*(\d{1,10})$", re.IGNORECASE)
_EMAIL_LOCAL_RE = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}$")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAC_RE = re.compile(r"^[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}$")
_COMPACT_MAC_RE = re.compile(r"^[0-9a-f]{12}$")
_CEP_RE = re.compile(r"^\d{5}-?\d{3}$")
_PLATE_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("selector must be a string")
    return value.strip()


def only_digits(value: str) -> str:
    """Return *value* with every non-digit removed."""
    return re.sub(r"\D", "", value)


def _check_digit(digits: str, weights: tuple[int, ...]) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(digits, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


_CNPJ_WEIGHTS_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_WEIGHTS_2 = (6, *_CNPJ_WEIGHTS_1)
_CPF_WEIGHTS_1 = (10, 9, 8, 7, 6, 5, 4, 3, 2)
_CPF_WEIGHTS_2 = (11, *_CPF_WEIGHTS_1)


def is_valid_cnpj(value: str) -> bool:
    """Validate a CNPJ by length, repetition and check digits."""
    digits = only_digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    first = _check_digit(digits[:12], _CNPJ_WEIGHTS_1)
    second = _check_digit(digits[:12] + str(first), _CNPJ_WEIGHTS_2)
    return digits[12:] == f"{first}{second}"


def is_valid_cpf(value: str) -> bool:
    """Validate a CPF by length, repetition and check digits.

    Used only by ``SensitivityPolicy`` before hashing; the CPF itself never
    becomes a graph selector.
    """
    digits = only_digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    first = _check_digit(digits[:9], _CPF_WEIGHTS_1)
    second = _check_digit(digits[:9] + str(first), _CPF_WEIGHTS_2)
    return digits[9:] == f"{first}{second}"


def _normalize_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(_text(value)))
    except ValueError as exc:
        raise ValueError(f"ip is not a valid IPv4/IPv6 address: {exc}") from exc


def _normalize_cidr(value: str) -> str:
    try:
        return str(ipaddress.ip_network(_text(value), strict=False))
    except ValueError as exc:
        raise ValueError(f"cidr is not a valid network: {exc}") from exc


def _normalize_asn(value: str) -> str:
    match = _ASN_RE.match(_text(value))
    if not match:
        raise ValueError("asn selector must be numeric, e.g. AS64500")
    number = int(match.group(1))
    if not 1 <= number <= 4294967295:
        raise ValueError("asn is out of the 32-bit range")
    return f"as{number}"


def _normalize_domain(value: str) -> str:
    text = _text(value)
    for dot in _UNICODE_DOTS:
        text = text.replace(dot, ".")
    text = text.rstrip(".").casefold()
    if not text:
        raise ValueError("domain selector is empty")
    if any(token in text for token in ("/", "@", ":", " ", "\t")):
        raise ValueError("domain selector must be a bare domain, not a URL or e-mail")
    try:
        ascii_domain = text.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"domain is not IDNA compliant: {exc}") from exc
    if not ascii_domain or len(ascii_domain) > 253:
        raise ValueError("domain length is invalid")
    return ascii_domain


def _normalize_email(value: str) -> str:
    text = _text(value).casefold()
    local, separator, domain = text.rpartition("@")
    if not separator or not local or not domain:
        raise ValueError("email selector must be local@domain")
    if not _EMAIL_LOCAL_RE.match(local) or local.startswith(".") or local.endswith("."):
        raise ValueError("email local part is invalid")
    normalized = f"{local}@{_normalize_domain(domain)}"
    if len(normalized) > 254:
        raise ValueError("email selector is too long")
    return normalized


def _normalize_username(value: str) -> str:
    text = _text(value)
    if text.startswith("@"):
        text = text[1:]
    text = text.casefold()
    if not _USERNAME_RE.match(text):
        raise ValueError("username must match [a-z0-9][a-z0-9._-]{0,63}")
    return text


def _normalized_words(value: str) -> str:
    text = " ".join(_text(value).split()).casefold()
    if not text:
        raise ValueError("selector is empty")
    return text


def _normalize_document(value: str) -> str:
    # Windows/UNC paths são case-insensitive na prática; normalizar o separador
    # mantém o mesmo documento com uma única identidade.
    return _text(value).replace("\\", "/").casefold()


def _format_mac(text: str) -> str:
    digits = re.sub(r"[:-]", "", text.casefold())
    return ":".join(digits[index : index + 2] for index in range(0, 12, 2))


def _normalize_signal(value: str) -> str:
    text = _text(value)
    lowered = text.casefold()
    if _MAC_RE.match(lowered) or _COMPACT_MAC_RE.match(lowered):
        return _format_mac(lowered)
    if not lowered:
        raise ValueError("signal selector is empty")
    return lowered


def _normalize_coordinate(value: str) -> str:
    text = _text(value)
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise ValueError("coordinate selector must be 'lat,lon'")
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValueError("coordinate selector must contain two numbers") from exc
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValueError("coordinate is outside latitude/longitude bounds")
    lat = 0.0 if lat == 0 else lat
    lon = 0.0 if lon == 0 else lon
    return f"{lat:.6f},{lon:.6f}"


def _normalize_host(value: str) -> str:
    text = _text(value)
    try:
        return _normalize_ip(text)
    except ValueError:
        pass
    text = text.rstrip(".").casefold()
    if not text or any(token in text for token in ("/", "@", " ", "\t")):
        raise ValueError("host selector must be an IP address or hostname")
    return text


def _normalize_cnpj(value: str) -> str:
    digits = only_digits(_text(value))
    if len(digits) != 14:
        raise ValueError("cnpj selector must contain exactly 14 digits")
    if not is_valid_cnpj(digits):
        raise ValueError("cnpj check digits are invalid")
    return digits


def _normalize_cpf_hash(value: str) -> str:
    match = _CPF_HASH_RE.match(_text(value))
    if not match:
        raise ValueError(
            "cpf_hash selector must be a sha256 digest produced by "
            "SensitivityPolicy; a raw CPF is never a graph selector"
        )
    return f"sha256:{match.group(1).lower()}"


def _normalize_address(value: str) -> str:
    text = " ".join(_text(value).split()).casefold()
    if not text:
        raise ValueError("address selector is empty")
    compact = text.replace(".", "").replace(" ", "")
    if _CEP_RE.match(compact):
        digits = compact.replace("-", "")
        return f"{digits[:5]}-{digits[5:]}"
    return text


def _normalize_phone(value: str) -> str:
    text = re.sub(r"[^\d+]", "", _text(value))
    prefix = "+" if text.startswith("+") else ""
    digits = text[1:] if prefix else text
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValueError("phone must contain 8 to 15 digits")
    return f"{prefix}{digits}"


def _normalize_vehicle(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]", "", _text(value)).upper()
    if not _PLATE_RE.match(text):
        raise ValueError("vehicle plate must be AAA1234 or AAA1A23")
    return text


def _normalize_legal_case(value: str) -> str:
    text = _text(value)
    digits = only_digits(text)
    if len(digits) == 20 and not any(character.isalpha() for character in text):
        return digits
    normalized = text.casefold()
    if not normalized:
        raise ValueError("legal_case selector is empty")
    return normalized


def _normalize_digital_account(value: str) -> str:
    text = _text(value).casefold()
    platform, separator, handle = text.partition(":")
    if not separator or not platform.strip() or not handle.strip():
        raise ValueError("digital_account selector must be 'platform:handle'")
    return f"{platform.strip()}:{handle.strip()}"


NORMALIZERS: Mapping[NodeType, Callable[[str], str]] = MappingProxyType(
    {
        NodeType.IP: _normalize_ip,
        NodeType.CIDR: _normalize_cidr,
        NodeType.ASN: _normalize_asn,
        NodeType.DOMAIN: _normalize_domain,
        NodeType.EMAIL: _normalize_email,
        NodeType.USERNAME: _normalize_username,
        NodeType.PERSON: _normalized_words,
        NodeType.ORG: _normalized_words,
        NodeType.DOCUMENT: _normalize_document,
        NodeType.SIGNAL: _normalize_signal,
        NodeType.SIGNAL_SET: _normalize_signal,
        NodeType.COORDINATE: _normalize_coordinate,
        NodeType.HOST: _normalize_host,
        NodeType.LEAK: _normalized_words,
        NodeType.CNPJ: _normalize_cnpj,
        NodeType.CPF_HASH: _normalize_cpf_hash,
        NodeType.ADDRESS: _normalize_address,
        NodeType.PHONE: _normalize_phone,
        NodeType.VEHICLE: _normalize_vehicle,
        NodeType.LEGAL_CASE: _normalize_legal_case,
        NodeType.DIGITAL_ACCOUNT: _normalize_digital_account,
    }
)


def normalize_selector(node_type: NodeType, selector: str) -> str:
    """Normalize *selector* according to *node_type*.

    This is the only accepted spelling of a selector inside the graph.
    """
    try:
        normalizer = NORMALIZERS[NodeType(node_type)]
    except KeyError as exc:  # pragma: no cover - defensive: every type has one
        raise ValueError(f"no normalizer registered for node type {node_type!r}") from exc
    normalized = normalizer(selector)
    if len(normalized) > _MAX_SELECTOR:
        raise ValueError(f"normalized selector exceeds {_MAX_SELECTOR} characters")
    return normalized


def node_id(node_type: NodeType, selector: str, scope_id: str) -> str:
    """Derive the canonical node id from (type, normalized selector, scope)."""
    payload = _FIELD_SEPARATOR.join((NodeType(node_type).value, selector, scope_id))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class Node(BaseModel):
    """An immutable, scope-bound graph entity with a derived identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default="", max_length=71)
    type: NodeType
    selector: str = Field(min_length=1, max_length=_MAX_SELECTOR)
    scope_id: str = Field(min_length=1, max_length=200)
    sensitive: bool = False
    last_seen: datetime | None = None
    interest: Interest | None = None
    attributes: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("last_seen", mode="before")
    @classmethod
    def _normalize_last_seen(cls, value: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValueError("last_seen must be a datetime")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("scope_id", mode="before")
    @classmethod
    def _normalize_scope(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("scope_id must be a string")
        text = value.strip()
        if not text:
            raise ValueError("scope_id must not be blank")
        return text

    @field_validator("selector", mode="before")
    @classmethod
    def _normalize(cls, value: str, info: ValidationInfo) -> str:
        node_type = info.data.get("type")
        if node_type is None:
            raise ValueError("node type must be declared before the selector")
        return normalize_selector(node_type, value)

    @model_validator(mode="after")
    def _derive_identity(self) -> "Node":
        expected = node_id(self.type, self.selector, self.scope_id)
        if self.id and self.id != expected:
            raise ValueError(
                "node id is derived from (type, selector, scope_id); it cannot be supplied"
            )
        object.__setattr__(self, "id", expected)
        if self.type in SENSITIVE_NODE_TYPES:
            object.__setattr__(self, "sensitive", True)
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        return self

    @field_serializer("attributes")
    def _serialize_attributes(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return dict(value)

    @property
    def requires_sensitive_store(self) -> bool:
        """True when this node must live in the separate sensitive store."""
        return self.sensitive or self.type in SENSITIVE_NODE_TYPES
