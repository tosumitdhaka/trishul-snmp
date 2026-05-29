"""Request dispatcher over the UDP client."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

from trishul_snmp.errors import ProtocolError, RequestTimeoutError
from trishul_snmp.security.model import SecurityModel
from trishul_snmp.transport.udp import UdpClient
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Prepared outbound request for send-only or send-and-wait flows."""

    request_id: int
    encoded_message: bytes


class RequestDispatcher:
    """Serialize request/response flows over a connected UDP client."""

    def __init__(
        self, client: UdpClient, *, security: SecurityModel, timeout: float, retries: int
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if retries < 0:
            raise ValueError("retries cannot be negative")
        self._client = client
        self._security = security
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
        pdu = Pdu(
            pdu_type=pdu_type,
            request_id=request_id,
            error_status=error_status,
            error_index=error_index,
            varbinds=varbinds,
        )
        return PreparedRequest(
            request_id=request_id,
            encoded_message=self._security.wrap_pdu(pdu),
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

    async def send_raw_and_receive(self, data: bytes) -> bytes:
        """Send raw bytes and return the first raw response, with retries.

        Used exclusively by UsmModel.prepare() for engine-discovery probes.
        The caller owns parsing; the REPORT PDU never enters the normal flow.
        """
        attempts = self._retries + 1
        last_timeout: RequestTimeoutError | None = None
        for _ in range(attempts):
            await self._client.send(data)
            try:
                return await self._client.receive(self._timeout)
            except RequestTimeoutError as exc:
                last_timeout = exc
        assert last_timeout is not None
        raise last_timeout

    async def _receive_matching_response(self, request_id: int) -> Pdu:
        while True:
            data = await self._client.receive(self._timeout)
            pdu = self._security.unwrap_message(data)
            if pdu is None:
                continue
            if pdu.pdu_type != PduType.RESPONSE:
                raise ProtocolError(f"Expected RESPONSE PDU, received {pdu.pdu_type.name}")
            if pdu.request_id != request_id:
                continue
            return pdu
