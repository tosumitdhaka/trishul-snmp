from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from trishul_snmp import ErrorStatus, RequestTimeoutError, load_bundle
from trishul_snmp.manager import V1Manager
from trishul_snmp.security.community import CommunityModel
from trishul_snmp.transport.dispatcher import RequestDispatcher
from trishul_snmp.types import EndOfMibViewValue, OctetStringValue, TimeTicksValue
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
        "imports": {},
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


class FakeUdpClient:
    def __init__(self, replies: list[bytes | Exception | Callable[[bytes], bytes]]) -> None:
        self._replies = list(replies)
        self.sent: list[bytes] = []

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float) -> bytes:
        del timeout
        if not self._replies:
            raise RequestTimeoutError("agent stopped responding")
        reply = self._replies.pop(0)
        if callable(reply):
            reply = reply(self.sent[-1])
        if isinstance(reply, Exception):
            raise reply
        return reply


class _V1Agent:
    """Fake SNMPv1 agent answering GET/GETNEXT from an in-memory table."""

    def __init__(self, *, community: str = "public") -> None:
        self._community = community
        self._objects: list[tuple[tuple[int, ...], object]] = [
            ((1, 3, 6, 1, 2, 1, 1, 3, 0), TimeTicksValue(12345)),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1), OctetStringValue(b"1")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2), OctetStringValue(b"2")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1), OctetStringValue(b"eth0")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2), OctetStringValue(b"eth1")),
        ]

    def __call__(self, sent: bytes) -> bytes:
        request = decode_message(sent)
        if request.pdu.pdu_type is PduType.GET:
            varbinds = tuple(self._lookup_exact(varbind.oid) for varbind in request.pdu.varbinds)
        elif request.pdu.pdu_type is PduType.GET_NEXT:
            varbinds = tuple(self._lookup_next(varbind.oid) for varbind in request.pdu.varbinds)
        else:
            raise AssertionError(f"v1 agent received unexpected PDU {request.pdu.pdu_type!r}")
        return encode_message(
            SnmpMessage(
                version=0,
                community=self._community,
                pdu=Pdu(
                    pdu_type=PduType.RESPONSE,
                    request_id=request.pdu.request_id,
                    error_status=0,
                    error_index=0,
                    varbinds=varbinds,
                ),
            )
        )

    def _lookup_exact(self, oid: tuple[int, ...]) -> RawVarBind:
        for known_oid, value in self._objects:
            if known_oid == oid:
                return RawVarBind(oid=oid, value=value)
        return RawVarBind(oid=oid, value=EndOfMibViewValue())

    def _lookup_next(self, oid: tuple[int, ...]) -> RawVarBind:
        for known_oid, value in self._objects:
            if known_oid > oid:
                return RawVarBind(oid=known_oid, value=value)
        return RawVarBind(oid=oid, value=EndOfMibViewValue())


def _response_bytes(
    *,
    request_id: int,
    community: str = "public",
    version: int = 0,
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    return encode_message(
        SnmpMessage(
            version=version,
            community=community,
            pdu=Pdu(
                pdu_type=PduType.RESPONSE,
                request_id=request_id,
                error_status=error_status,
                error_index=error_index,
                varbinds=(
                    RawVarBind(
                        oid=(1, 3, 6, 1, 2, 1, 1, 3, 0),
                        value=TimeTicksValue(1),
                    ),
                ),
            ),
        )
    )


def _build_manager(
    *,
    bundle_path: Path | None = None,
    replies: list[bytes | Exception | Callable[[bytes], bytes]] | None = None,
    community: str = "public",
) -> tuple[V1Manager, FakeUdpClient]:
    bundle = load_bundle(bundle_path) if bundle_path is not None else None
    manager = V1Manager(
        host="127.0.0.1",
        port=161,
        community=community,
        bundle=bundle,
        timeout=0.2,
        retries=0,
    )
    fake_client = FakeUdpClient(replies or [])
    manager._session._client = fake_client  # type: ignore[attr-defined]
    manager._session._dispatcher = RequestDispatcher(  # type: ignore[attr-defined]
        fake_client,
        security=CommunityModel(community, version=0),
        timeout=0.2,
        retries=0,
    )
    return manager, fake_client


def test_v1_manager_get_roundtrips_v1_wire_message() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()])

    async def scenario() -> int:
        async with manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert response.varbinds[0].value == TimeTicksValue(12345)
        return response.request_id

    request_id = asyncio.run(scenario())

    request = decode_message(fake_client.sent[0])
    assert request.version == 0
    assert request.community == "public"
    assert request.pdu.pdu_type is PduType.GET
    assert request.pdu.request_id == request_id


