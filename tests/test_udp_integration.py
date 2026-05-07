from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest

from trishul_snmp import ErrorStatus, RequestTimeoutError, TransportError, V2cManager, load_bundle
from trishul_snmp.types import (
    EndOfMibViewValue,
    IntegerValue,
    OctetStringValue,
    TimeTicksValue,
)
from trishul_snmp.wire.message import SnmpMessage, decode_message, encode_message
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind


def _write_json(path: Path, payload: dict[object, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_module(*, module: str) -> dict[object, object]:
    return {
        "module": module,
        "language": "SMIv2",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-06T12:00:00Z",
        "imports": {"SNMPv2-TC": ["DisplayString", "InterfaceIndex"]},
        "objects": {},
        "types": {},
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }


def _if_mib_payload() -> dict[object, object]:
    payload = _base_module(module="IF-MIB")
    payload["objects"] = {
        "ifTable": {
            "oid": "1.3.6.1.2.1.2.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "table",
            "syntax": "SEQUENCE OF IfEntry",
            "max_access": "not-accessible",
            "status": "current",
        },
        "ifIndex": {
            "oid": "1.3.6.1.2.1.2.2.1.1",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 1],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "InterfaceIndex",
            "max_access": "read-only",
            "status": "current",
        },
        "ifDescr": {
            "oid": "1.3.6.1.2.1.2.2.1.2",
            "oid_path": [1, 3, 6, 1, 2, 1, 2, 2, 1, 2],
            "object_type": "OBJECT-TYPE",
            "class": "objecttype",
            "nodetype": "column",
            "syntax": "DisplayString",
            "max_access": "read-only",
            "status": "current",
        },
    }
    return payload


def _snmpv2_tc_payload() -> dict[object, object]:
    payload = {
        "module": "SNMPv2-TC",
        "language": "SMIv2",
        "generated_by": "trishul-smi",
        "generated_at": "2026-05-06T12:00:00Z",
        "imports": {},
        "objects": {},
        "types": {
            "DisplayString": {
                "class": "textualconvention",
                "base_type": "OctetString",
                "display_hint": "255a",
                "status": "current",
            },
            "InterfaceIndex": {
                "class": "textualconvention",
                "base_type": "Integer32",
                "display_hint": "d",
                "status": "current",
            },
        },
        "notifications": {},
        "module_metadata": {"lastupdated": None, "revisions": []},
    }
    return payload


class LoopbackSnmpAgent(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.last_error: Exception | None = None
        self.objects: list[tuple[tuple[int, ...], object]] = [
            ((1, 3, 6, 1, 2, 1, 1, 3, 0), TimeTicksValue(12345)),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1), IntegerValue(1)),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2), IntegerValue(2)),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1), OctetStringValue(b"eth0")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2), OctetStringValue(b"eth1")),
        ]

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.DatagramTransport, transport)

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            message = decode_message(data)
            response_pdu = self._build_response(message)
            response = SnmpMessage(
                version=message.version,
                community=message.community,
                pdu=response_pdu,
            )
            assert self.transport is not None
            self.transport.sendto(encode_message(response), addr)
        except Exception as exc:  # pragma: no cover - surfaced explicitly in test
            self.last_error = exc

    def _build_response(self, message: SnmpMessage) -> Pdu:
        pdu = message.pdu
        if pdu.pdu_type == PduType.GET:
            response_varbinds = tuple(self._lookup_exact(vb.oid) for vb in pdu.varbinds)
        elif pdu.pdu_type == PduType.GET_NEXT:
            response_varbinds = tuple(self._lookup_next(vb.oid) for vb in pdu.varbinds)
        elif pdu.pdu_type == PduType.GET_BULK:
            response_varbinds = tuple(self._bulk_walk(pdu.varbinds[0].oid, pdu.error_index))
        else:
            response_varbinds = tuple(
                RawVarBind(oid=vb.oid, value=EndOfMibViewValue()) for vb in pdu.varbinds
            )

        return Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=pdu.request_id,
            error_status=0,
            error_index=0,
            varbinds=response_varbinds,
        )

    def _lookup_exact(self, oid: tuple[int, ...]) -> RawVarBind:
        for known_oid, value in self.objects:
            if known_oid == oid:
                return RawVarBind(oid=oid, value=value)
        return RawVarBind(oid=oid, value=EndOfMibViewValue())

    def _lookup_next(self, oid: tuple[int, ...]) -> RawVarBind:
        for known_oid, value in self.objects:
            if known_oid > oid:
                return RawVarBind(oid=known_oid, value=value)
        return RawVarBind(oid=oid, value=EndOfMibViewValue())

    def _bulk_walk(self, oid: tuple[int, ...], max_repetitions: int) -> list[RawVarBind]:
        results: list[RawVarBind] = []
        current = oid
        for _ in range(max_repetitions):
            next_varbind = self._lookup_next(current)
            results.append(next_varbind)
            if isinstance(next_varbind.value, EndOfMibViewValue):
                break
            current = next_varbind.oid
        return results


