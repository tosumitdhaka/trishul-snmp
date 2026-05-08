from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from trishul_snmp import (
    CallbackObjectSource,
    ErrorStatus,
    InMemoryObjectSource,
    IntegerValue,
    NoSuchObjectValue,
    NullValue,
    OctetStringValue,
    RequestTimeoutError,
    TimeTicksValue,
    V2cManager,
    V2cResponder,
    load_bundle,
)
from trishul_snmp.errors import TransportError
from trishul_snmp.types import EndOfMibViewValue, SocketAddress
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
            "syntax": "Integer32",
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


def _skip_if_udp_restricted(exc: Exception) -> None:
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno in {1, 13}:
        pytest.skip(f"UDP sockets are not permitted in this environment: {cause}")


def _responder_port(responder: V2cResponder) -> int:
    local = responder.local_address
    assert local is not None
    return local[1]


@dataclass(frozen=True, slots=True)
class _FakeDatagram:
    data: bytes
    source_address: SocketAddress


class _FakeServer:
    def __init__(self, items: list[_FakeDatagram | Exception]) -> None:
        self._items = list(items)
        self.sent: list[tuple[bytes, SocketAddress]] = []
        self.local_address: SocketAddress | None = ("127.0.0.1", 40161)

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def receive(self) -> _FakeDatagram:
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def sendto(self, data: bytes, addr: SocketAddress) -> None:
        self.sent.append((data, addr))


def test_in_memory_object_source_supports_symbolic_targets_and_order(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle(tmp_path / "IF-MIB.json")
    source = InMemoryObjectSource(bundle=bundle)

    first_oid = source.set_object("IF-MIB::ifDescr.2", OctetStringValue(b"eth1"))
    inserted = source.set_objects(
        [
            ("IF-MIB::ifIndex.1", IntegerValue(1)),
            ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
        ]
    )

    assert first_oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2)
    assert inserted == (
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1),
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),
    )
    assert source.oids == (
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1),
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1),
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2),
    )
    assert source.lookup_exact((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1)) == OctetStringValue(b"eth0")
    assert source.lookup_next((1, 3, 6, 1, 2, 1, 2, 2)) == (
        (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1),
        IntegerValue(1),
    )
    assert source.delete_object("IF-MIB::ifDescr.2") is True
    assert source.delete_object("IF-MIB::ifDescr.2") is False


def test_callback_object_source_delegates() -> None:
    seen: list[tuple[str, tuple[int, ...]]] = []

    source = CallbackObjectSource(
        exact_lookup=lambda oid: seen.append(("exact", oid)) or IntegerValue(7),
        next_lookup=lambda oid: (
            seen.append(("next", oid)) or ((1, 3, 6, 1, 2), OctetStringValue(b"eth0"))
        ),
    )

    assert source.lookup_exact((1, 3, 6, 1)) == IntegerValue(7)
    assert source.lookup_next((1, 3, 6, 1)) == (
        (1, 3, 6, 1, 2),
        OctetStringValue(b"eth0"),
    )
    assert seen == [
        ("exact", (1, 3, 6, 1)),
        ("next", (1, 3, 6, 1)),
    ]


def test_v2c_responder_default_source_mutators_and_properties() -> None:
    responder = V2cResponder()

    assert responder.local_address is None
    assert isinstance(responder.source, InMemoryObjectSource)
    assert responder.set_object("1.3.6.1.2.1.1.3.0", TimeTicksValue(5)) == (
        1,
        3,
        6,
        1,
        2,
        1,
        1,
        3,
        0,
    )
    responder.clear_objects()
    assert responder.source.lookup_exact((1, 3, 6, 1, 2, 1, 1, 3, 0)) is None


