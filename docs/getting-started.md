# Getting Started

`tsnmp` is a package-first SNMP runtime. Start with numeric OIDs and no bundle;
add compiled JSON only when you need symbolic resolution or better display metadata.

---

## Install

```bash
pip install trishul-snmp
```

For SNMPv3 auth/priv support (HMAC and AES-128-CFB encryption), install the `[v3]` extra:

```bash
pip install "trishul-snmp[v3]"
```

The base package always imports correctly without `[v3]`; only calling auth or priv methods
at runtime requires it.

For local development:

```bash
pip install -e ".[dev,v3]"
```

Requires Python `>=3.10`.

---

## Scope

Current main-branch baseline:

- manager operations plus notification send/listen/decode
- narrow read-only responder/simulator support
- SNMPv2c and SNMPv3 USM (noAuthNoPriv, authNoPriv, authPriv AES-128)
- read-only operations: `get`, `get_next`, `get_bulk`, `walk`, `bulkwalk`
- package-first Python API
- optional compiled-JSON bundle loading from a single module file or a bundle directory

Deliberately out of scope:

- raw MIB file or raw MIB directory ingestion
- runtime dependency on `trishul-smi`
- `set`
- SNMPv1
- full agent or writable responder behavior

---

## First numeric GET

This works with no bundle loaded.

```python
import asyncio

from trishul_snmp import V2cManager


async def main() -> None:
    async with V2cManager(host="10.0.0.10", community="public") as manager:
        response = await manager.get("1.3.6.1.2.1.1.3.0")
        for varbind in response.varbinds:
            print(varbind.oid_str, varbind.value_type, varbind.display_value)


asyncio.run(main())
```

---

## First symbolic GET

If you already have compiled JSON artifacts, load them and use symbolic names.

```python
import asyncio

from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./IF-MIB.json")


async def main() -> None:
    async with V2cManager(
        host="10.0.0.10",
        community="public",
        bundle=bundle,
    ) as manager:
        response = await manager.get("IF-MIB::ifDescr.1")
        for varbind in response.varbinds:
            print(varbind.display_name, "=", varbind.display_value)


asyncio.run(main())
```

---

## First walk

```python
import asyncio

from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./mibs-json")


async def main() -> None:
    async with V2cManager(
        host="10.0.0.10",
        community="public",
        bundle=bundle,
    ) as manager:
        rows = await manager.walk("IF-MIB::ifTable")
        for row in rows:
            print(row.display_name, "=", row.display_value)


asyncio.run(main())
```

---

## First notification send

```python
import asyncio

from trishul_snmp import IntegerValue, V2cNotifier, load_bundle

bundle = load_bundle("./mibs-json")


async def main() -> None:
    async with V2cNotifier(
        host="10.0.0.20",
        community="public",
        bundle=bundle,
    ) as notifier:
        await notifier.send_trap(
            "IF-MIB::linkDown",
            varbinds=[("IF-MIB::ifIndex.7", IntegerValue(7))],
            uptime=123,
        )


asyncio.run(main())
```

---

## First read-only responder

```python
import asyncio

from trishul_snmp import IntegerValue, OctetStringValue, V2cResponder, load_bundle

bundle = load_bundle("./mibs-json")


async def main() -> None:
    async with V2cResponder(
        host="127.0.0.1",
        port=1161,
        communities=["public"],
        bundle=bundle,
    ) as responder:
        responder.set_objects(
            [
                ("IF-MIB::ifIndex.1", IntegerValue(1)),
                ("IF-MIB::ifDescr.1", OctetStringValue(b"eth0")),
            ]
        )
        await responder.serve_forever()


asyncio.run(main())
```

---

## Offline translation

No SNMP traffic is involved here.

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./mibs-json")

print(bundle.translate("IF-MIB::ifDescr.7"))
print(bundle.translate("1.3.6.1.2.1.2.2.1.2.7"))
```

---

## End-to-end flows

Offline translation:

1. Compile MIBs separately with `tsmi` or provide an equivalent supported JSON artifact.
2. Load a compiled module JSON file or bundle directory with `load_bundle()`.
3. `tsnmp` validates and normalizes the bundle.
4. Translation resolves symbol to numeric OID and numeric OID back to symbolic name.

Live numeric GET with no bundle:

1. Call `manager.get()` with numeric OIDs.
2. The manager builds numeric request varbinds.
3. The transport sends an SNMPv2c message over UDP.
4. The response is decoded into typed SNMP values.
5. `display_value` is still available without symbolic metadata.

Live symbolic walk with a bundle:

1. Load compiled JSON artifacts with `load_bundle()`.
2. Call `manager.walk("IF-MIB::ifTable")`.
3. The symbolic root is translated to a numeric OID before network I/O.
4. The walk uses `GETBULK` by default or `GETNEXT` when requested.
5. Returned numeric OIDs are enriched back into symbolic names and formatted display values.

Live notification send:

1. Load a bundle only if you want symbolic notification or varbind targets.
2. Call `send_trap()` or `send_inform()` on `V2cNotifier`.
3. `tsnmp` auto-populates `sysUpTime.0` and `snmpTrapOID.0` unless you override them.
4. Inform requests wait for a matching response; traps are fire-and-forget.

Responder simulation:

1. Create `V2cResponder` with either the default in-memory source or a callback-backed source.
2. Seed exact objects numerically or symbolically when a bundle is loaded.
3. Call `serve()` or `serve_forever()` to answer `GET`, `GET_NEXT`, and `GET_BULK`.
4. Missing exact objects return `noSuchObject`; end-of-tree lookups return `endOfMibView`.

---

## Where Next

- [Python API](python-api.md) — primary package surface for manager, notifier, listener, responder, and bundle usage
- [CLI Reference](cli.md) — thin wrapper for smoke testing, notifications, and offline decode
- [Ecosystem and Compatibility](ecosystem.md) — `tsnmp`/`tsmi` split, supported inputs, and current pairing status
- [Architecture](architecture.md) — package layering and end-to-end runtime call flows
- [Bundle Contract](bundles.md) — compiled JSON expectations, sidecars, and validation rules
