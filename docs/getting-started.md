# Getting Started

`tsnmp` is a package-first SNMP manager runtime. Start with numeric OIDs and no bundle;
add compiled JSON only when you need symbolic resolution or better display metadata.

---

## Install

```bash
pip install trishul-snmp
```

For local development:

```bash
pip install -e ".[dev]"
```

Requires Python `>=3.10`.

---

## Scope

Current `v0.1` baseline:

- manager-only
- SNMPv2c-only
- read-only operations: `get`, `get_next`, `get_bulk`, `walk`, `bulkwalk`
- package-first Python API
- optional compiled-JSON bundle loading from a single module file or a bundle directory

Deliberately out of scope:

- raw MIB file or raw MIB directory ingestion
- runtime dependency on `trishul-smi`
- `set`
- SNMPv1
- SNMPv3
- traps/listener or agent/responder behavior

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

---

## Next

- [Python API](python-api.md)
- [CLI Reference](cli.md)
- [Bundle Contract](bundles.md)
