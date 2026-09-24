"""CommunityModel — SNMPv1/v2c community-string implementation of SecurityModel."""

from __future__ import annotations

from trishul_snmp.errors import ProtocolError
from trishul_snmp.wire.message import (
    SNMP_V1_VERSION,
    SNMP_V2C_VERSION,
    SnmpMessage,
    decode_message,
    encode_message,
)
from trishul_snmp.wire.pdu import Pdu


class CommunityModel:
    """Wrap/unwrap SNMP messages using a community string (v1 or v2c)."""

    def __init__(self, community: str, *, version: int = SNMP_V2C_VERSION) -> None:
        if version not in (SNMP_V1_VERSION, SNMP_V2C_VERSION):
            raise ProtocolError(
                f"Community security model supports versions {SNMP_V1_VERSION} (SNMPv1) and "
                f"{SNMP_V2C_VERSION} (SNMPv2c), got {version}"
            )
        self._community = community
        self._version = version

    @property
    def version(self) -> int:
        """SNMP message version this model encodes and accepts (0 = v1, 1 = v2c)."""
        return self._version

    def wrap_pdu(self, pdu: Pdu) -> bytes:
        message = SnmpMessage(
            version=self._version,
            community=self._community,
            pdu=pdu,
        )
        return encode_message(message)

    def unwrap_message(self, data: bytes) -> Pdu | None:
        message = decode_message(data)
        if message.version != self._version:
            return None
        if message.community != self._community:
            return None
        return message.pdu