class SilentUdpListener(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = cast(asyncio.DatagramTransport, transport)


async def _start_loopback_agent() -> tuple[asyncio.DatagramTransport, LoopbackSnmpAgent, int]:
    loop = asyncio.get_running_loop()
    agent = LoopbackSnmpAgent()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: agent,
            local_addr=("127.0.0.1", 0),
        )
    except OSError as exc:
        if exc.errno in {1, 13}:
            pytest.skip(f"UDP sockets are not permitted in this environment: {exc}")
        raise

    sockname = transport.get_extra_info("sockname")
    assert isinstance(sockname, tuple)
    port = sockname[1]
    return cast(asyncio.DatagramTransport, transport), agent, port


async def _start_silent_listener() -> tuple[asyncio.DatagramTransport, int]:
    loop = asyncio.get_running_loop()
    listener = SilentUdpListener()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: listener,
            local_addr=("127.0.0.1", 0),
        )
    except OSError as exc:
        if exc.errno in {1, 13}:
            pytest.skip(f"UDP sockets are not permitted in this environment: {exc}")
        raise

    sockname = transport.get_extra_info("sockname")
    assert isinstance(sockname, tuple)
    port = sockname[1]
    return cast(asyncio.DatagramTransport, transport), port


def _skip_if_udp_connect_restricted(exc: TransportError) -> None:
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno in {1, 13}:
        pytest.skip(f"UDP client sockets are not permitted in this environment: {cause}")


def test_udp_manager_get_without_bundle() -> None:
    async def scenario() -> None:
        transport, agent, port = await _start_loopback_agent()
        try:
            try:
                async with V2cManager(
                    host="127.0.0.1",
                    port=port,
                    community="public",
                    timeout=0.5,
                    retries=0,
                ) as manager:
                    response = await manager.get("1.3.6.1.2.1.1.3.0")
            except TransportError as exc:
                _skip_if_udp_connect_restricted(exc)
                raise

            assert response.error_status is ErrorStatus.NO_ERROR
            assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
            assert response.varbinds[0].display_name is None
            assert response.varbinds[0].display_value == "12345"
            assert agent.last_error is None
        finally:
            transport.close()

    asyncio.run(scenario())


def test_udp_manager_symbolic_walk_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    _write_json(tmp_path / "SNMPv2-TC.json", _snmpv2_tc_payload())
    bundle = load_bundle(tmp_path)

    async def scenario() -> None:
        transport, agent, port = await _start_loopback_agent()
        try:
            try:
                async with V2cManager(
                    host="127.0.0.1",
                    port=port,
                    community="public",
                    timeout=0.5,
                    retries=0,
                    bundle=bundle,
                ) as manager:
                    response = await manager.get("IF-MIB::ifDescr.1")
                    walked = await manager.walk("IF-MIB::ifTable", max_repetitions=10)
            except TransportError as exc:
                _skip_if_udp_connect_restricted(exc)
                raise

            assert response.error_status is ErrorStatus.NO_ERROR
            assert response.varbinds[0].display_name == "IF-MIB::ifDescr.1"
            assert response.varbinds[0].display_value == "eth0"
            assert [varbind.display_name for varbind in walked] == [
                "IF-MIB::ifIndex.1",
                "IF-MIB::ifIndex.2",
                "IF-MIB::ifDescr.1",
                "IF-MIB::ifDescr.2",
            ]
            assert [varbind.display_value for varbind in walked] == [
                "1",
                "2",
                "eth0",
                "eth1",
            ]
            assert agent.last_error is None
        finally:
            transport.close()

    asyncio.run(scenario())


def test_udp_manager_times_out_against_silent_port() -> None:
    async def scenario() -> None:
        transport, port = await _start_silent_listener()
        try:
            async with V2cManager(
                host="127.0.0.1",
                port=port,
                community="public",
                timeout=0.05,
                retries=0,
            ) as manager:
                with pytest.raises(RequestTimeoutError, match="timed out"):
                    await manager.get("1.3.6.1.2.1.1.3.0")
        except TransportError as exc:
            _skip_if_udp_connect_restricted(exc)
            raise
        finally:
            transport.close()

    asyncio.run(scenario())
