"""Request dispatcher over the UDP client."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

from trishul_snmp.errors import ProtocolError, RequestTimeoutError
from trishul_snmp.transport.udp import UdpClient
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Prepared outbound request for send-only or send-and-wait flows."""

    request_id: int
    message: SnmpMessage
    encoded_message: bytes


class RequestDispatcher:
    """Serialize request/response flows over a connected UDP client."""

    def __init__(self, client: UdpClient, *, community: str, timeout: float, retries: int) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if retries < 0:
            raise ValueError("retries cannot be negative")
        self._client = client
        self._community = community
        self._timeout = timeout
        self._retries = retries
        self._request_ids = count(1)

    def prepare_request(
        self,
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> PreparedRequest:
        """Prepare an outbound request without deciding how it will be sent."""
        request_id = next(self._request_ids)
        message = SnmpMessage(
            version=1,
            community=self._community,
            pdu=Pdu(
                pdu_type=pdu_type,
                request_id=request_id,
                error_status=error_status,
                error_index=error_index,
                varbinds=varbinds,
            ),
        )
        return PreparedRequest(
            request_id=request_id,
            message=message,
            encoded_message=encode_message(message),
        )

    async def send_only(self, request: PreparedRequest) -> None:
        """Send a prepared request without waiting for a response."""
        await self._client.send(request.encoded_message)

    async def receive_response(self, request_id: int) -> Pdu:
        """Wait for a matching response to an earlier prepared request."""
        return await self._receive_matching_response(request_id)

    async def send_prepared_request(self, request: PreparedRequest) -> Pdu:
        """Send a prepared request and wait for a matching response."""
        attempts = self._retries + 1
        last_timeout: RequestTimeoutError | None = None
        for _ in range(attempts):
            await self.send_only(request)
            try:
                return await self.receive_response(request.request_id)
            except RequestTimeoutError as exc:
                last_timeout = exc
        assert last_timeout is not None
        raise last_timeout

    async def send_pdu(
        self,
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> Pdu:
        """Encode, send, and wait for a matching response PDU."""
        request = self.prepare_request(
            pdu_type,
            varbinds,
            error_status=error_status,
            error_index=error_index,
        )
        return await self.send_prepared_request(request)

    async def _receive_matching_response(self, request_id: int) -> Pdu:
        while True:
            data = await self._client.receive(self._timeout)
            message = decode_message(data)
            if message.community != self._community:
                continue
            if message.pdu.pdu_type != PduType.RESPONSE:
                raise ProtocolError(f"Expected RESPONSE PDU, received {message.pdu.pdu_type.name}")
            if message.pdu.request_id != request_id:
                continue
            return message.pdu
