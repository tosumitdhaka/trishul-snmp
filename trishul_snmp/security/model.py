"""SecurityModel protocol — community (v2c) and USM (v3) both implement this."""

from __future__ import annotations

from typing import Protocol

from trishul_snmp.wire.pdu import Pdu


class SecurityModel(Protocol):
    def wrap_pdu(self, pdu: Pdu) -> bytes: ...
    def unwrap_message(self, data: bytes) -> Pdu | None: ...
