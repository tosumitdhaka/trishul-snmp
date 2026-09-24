"""Request dispatcher over the UDP client."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from trishul_snmp.errors import (
    AuthenticationError,
    EngineRecoveryReportError,
    ProtocolError,
    RequestTimeoutError,
)
from trishul_snmp.security.model import SecurityModel
from trishul_snmp.transport.udp import UdpClient
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

_REQUEST_ID_MASK = (1 << 31) - 1  # RFC 3412: request-id ranges over 0..2**31 - 1


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
        self._issued_request_ids: set[int] = set()

    def _new_request_id(self) -> int:
        """Return an unpredictable nonzero 31-bit ID not in use by a live request."""
        while True:
            request_id = int.from_bytes(os.urandom(4), "big") & _REQUEST_ID_MASK
            if request_id != 0 and request_id not in self._issued_request_ids:
                self._issued_request_ids.add(request_id)
                return request_id

    def prepare_request(
        self,
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> PreparedRequest:
        """Prepare an outbound request without deciding how it will be sent."""
        request_id = self._new_request_id()
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
        try:
            return await self._receive_matching_response(request_id)
        finally:
            self._issued_request_ids.discard(request_id)

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
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RequestTimeoutError("SNMP request timed out waiting for a response")
            data = await self._client.receive(remaining)
            try:
                pdu = self._security.unwrap_message(data)
            except AuthenticationError:
                raise
            except ProtocolError:
                continue
            if pdu is None:
                # A usmStatsNotInTimeWindows REPORT is consumed by the USM model,
                # which adopts the peer's authoritative engine state and returns
                # None. Surface it so the caller can retry immediately instead of
                # waiting out the full timeout.
                if getattr(self._security, "engine_recovery_needed", False):
                    raise EngineRecoveryReportError(
                        "SNMPv3 engine-recovery REPORT received; retry the request "
                        "after adopting the peer's engine state",
                        report=data,
                    )
                continue
            if pdu.pdu_type != PduType.RESPONSE:
                raise ProtocolError(f"Expected RESPONSE PDU, received {pdu.pdu_type.name}")
            if pdu.request_id != request_id:
                continue
            return pdu
