from __future__ import annotations

import asyncio
import json
from itertools import count
from pathlib import Path

from trishul_snmp import ErrorStatus, V2cManager, load_bundle
from trishul_snmp.types import EndOfMibViewValue, OctetStringValue, TimeTicksValue
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


class _NoopClient:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeDispatcher:
    def __init__(self) -> None:
        self._request_ids = count(1)
        self._objects: list[tuple[tuple[int, ...], object]] = [
            ((1, 3, 6, 1, 2, 1, 1, 3, 0), TimeTicksValue(12345)),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1), OctetStringValue(b"1")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 2), OctetStringValue(b"2")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 1), OctetStringValue(b"eth0")),
            ((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 2), OctetStringValue(b"eth1")),
        ]

    async def send_pdu(
        self,
        pdu_type: PduType,
        varbinds: tuple[RawVarBind, ...],
        *,
        error_status: int = 0,
        error_index: int = 0,
    ) -> Pdu:
        request_id = next(self._request_ids)
        if pdu_type == PduType.GET:
            response_varbinds = tuple(self._lookup_exact(vb.oid) for vb in varbinds)
        elif pdu_type == PduType.GET_NEXT:
            response_varbinds = tuple(self._lookup_next(vb.oid) for vb in varbinds)
        elif pdu_type == PduType.GET_BULK:
            seed = varbinds[0].oid
            response_varbinds = tuple(self._bulk_walk(seed, error_index))
        else:
            raise AssertionError(f"Unexpected PDU type {pdu_type!r}")

        return Pdu(
            pdu_type=PduType.RESPONSE,
            request_id=request_id,
            error_status=0,
            error_index=0,
            varbinds=response_varbinds,
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


def _build_manager(*, bundle_path: Path) -> V2cManager:
    bundle = load_bundle(bundle_path)
    manager = V2cManager(host="127.0.0.1", port=161, community="public", bundle=bundle)
    manager._session._client = _NoopClient()  # type: ignore[attr-defined]
    manager._session._dispatcher = FakeDispatcher()  # type: ignore[attr-defined]
    return manager


def test_v2c_manager_get_and_symbolic_translation(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())

    async def scenario() -> None:
        async with _build_manager(bundle_path=tmp_path / "IF-MIB.json") as manager:
            response = await manager.get("IF-MIB::ifDescr.1")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].display_name == "IF-MIB::ifDescr.1"
        assert response.varbinds[0].display_value == "eth0"

    asyncio.run(scenario())


def test_v2c_manager_get_bulk_and_walk(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())

    async def scenario() -> None:
        async with _build_manager(bundle_path=tmp_path / "IF-MIB.json") as manager:
            bulk = await manager.get_bulk("IF-MIB::ifTable", max_repetitions=3)
            walked = await manager.walk("IF-MIB::ifTable", max_repetitions=10)

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert [vb.display_name for vb in bulk.varbinds] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
        ]
        assert [vb.display_name for vb in walked] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
            "IF-MIB::ifDescr.2",
        ]

    asyncio.run(scenario())


def test_v2c_manager_get_next_and_walk_variants(tmp_path: Path) -> None:
    _write_json(tmp_path / "IF-MIB.json", _if_mib_payload())

    async def scenario() -> None:
        async with _build_manager(bundle_path=tmp_path / "IF-MIB.json") as manager:
            next_response = await manager.get_next("IF-MIB::ifTable")
            next_walked = await manager.walk("IF-MIB::ifTable", bulk=False, max_repetitions=10)
            bulk_walked = await manager.bulkwalk("IF-MIB::ifTable", max_repetitions=10)

        assert next_response.error_status is ErrorStatus.NO_ERROR
        assert [vb.display_name for vb in next_response.varbinds] == [
            "IF-MIB::ifIndex.1",
        ]
        assert [vb.display_name for vb in next_walked] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
            "IF-MIB::ifDescr.2",
        ]
        assert [vb.display_name for vb in bulk_walked] == [
            "IF-MIB::ifIndex.1",
            "IF-MIB::ifIndex.2",
            "IF-MIB::ifDescr.1",
            "IF-MIB::ifDescr.2",
        ]

    asyncio.run(scenario())