def test_v1_manager_get_symbolic_enrichment_with_bundle(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    manager, _ = _build_manager(
        bundle_path=tmp_path / "IF-MIB.json",
        replies=[_V1Agent()],
    )

    async def scenario() -> None:
        async with manager:
            response = await manager.get("IF-MIB::ifDescr.1")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].display_name == "IF-MIB::ifDescr.1"
        assert response.varbinds[0].display_value == "eth0"

    asyncio.run(scenario())


def test_v1_manager_get_next_uses_getnext_pdu() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()])

    async def scenario() -> None:
        async with manager:
            response = await manager.get_next("1.3.6.1.2.1.2.2")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1)

    asyncio.run(scenario())

    request = decode_message(fake_client.sent[0])
    assert request.version == 0
    assert request.pdu.pdu_type is PduType.GET_NEXT


def test_v1_manager_walk_uses_getnext_machinery() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()] * 10)

    async def scenario() -> None:
        async with manager:
            walked = await manager.walk("1.3.6.1.2.1.2.2")

        assert [varbind.oid for varbind in walked] == [
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2),
        ]

    asyncio.run(scenario())

    assert fake_client.sent
    for sent in fake_client.sent:
        request = decode_message(sent)
        assert request.version == 0
        assert request.pdu.pdu_type is PduType.GET_NEXT


def test_v1_manager_walk_ignores_bulk_flag() -> None:
    agent = _V1Agent()
    bulk_manager, bulk_client = _build_manager(replies=[agent] * 10)
    next_manager, _ = _build_manager(replies=[agent] * 10)

    async def scenario() -> None:
        async with bulk_manager:
            with_bulk = await bulk_manager.walk("1.3.6.1.2.1.2.2", bulk=True)
        async with next_manager:
            without_bulk = await next_manager.walk("1.3.6.1.2.1.2.2", bulk=False)

        assert with_bulk == without_bulk

    asyncio.run(scenario())

    assert all(decode_message(sent).pdu.pdu_type is PduType.GET_NEXT for sent in bulk_client.sent)


def test_v1_manager_bulkwalk_downgrades_to_getnext() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()] * 10)

    async def scenario() -> None:
        async with manager:
            walked = await manager.bulkwalk("1.3.6.1.2.1.2.2")

        assert [varbind.oid for varbind in walked] == [
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2),
        ]

    asyncio.run(scenario())

    assert all(decode_message(sent).pdu.pdu_type is PduType.GET_NEXT for sent in fake_client.sent)


def test_v1_manager_get_bulk_downgrades_to_getnext_loop(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    manager, fake_client = _build_manager(
        bundle_path=tmp_path / "IF-MIB.json",
        replies=[_V1Agent()] * 10,
    )

    async def scenario() -> None:
        async with manager:
            bulk = await manager.get_bulk("IF-MIB::ifTable", max_repetitions=3)

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert [varbind.display_name for varbind in bulk.varbinds] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
        ]

    asyncio.run(scenario())

    assert len(fake_client.sent) == 3
    assert all(decode_message(sent).pdu.pdu_type is PduType.GET_NEXT for sent in fake_client.sent)


