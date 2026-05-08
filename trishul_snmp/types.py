"""Shared public types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TypeAlias

OID: TypeAlias = tuple[int, ...]
SocketAddress: TypeAlias = tuple[str, int] | tuple[str, int, int, int]


class ErrorStatus(IntEnum):
    """SNMP PDU error status values."""

    NO_ERROR = 0
    TOO_BIG = 1
    NO_SUCH_NAME = 2
    BAD_VALUE = 3
    READ_ONLY = 4
    GEN_ERR = 5
    NO_ACCESS = 6
    WRONG_TYPE = 7
    WRONG_LENGTH = 8
    WRONG_ENCODING = 9
    WRONG_VALUE = 10
    NO_CREATION = 11
    INCONSISTENT_VALUE = 12
    RESOURCE_UNAVAILABLE = 13
    COMMIT_FAILED = 14
    UNDO_FAILED = 15
    AUTHORIZATION_ERROR = 16
    NOT_WRITABLE = 17
    INCONSISTENT_NAME = 18

    @property
    def label(self) -> str:
        return self.name.lower()


class SnmpValue:
    """Base SNMP value object."""

    type_name = "value"

    def to_display_string(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class IntegerValue(SnmpValue):
    value: int
    type_name = "integer"

    def to_display_string(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class OctetStringValue(SnmpValue):
    value: bytes
    type_name = "octet-string"

    def to_display_string(self) -> str:
        if not self.value:
            return ""
        try:
            decoded = self.value.decode("utf-8")
        except UnicodeDecodeError:
            return self.value.hex()
        if all(ch.isprintable() for ch in decoded):
            return decoded
        return self.value.hex()


@dataclass(frozen=True, slots=True)
class NullValue(SnmpValue):
    type_name = "null"

    def to_display_string(self) -> str:
        return "null"


@dataclass(frozen=True, slots=True)
class ObjectIdentifierValue(SnmpValue):
    value: OID
    type_name = "object-identifier"

    def to_display_string(self) -> str:
        return ".".join(str(arc) for arc in self.value)


@dataclass(frozen=True, slots=True)
class IpAddressValue(SnmpValue):
    value: str
    type_name = "ip-address"

    def to_display_string(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Counter32Value(SnmpValue):
    value: int
    type_name = "counter32"

    def to_display_string(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Gauge32Value(SnmpValue):
    value: int
    type_name = "gauge32"

    def to_display_string(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TimeTicksValue(SnmpValue):
    value: int
    type_name = "timeticks"

    def to_display_string(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class OpaqueValue(SnmpValue):
    value: bytes
    type_name = "opaque"

    def to_display_string(self) -> str:
        return self.value.hex()


@dataclass(frozen=True, slots=True)
class Counter64Value(SnmpValue):
    value: int
    type_name = "counter64"

    def to_display_string(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class NoSuchObjectValue(SnmpValue):
    type_name = "no-such-object"

    def to_display_string(self) -> str:
        return "noSuchObject"


@dataclass(frozen=True, slots=True)
class NoSuchInstanceValue(SnmpValue):
    type_name = "no-such-instance"

    def to_display_string(self) -> str:
        return "noSuchInstance"


@dataclass(frozen=True, slots=True)
class EndOfMibViewValue(SnmpValue):
    type_name = "end-of-mib-view"

    def to_display_string(self) -> str:
        return "endOfMibView"


SnmpValueType: TypeAlias = (
    IntegerValue
    | OctetStringValue
    | NullValue
    | ObjectIdentifierValue
    | IpAddressValue
    | Counter32Value
    | Gauge32Value
    | TimeTicksValue
    | OpaqueValue
    | Counter64Value
    | NoSuchObjectValue
    | NoSuchInstanceValue
    | EndOfMibViewValue
)


@dataclass(frozen=True, slots=True)
class OidMatch:
    """Resolved view of a numeric OID against the loaded bundle."""

    oid: OID
    module: str
    symbol: str
    matched_oid: OID
    suffix: OID = ()
    class_name: str | None = None
    object_type: str | None = None
    nodetype: str | None = None

    @property
    def symbolic(self) -> str:
        base = f"{self.module}::{self.symbol}"
        if not self.suffix:
            return base
        suffix = ".".join(str(arc) for arc in self.suffix)
        return f"{base}.{suffix}"


@dataclass(frozen=True, slots=True)
class VarBind:
    """Public response varbind model."""

    oid: OID
    value: SnmpValueType
    match: OidMatch | None = None
    display_name: str | None = None
    display_value: str | None = None

    @property
    def oid_str(self) -> str:
        return ".".join(str(arc) for arc in self.oid)

    @property
    def value_type(self) -> str:
        return self.value.type_name


@dataclass(frozen=True, slots=True)
class Response:
    """Public manager response model."""

    request_id: int
    error_status: ErrorStatus
    error_index: int
    varbinds: tuple[VarBind, ...]
