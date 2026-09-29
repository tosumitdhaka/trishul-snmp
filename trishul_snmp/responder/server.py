"""Async SNMPv2c read-only responder and simulator."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from types import TracebackType

from trishul_snmp.errors import ProtocolError, TransportError
from trishul_snmp.mib.bundle import MibBundle
from trishul_snmp.responder.sources import (
    InMemoryObjectSource,
    ObjectInput,
    ResponderSource,
)
from trishul_snmp.transport.udp import UdpServer
from trishul_snmp.types import (
    OID,
    EndOfMibViewValue,
    ErrorStatus,
    NoSuchObjectValue,
    SnmpValueType,
    SocketAddress,
)
from trishul_snmp.wire.message import (
    SNMP_V2C_VERSION,
    SnmpMessage,
    decode_message,
    encode_message,
)
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

_DEFAULT_MAX_BULK_REPETITIONS = 1000
_DEFAULT_MAX_RESPONSE_BYTES = 65535


class V2cResponder:
    """Async SNMPv2c read-only responder for simulator-style use cases.

    The responder speaks SNMPv2c only: SNMPv1 requests are dropped at the
    receive boundary rather than answered with v2-only exception values.
    GETBULK work is bounded by *max_bulk_repetitions* and response
    varbinds are truncated (RFC 3416 section 4.2.3) so the encoded
    response stays within *max_response_bytes*.
    """

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 161,
        communities: Sequence[str] | None = None,
        source: ResponderSource | None = None,
        objects: Iterable[ObjectInput] = (),
        bundle: MibBundle | None = None,
        max_bulk_repetitions: int = _DEFAULT_MAX_BULK_REPETITIONS,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if source is not None and tuple(objects):
            raise ValueError("objects cannot be used when source is provided")
        if max_bulk_repetitions < 0:
            raise ValueError("max_bulk_repetitions cannot be negative")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be at least 1")

        self._server = UdpServer(host, port)
        self._communities = _normalize_communities(communities)
        self._max_bulk_repetitions = max_bulk_repetitions
        self._max_response_bytes = max_response_bytes
        self._closed = False
        self._source: ResponderSource
        if source is None:
            self._source = InMemoryObjectSource(bundle=bundle, objects=objects)
        else:
            self._source = source

    async def __aenter__(self) -> V2cResponder:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        await self.close()

    @property
    def local_address(self) -> SocketAddress | None:
        return self._server.local_address

    @property
    def source(self) -> ResponderSource:
        return self._source

    async def open(self) -> None:
        """Bind the responder socket."""
        self._closed = False
        await self._server.open()

    async def close(self) -> None:
        """Close the responder socket."""
        self._closed = True
        await self._server.close()

    async def serve(self, *, count: int = 0) -> int:
        """Serve up to *count* requests, or run until closed when count is ``0``."""
        if count < 0:
            raise ValueError("count cannot be negative")

        handled = 0
        while count == 0 or handled < count:
            try:
                await self.handle_request()
            except TransportError:
                if self._closed:
                    return handled
                raise
            handled += 1
        return handled

    async def serve_forever(self) -> None:
        """Serve requests until the responder is closed."""
        await self.serve(count=0)

    async def handle_request(self) -> None:
        """Wait for and handle the next supported request."""
        while True:
            datagram = await self._server.receive()
            try:
                message = decode_message(datagram.data)
            except ProtocolError:
                continue
            if message.version != SNMP_V2C_VERSION:
                # The responder is v2c-only: answering an SNMPv1 request with
                # v2-only exception values would produce an invalid v1
                # response, so v1 traffic is dropped at the boundary.
                continue
            if not _community_allowed(communities=self._communities, community=message.community):
                continue

            try:
                response = self._build_response_message(message)
                if response is None:
                    continue
                encoded = encode_message(response)
            except ProtocolError:
                # A simulated value that cannot be encoded must not
                # terminate the service loop: drop the response.
                continue

            await self._server.sendto(encoded, datagram.source_address)
            return None

    def set_object(self, target: str | Sequence[int], value: SnmpValueType) -> OID:
        """Set an object value when using the default in-memory source."""
        return self._require_in_memory_source().set_object(target, value)

    def set_objects(self, objects: Iterable[ObjectInput]) -> tuple[OID, ...]:
        """Set multiple object values when using the default in-memory source."""
        return self._require_in_memory_source().set_objects(objects)

    def clear_objects(self) -> None:
        """Clear all objects when using the default in-memory source."""
        self._require_in_memory_source().clear()

    def _require_in_memory_source(self) -> InMemoryObjectSource:
        if isinstance(self._source, InMemoryObjectSource):
            return self._source
        raise TypeError("Responder is not using an InMemoryObjectSource")

    def _build_response_message(self, message: SnmpMessage) -> SnmpMessage | None:
        response_pdu = self._build_response_pdu(message.pdu)
        if response_pdu is None:
            return None
        response = SnmpMessage(
            version=message.version,
            community=message.community,
            pdu=response_pdu,
        )
        if message.pdu.pdu_type is PduType.GET_BULK:
            return self._truncate_bulk_response(response)
        return response

    def _truncate_bulk_response(self, response: SnmpMessage) -> SnmpMessage:
        """Truncate a GETBULK response to *max_response_bytes*.

        RFC 3416 section 4.2.3: a GETBULK response that does not fit is
        truncated (dropping trailing varbinds), never answered with a
        tooBig error. Non-repeaters come first, so they survive truncation.
        """
        while len(encode_message(response)) > self._max_response_bytes:
            varbinds = response.pdu.varbinds
            if not varbinds:
                # An empty PDU is the smallest valid truncation.
                return response
            keep = len(varbinds) // 2
            response = SnmpMessage(
                version=response.version,
                community=response.community,
                pdu=replace(response.pdu, varbinds=varbinds[:keep]),
            )
        return response

    def _build_response_pdu(self, request_pdu: Pdu) -> Pdu | None:
        if request_pdu.pdu_type is PduType.GET:
            response_varbinds = tuple(
                self._lookup_exact_varbind(varbind.oid) for varbind in request_pdu.varbinds
            )
            return self._response_pdu(request_pdu, varbinds=response_varbinds)

        if request_pdu.pdu_type is PduType.GET_NEXT:
            response_varbinds = tuple(
                self._lookup_next_varbind(varbind.oid) for varbind in request_pdu.varbinds
            )
            return self._response_pdu(request_pdu, varbinds=response_varbinds)

        if request_pdu.pdu_type is PduType.GET_BULK:
            response_varbinds = self._build_bulk_varbinds(
                request_pdu.varbinds,
                non_repeaters=request_pdu.error_status,
                max_repetitions=request_pdu.error_index,
            )
            return self._response_pdu(request_pdu, varbinds=response_varbinds)

        if request_pdu.pdu_type is PduType.SET:
            return self._response_pdu(
                request_pdu,
                varbinds=request_pdu.varbinds,
                error_status=int(ErrorStatus.NOT_WRITABLE),
                error_index=1 if request_pdu.varbinds else 0,
            )

        return None

    def _response_pdu(
        self,
        request_pdu: Pdu,
        *,
        varbinds: tuple[RawVarBind, ...],
        error_status: int = 0,
        error_index: int = 0,
    ) -> Pdu:
        return Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=request_pdu.request_id,
            error_status=error_status,
            error_index=error_index,
            varbinds=varbinds,
        )

    def _lookup_exact_varbind(self, oid: OID) -> RawVarBind:
        value = self._source.lookup_exact(oid)
        if value is None:
            return RawVarBind(oid=oid, value=NoSuchObjectValue())
        return RawVarBind(oid=oid, value=value)

    def _lookup_next_varbind(self, oid: OID) -> RawVarBind:
        match = self._source.lookup_next(oid)
        if match is None:
            return RawVarBind(oid=oid, value=EndOfMibViewValue())
        next_oid, value = match
        return RawVarBind(oid=next_oid, value=value)

    def _build_bulk_varbinds(
        self,
        request_varbinds: tuple[RawVarBind, ...],
        *,
        non_repeaters: int,
        max_repetitions: int,
    ) -> tuple[RawVarBind, ...]:
        if max_repetitions <= 0:
            max_repetitions = 0
        if non_repeaters < 0:
            non_repeaters = 0
        # Bound the response work: the wire value never drives more than
        # the configured repetition cap regardless of what was requested.
        max_repetitions = min(max_repetitions, self._max_bulk_repetitions)

        request_oids = [varbind.oid for varbind in request_varbinds]
        split = min(non_repeaters, len(request_oids))
        response_varbinds = [self._lookup_next_varbind(oid) for oid in request_oids[:split]]

        repeaters = request_oids[split:]
        exhausted = [False] * len(repeaters)
        current_oids = repeaters.copy()
        for _ in range(max_repetitions):
            if all(exhausted):
                # Every repeater column reached endOfMibView: no further
                # repetition can add information, so stop early.
                break
            for index, current_oid in enumerate(current_oids):
                if exhausted[index]:
                    # Frozen column: endOfMibView was already emitted once
                    # for this repeater, so it must not be repeated.
                    continue
                next_varbind = self._lookup_next_varbind(current_oid)
                response_varbinds.append(next_varbind)
                if isinstance(next_varbind.value, EndOfMibViewValue):
                    exhausted[index] = True
                else:
                    current_oids[index] = next_varbind.oid

        return tuple(response_varbinds)


def _normalize_communities(communities: Sequence[str] | None) -> frozenset[str] | None:
    if communities is None:
        return None
    return frozenset(value for value in communities if value)


def _community_allowed(*, communities: frozenset[str] | None, community: str) -> bool:
    if communities is None:
        return True
    return community in communities