def test_v1_manager_get_bulk_non_repeaters() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()] * 10)

    async def scenario() -> None:
        async with manager:
            bulk = await manager.get_bulk(
                "1.3.6.1.2.1.2.2.1.2.1",
                "1.3.6.1.2.1.2.2.1.1.1",
                non_repeaters=1,
                max_repetitions=2,
            )

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert [varbind.oid for varbind in bulk.varbinds] == [
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2),  # single successor of ifDescr.1
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2),  # successor of ifIndex.1
            (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),  # successor of ifIndex.2
        ]

    asyncio.run(scenario())

    assert len(fake_client.sent) == 3  # 1 non-repeater + 2 repeater GETNEXTs
    assert all(decode_message(sent).pdu.pdu_type is PduType.GET_NEXT for sent in fake_client.sent)


def test_v1_manager_get_bulk_stops_at_end_of_mib_view() -> None:
    manager, fake_client = _build_manager(replies=[_V1Agent()] * 10)

    async def scenario() -> None:
        async with manager:
            bulk = await manager.get_bulk("1.3.6.1.2.1.2.2.1.2.2", max_repetitions=10)

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert len(bulk.varbinds) == 1
        assert bulk.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2)
        assert isinstance(bulk.varbinds[0].value, EndOfMibViewValue)

    asyncio.run(scenario())

    assert len(fake_client.sent) == 1


def test_v1_manager_get_bulk_stops_on_empty_getnext_response() -> None:
    def empty_reply(sent: bytes) -> bytes:
        request = decode_message(sent)
        return encode_message(
            SnmpMessage(
                version=0,
                community="public",
                pdu=Pdu(
                    pdu_type=PduType.RESPONSE,
                    request_id=request.pdu.request_id,
                    error_status=0,
                    error_index=0,
                    varbinds=(),
                ),
            )
        )

    manager, fake_client = _build_manager(replies=[empty_reply])

    async def scenario() -> None:
        async with manager:
            bulk = await manager.get_bulk("1.3.6.1.2.1.1.3.0", max_repetitions=5)

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert bulk.varbinds == ()

    asyncio.run(scenario())

    assert len(fake_client.sent) == 1


def test_v1_manager_get_bulk_propagates_getnext_error() -> None:
    def error_reply(sent: bytes) -> bytes:
        request = decode_message(sent)
        return encode_message(
            SnmpMessage(
                version=0,
                community="public",
                pdu=Pdu(
                    pdu_type=PduType.RESPONSE,
                    request_id=request.pdu.request_id,
                    error_status=2,
                    error_index=1,
                    varbinds=request.pdu.varbinds,
                ),
            )
        )

    manager, _ = _build_manager(replies=[error_reply])

    async def scenario() -> None:
        async with manager:
            bulk = await manager.get_bulk("1.3.6.1.2.1.1.3.0", max_repetitions=3)

        assert bulk.error_status is ErrorStatus.NO_SUCH_NAME
        assert bulk.error_index == 1
        assert bulk.varbinds == ()

    asyncio.run(scenario())


def test_v1_manager_ignores_v2c_response_and_times_out() -> None:
    def v2c_reply(sent: bytes) -> bytes:
        return _response_bytes(
            request_id=decode_message(sent).pdu.request_id,
            version=1,
        )

    manager, _ = _build_manager(replies=[v2c_reply])

    async def scenario() -> None:
        async with manager:
            await manager.get("1.3.6.1.2.1.1.3.0")

    with pytest.raises(RequestTimeoutError):
        asyncio.run(scenario())


def test_v1_manager_ignores_community_mismatch_and_times_out() -> None:
    def wrong_community(sent: bytes) -> bytes:
        return _response_bytes(
            request_id=decode_message(sent).pdu.request_id,
            community="private",
        )

    manager, _ = _build_manager(replies=[wrong_community])

    async def scenario() -> None:
        async with manager:
            await manager.get("1.3.6.1.2.1.1.3.0")

    with pytest.raises(RequestTimeoutError):
        asyncio.run(scenario())


def test_v1_manager_raises_on_timeout() -> None:
    manager, _ = _build_manager(replies=[RequestTimeoutError("timed out")])

    async def scenario() -> None:
        async with manager:
            await manager.get("1.3.6.1.2.1.1.3.0")

    with pytest.raises(RequestTimeoutError, match="timed out"):
        asyncio.run(scenario())