def test_v2c_responder_serves_manager_reads(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle(tmp_path / "IF-MIB.json")
    source = InMemoryObjectSource(
        bundle=bundle,
        objects=[
            ("1.3.6.1.2.1.1.3.0", TimeTicksValue(12345)),
            ("IF-MIB::ifIndex.1", IntegerValue(1)),
            ("IF-MIB::ifIndex.2", IntegerValue(2)),
            ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
            ("IF-MIB::ifDescr.2", OctetStringValue(b"eth1")),
        ],
    )

    async def scenario() -> None:
        try:
            async with V2cResponder(
                host="127.0.0.1",
                port=0,
                communities=["public"],
                source=source,
            ) as responder:
                serve_task = asyncio.create_task(responder.serve(count=4))
                async with V2cManager(
                    host="127.0.0.1",
                    port=_responder_port(responder),
                    community="public",
                    timeout=0.5,
                    retries=0,
                    bundle=bundle,
                ) as manager:
                    get_response = await manager.get("IF-MIB::ifDescr.1")
                    next_response = await manager.get_next("IF-MIB::ifTable")
                    bulk_response = await manager.get_bulk(
                        "IF-MIB::ifTable",
                        non_repeaters=0,
                        max_repetitions=3,
                    )
                    missing_response = await manager.get("1.3.6.1.2.1.999.0")
                handled = await serve_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert handled == 4
        assert get_response.error_status is ErrorStatus.NO_ERROR
        assert get_response.varbinds[0].display_name == "IF-MIB::ifDescr.1"
        assert get_response.varbinds[0].display_value == "eth0"
        assert [varbind.display_name for varbind in next_response.varbinds] == [
            "IF-MIB::ifIndex.1",
        ]
        assert [varbind.display_name for varbind in bulk_response.varbinds] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
        ]
        assert isinstance(missing_response.varbinds[0].value, NoSuchObjectValue)
        assert missing_response.varbinds[0].display_value == "noSuchObject"

    asyncio.run(scenario())


def test_v2c_responder_serves_symbolic_walk(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())
    bundle = load_bundle(tmp_path / "IF-MIB.json")

    async def scenario() -> None:
        try:
            async with V2cResponder(
                host="127.0.0.1",
                port=0,
                communities=["public"],
                bundle=bundle,
            ) as responder:
                responder.set_objects(
                    [
                        ("IF-MIB::ifIndex.1", IntegerValue(1)),
                        ("IF-MIB::ifIndex.2", IntegerValue(2)),
                        ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
                        ("IF-MIB::ifDescr.2", OctetStringValue(b"eth1")),
                    ]
                )
                serve_task = asyncio.create_task(responder.serve(count=1))
                async with V2cManager(
                    host="127.0.0.1",
                    port=_responder_port(responder),
                    community="public",
                    timeout=0.5,
                    retries=0,
                    bundle=bundle,
                ) as manager:
                    walked = await manager.walk("IF-MIB::ifTable", max_repetitions=10)
                handled = await serve_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert handled == 1
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

    asyncio.run(scenario())


def test_v2c_responder_community_filter_causes_timeout() -> None:
    async def scenario() -> None:
        try:
            async with V2cResponder(
                host="127.0.0.1",
                port=0,
                communities=["private"],
                objects=[("1.3.6.1.2.1.1.3.0", TimeTicksValue(12345))],
            ) as responder:
                serve_task = asyncio.create_task(responder.serve())
                async with V2cManager(
                    host="127.0.0.1",
                    port=_responder_port(responder),
                    community="public",
                    timeout=0.05,
                    retries=0,
                ) as manager:
                    with pytest.raises(RequestTimeoutError, match="timed out"):
                        await manager.get("1.3.6.1.2.1.1.3.0")
                await responder.close()
                handled = await serve_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert handled == 0

    asyncio.run(scenario())


def test_v2c_responder_supports_callback_source() -> None:
    objects = [
        ((1, 3, 6, 1, 2, 1, 1, 3, 0), TimeTicksValue(12345)),
        ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1), IntegerValue(1)),
    ]

    def exact_lookup(oid: tuple[int, ...]):
        for known_oid, value in objects:
            if known_oid == oid:
                return value
        return None

    def next_lookup(oid: tuple[int, ...]):
        for known_oid, value in objects:
            if known_oid > oid:
                return known_oid, value
        return None

    async def scenario() -> None:
        try:
            async with V2cResponder(
                host="127.0.0.1",
                port=0,
                communities=["public"],
                source=CallbackObjectSource(
                    exact_lookup=exact_lookup,
                    next_lookup=next_lookup,
                ),
            ) as responder:
                serve_task = asyncio.create_task(responder.serve(count=2))
                async with V2cManager(
                    host="127.0.0.1",
                    port=_responder_port(responder),
                    community="public",
                    timeout=0.5,
                    retries=0,
                ) as manager:
                    exact_response = await manager.get("1.3.6.1.2.1.1.3.0")
                    next_response = await manager.get_next("1.3.6.1.2.1.1.3.0")
                handled = await serve_task
        except Exception as exc:
            _skip_if_udp_restricted(exc)
            raise

        assert handled == 2
        assert exact_response.varbinds[0].display_value == "12345"
        assert next_response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1)

    asyncio.run(scenario())


