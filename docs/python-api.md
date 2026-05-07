# Python API

Import `trishul_snmp` directly for runtime use. The CLI is a thin wrapper over the
same package surface.

---

## Main entry points

| Symbol | Kind | Purpose |
|---|---|---|
| `V2cManager` | class | Async SNMPv2c manager client |
| `load_bundle(path)` | function | Load a compiled module JSON file or bundle directory |
| `MibBundle` | class | Bundle translation and enrichment handle |
| `Response` | dataclass | Result for `get`, `get_next`, and `get_bulk` |
| `VarBind` | dataclass | OID/value pair plus optional enrichment fields |

Important public enums and value models:

- `ErrorStatus`
- `IntegerValue`
- `OctetStringValue`
- `ObjectIdentifierValue`
- `TimeTicksValue`
- `Counter32Value`
- `Counter64Value`
- `Gauge32Value`
- `IpAddressValue`
- `NoSuchObjectValue`
- `NoSuchInstanceValue`
- `EndOfMibViewValue`

---

## `V2cManager`

```python
from trishul_snmp import V2cManager

manager = V2cManager(
    host="10.0.0.10",
    community="public",
    port=161,
    timeout=2.0,
    retries=1,
    bundle=None,
    max_datagram_size=65535,
)
```

### Constructor fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target hostname or IP address |
| `community` | `str` | required | SNMPv2c community string |
| `port` | `int` | `161` | Target UDP port |
| `timeout` | `float` | `2.0` | Per-request timeout in seconds |
| `retries` | `int` | `1` | Retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle for symbolic resolution and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum datagram size for UDP receive |

### Lifecycle

Use it as an async context manager:

```python
async with V2cManager(host="10.0.0.10", community="public") as manager:
    ...
```

Or manage transport explicitly:

```python
manager = V2cManager(host="10.0.0.10", community="public")
await manager.open()
try:
    ...
finally:
    await manager.close()
```

---

## Operations

| Method | Returns | Notes |
|---|---|---|
| `get(*targets)` | `Response` | SNMP GET |
| `get_next(*targets)` | `Response` | SNMP GETNEXT |
| `get_bulk(*targets, non_repeaters=0, max_repetitions=10)` | `Response` | SNMP GETBULK |
| `walk(root, bulk=True, max_repetitions=10)` | `tuple[VarBind, ...]` | Subtree walk using GETBULK by default |
| `bulkwalk(root, max_repetitions=10)` | `tuple[VarBind, ...]` | Explicit GETBULK subtree walk |

Examples:

```python
response = await manager.get("1.3.6.1.2.1.1.3.0")
response = await manager.get("IF-MIB::ifDescr.1", "IF-MIB::ifIndex.1")
response = await manager.get_next("1.3.6.1.2.1.2.2")
response = await manager.get_bulk("IF-MIB::ifTable", non_repeaters=0, max_repetitions=10)
rows = await manager.walk("IF-MIB::ifTable")
rows = await manager.walk("IF-MIB::ifTable", bulk=False)
rows = await manager.bulkwalk("IF-MIB::ifTable", max_repetitions=10)
```

---

## Input rules

All manager operations accept:

- numeric OID text such as `1.3.6.1.2.1.1.3.0`
- numeric OID sequences such as `(1, 3, 6, 1, 2, 1, 1, 3, 0)`
- symbolic targets such as `IF-MIB::ifDescr.1` only when a bundle is loaded

If symbolic input is used with no bundle loaded, `UnknownSymbolError` is raised.

---

## Response model

`get`, `get_next`, and `get_bulk` return a `Response`.

| Field | Description |
|---|---|
| `request_id` | SNMP request identifier used for the exchange |
| `error_status` | `ErrorStatus` enum describing agent-side request status |
| `error_index` | Agent-provided index into the request varbind list |
| `varbinds` | Tuple of decoded `VarBind` objects |

Each `VarBind` exposes:

| Field | Description |
|---|---|
| `oid` | Numeric OID tuple |
| `oid_str` | Dotted-string OID |
| `value` | Raw typed SNMP value object |
| `value_type` | Stable type label for display and JSON output |
| `match` | Optional bundle lookup match |
| `display_name` | Optional symbolic name derived from the bundle |
| `display_value` | Rendered value string with optional bundle-aware formatting |

The raw typed value is always preserved. Enrichment only affects the additional
display fields.

---

## Bundle helpers

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./mibs-json")

print(bundle.translate("IF-MIB::ifDescr.7"))
print(bundle.translate("1.3.6.1.2.1.2.2.1.2.7"))
print(bundle.resolve("IF-MIB::ifDescr.7"))
print(bundle.lookup("1.3.6.1.2.1.2.2.1.2.7"))
```

Main bundle methods:

- `translate()`
- `resolve()`
- `lookup()`
- `resolve_type()`
- `modules`

---

## Error model

Bundle and translation errors:

- `BundleError`
- `BundleValidationError`
- `TranslationError`
- `UnknownSymbolError`
- `UnknownOidError`
- `InvalidOidError`

Runtime and protocol errors:

- `TransportError`
- `RequestTimeoutError`
- `ProtocolError`

---

## Notes

- The runtime core stays numeric internally.
- Bundle-backed translation happens at the API edge before send.
- Bundle-backed enrichment happens after receive.
- `tsnmp` does not require `trishul-smi` to be installed at runtime.
