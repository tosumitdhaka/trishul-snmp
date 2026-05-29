"""CommunityModel — SNMPv2c community-string implementation of SecurityModel."""

from __future__ import annotations

from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu


class CommunityModel:
    """Wrap/unwrap SNMP messages using a v2c community string."""

    def __init__(self, community: str) -> None:
        self._community = community

    def wrap_pdu(self, pdu: Pdu) -> bytes:
        return encode_message(SnmpMessage(version=1, community=self._community, pdu=pdu))

    def unwrap_message(self, data: bytes) -> Pdu | None:
        message = decode_message(data)
        if message.community != self._community:
            return None
        return message.pdu