def test_v2c_responder_rejects_object_seed_with_custom_source() -> None:
    with pytest.raises(ValueError, match="objects cannot be used when source is provided"):
        V2cResponder(
            source=CallbackObjectSource(
                exact_lookup=lambda oid: None,
                next_lookup=lambda oid: None,
            ),
            objects=[("1.3.6.1.2.1.1.3.0", TimeTicksValue(1))],
        )


def test_v2c_responder_rejects_in_memory_only_mutators_with_custom_source() -> None:
    responder = V2cResponder(
        source=CallbackObjectSource(
            exact_lookup=lambda oid: None,
            next_lookup=lambda oid: None,
        )
    )

    with pytest.raises(TypeError, match="InMemoryObjectSource"):
        responder.set_object("1.3.6.1.2.1.1.3.0", TimeTicksValue(1))
    with pytest.raises(TypeError, match="InMemoryObjectSource"):
        responder.clear_objects()


def test_v2c_responder_serve_validation_and_forever_forwarding(monkeypatch) -> None:
    responder = V2cResponder()

    async def bad_count() -> None:
        with pytest.raises(ValueError, match="count cannot be negative"):
            await responder.serve(count=-1)

    async def raise_transport() -> None:
        async def fail() -> None:
            raise TransportError("boom")

        responder.handle_request = fail  # type: ignore[method-assign]
        with pytest.raises(TransportError, match="boom"):
            await responder.serve(count=1)

    seen: list[int] = []

    async def fake_serve(*, count: int = 0) -> int:
        seen.append(count)
        return 0

    async def call_forever() -> None:
        monkeypatch.setattr(responder, "serve", fake_serve)
        await responder.serve_forever()

    asyncio.run(bad_count())
    asyncio.run(raise_transport())
    asyncio.run(call_forever())
    assert seen == [0]


def test_v2c_responder_handle_request_skips_invalid_and_unsupported_messages() -> None:
    valid_get = encode_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.GET,
                request_id=7,
                error_status=0,
                error_index=0,
                varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),),
            ),
        )
    )
    unsupported = encode_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.RESPONSE,
                request_id=8,
                error_status=0,
                error_index=0,
                varbinds=(),
            ),
        )
    )
    server = _FakeServer(
        [
            _FakeDatagram(data=b"not-snmp", source_address=("127.0.0.1", 40000)),
            _FakeDatagram(data=unsupported, source_address=("127.0.0.1", 40000)),
            _FakeDatagram(data=valid_get, source_address=("127.0.0.1", 40001)),
        ]
    )
    responder = V2cResponder(objects=[("1.3.6.1.2.1.1.3.0", TimeTicksValue(9))])
    responder._server = server  # type: ignore[attr-defined]

    async def scenario() -> None:
        await responder.handle_request()

    asyncio.run(scenario())

    assert len(server.sent) == 1
    response = decode_message(server.sent[0][0])
    assert response.pdu.pdu_type is PduType.RESPONSE
    assert response.pdu.varbinds[0].value == TimeTicksValue(9)


def test_v2c_responder_set_and_bulk_edge_cases() -> None:
    responder = V2cResponder(objects=[("1.3.6.1.2.1.1.3.0", TimeTicksValue(9))])

    set_response = responder._build_response_pdu(
        Pdu(
            pdu_type=PduType.SET,
            request_id=4,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=IntegerValue(1)),),
        )
    )
    unsupported = responder._build_response_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=Pdu(
                pdu_type=PduType.RESPONSE,
                request_id=5,
                error_status=0,
                error_index=0,
                varbinds=(),
            ),
        )
    )
    bulk = responder._build_bulk_varbinds(
        (
            RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 3, 0), value=NullValue()),
            RawVarBind(oid=(1, 3, 6, 1, 2, 1, 999, 0), value=NullValue()),
        ),
        non_repeaters=-1,
        max_repetitions=0,
    )
    end_of_mib = responder._lookup_next_varbind((9, 9, 9))

    assert set_response is not None
    assert set_response.error_status == int(ErrorStatus.NOT_WRITABLE)
    assert set_response.error_index == 1
    assert unsupported is None
    assert bulk == ()
    assert isinstance(end_of_mib.value, EndOfMibViewValue)
