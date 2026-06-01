# Python API

Import `trishul_snmp` directly for runtime use. The CLI is a thin wrapper over the
same package surface.

---

## Main entry points

| Symbol | Kind | Purpose |
|---|---|---|
| `V2cManager` | class | Async SNMPv2c manager client |
| `V3Manager` | class | Async SNMPv3 USM manager client |
| `V2cNotifier` | class | Async SNMPv2c trap and inform sender |
| `V3Notifier` | class | Async SNMPv3 USM notifier; informs use peer discovery, traps require `UsmLocalEngine` |
| `V2cNotificationListener` | class | Async SNMPv2c trap and inform listener |
| `V2cResponder` | class | Async SNMPv2c read-only responder for simulator-style use |
| `decode_notification(data, *, bundle=None, source_address=None)` | function | Offline decode for BER-encoded SNMPv2c traps and informs |
| `load_bundle(path)` | function | Load a compiled module JSON file or bundle directory |
| `MibBundle` | class | Bundle translation and enrichment handle |
| `InMemoryObjectSource` | class | Mutable in-memory responder object source; accepts static values and simulation rules |
| `CallbackObjectSource` | class | Callback-backed responder object source |
| `SimulationRule` | protocol | Protocol for dynamic OID value rules |
| `CounterRule` | class | Monotonically-increasing counter rule |
| `RandomNumericRule` | class | Random integer in a range, re-sampled on each read |
| `UptimeRule` | class | Auto-incrementing timeticks (centiseconds) since construction |
| `TimestampRule` | class | Current Unix epoch time as a scalar value |
| `Response` | dataclass | Result for `get`, `get_next`, and `get_bulk` |
| `VarBind` | dataclass | OID/value pair plus optional enrichment fields |
| `NotificationEvent` | dataclass | Structured inbound notification event |
| `NotificationMemberBinding` | dataclass | Declared notification member paired with the received varbind |

SNMPv3 USM types (require `pip install "trishul-snmp[v3]"` for auth/priv methods):

- `UsmUser`
- `UsmLocalEngine`
- `AuthProtocol`
- `PrivProtocol`
- `UsmModel`

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

## `V3Manager`

Requires `pip install "trishul-snmp[v3]"` for auth/priv methods.

```python
from trishul_snmp import V3Manager, UsmUser, AuthProtocol, PrivProtocol

user = UsmUser(
    username="myuser",
    auth_protocol=AuthProtocol.SHA1,
    auth_key=b"my-auth-passphrase",
    priv_protocol=PrivProtocol.AES128,
    priv_key=b"my-priv-passphrase",
)

async with V3Manager(host="10.0.0.10", user=user) as manager:
    response = await manager.get("1.3.6.1.2.1.1.3.0")
```

### Constructor fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target hostname or IP address |
| `user` | `UsmUser` | required | USM credentials |
| `port` | `int` | `161` | Target UDP port |
| `timeout` | `float` | `2.0` | Per-request timeout in seconds |
| `retries` | `int` | `1` | Retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle for symbolic resolution and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum datagram size for UDP receive |
| `context_name` | `bytes` | `b""` | SNMPv3 context name |

`V3Manager.open()` runs RFC 3414 engine discovery automatically before the first request.
All manager operations (`get`, `get_next`, `get_bulk`, `walk`, `bulkwalk`) are identical
to `V2cManager`.

### `UsmUser` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `username` | `str` | required | USM security name |
| `auth_protocol` | `AuthProtocol` | `AuthProtocol.NONE` | HMAC algorithm |
| `auth_key` | `bytes` | `b""` | Auth passphrase (or pre-localized key if `auth_key_localized=True`) |
| `auth_key_localized` | `bool` | `False` | Skip RFC 3414 key derivation and use `auth_key` bytes directly |
| `priv_protocol` | `PrivProtocol` | `PrivProtocol.NONE` | Privacy algorithm |
| `priv_key` | `bytes` | `b""` | Priv passphrase |

`AuthProtocol` values: `NONE`, `MD5`, `SHA1`, `SHA256`

`PrivProtocol` values: `NONE`, `AES128` (`DES` enum value exists for wire identification but raises `ProtocolError` at runtime)

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
- `resolve_node()`
- `resolve_type()`
- `modules`
- `iter_objects(*, module=None, type_filter=None)` — iterate over object nodes
- `iter_notifications(*, module=None)` — iterate over notification nodes
- `search(query, *, module=None, type_filter=None, limit=100)` — case-insensitive substring search over node names and descriptions

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
- `AuthenticationError` (subclass of `ProtocolError`; raised on USM HMAC verification failure)

---

## Notes

- The runtime core stays numeric internally.
- Bundle-backed translation happens at the API edge before send.
- Bundle-backed enrichment happens after receive.
- `tsnmp` does not require `trishul-smi` to be installed at runtime.

---

## `V2cNotifier`

```python
from trishul_snmp import V2cNotifier

notifier = V2cNotifier(
    host="10.0.0.20",
    community="public",
    port=162,
    timeout=2.0,
    retries=1,
    bundle=None,
    max_datagram_size=65535,
)
```

Use it as an async context manager just like `V2cManager`.

Available methods:

| Method | Returns | Notes |
|---|---|---|
| `send_trap(notification, *, varbinds=(), uptime=0)` | `int` | Fire-and-forget SNMPv2c trap send; returns the assigned request id |
| `send_inform(notification, *, varbinds=(), uptime=0)` | `Response` | Sends an SNMPv2c inform and waits for the matching response |

Input rules:

- `notification` accepts numeric OIDs or `MODULE::symbol` when a bundle is loaded
- `varbinds` accepts `(target, value)` pairs where `target` is numeric or symbolic
- `sysUpTime.0` and `snmpTrapOID.0` are auto-populated if not provided explicitly

Example:

```python
from trishul_snmp import IntegerValue, V2cNotifier, load_bundle

bundle = load_bundle("./mibs-json")

async with V2cNotifier(host="10.0.0.20", community="public", bundle=bundle) as notifier:
    await notifier.send_trap(
        "IF-MIB::linkDown",
        varbinds=[("IF-MIB::ifIndex.7", IntegerValue(7))],
        uptime=123,
    )
```

---

## `V3Notifier`

Requires `pip install "trishul-snmp[v3]"` for auth/priv methods.

Constructor fields are identical to `V2cNotifier` except `community` is replaced by
`user: UsmUser`, and SNMPv3 adds `context_name: bytes = b""` plus
`local_engine: UsmLocalEngine | None = None`.

`send_inform()` is fully supported. Informs are confirmed-class PDUs that require the
receiver's engine parameters; `V3Notifier` discovers those lazily on first use.

`send_trap()` is also supported, but only when `local_engine` is configured. SNMPv3 traps are
unconfirmed PDUs that must carry the sender's own authoritative engine state (RFC 3412 §7.1.9),
so the caller must supply it explicitly.

### `UsmLocalEngine` fields

| Field | Type | Description |
|---|---|---|
| `engine_id` | `bytes` | Sender authoritative engine-id |
| `engine_boots` | `int` | Sender authoritative `engineBoots` |
| `engine_time` | `int` | Sender authoritative `engineTime` |

Example:

```python
from trishul_snmp import UsmLocalEngine, UsmUser, V3Notifier

user = UsmUser(username="notify")
local_engine = UsmLocalEngine(
    engine_id=bytes.fromhex("8000010203"),
    engine_boots=7,
    engine_time=99,
)

async with V3Notifier(host="10.0.0.20", user=user, local_engine=local_engine) as notifier:
    await notifier.send_trap("1.3.6.1.6.3.1.1.5.3")
```

---

## `V2cNotificationListener`

```python
from trishul_snmp import V2cNotificationListener

listener = V2cNotificationListener(
    host="0.0.0.0",
    port=162,
    communities=["public"],
    bundle=None,
)
```

Use it as an async context manager, then either call `receive()` directly or
iterate over it asynchronously.

Available methods and properties:

| Symbol | Returns | Notes |
|---|---|---|
| `receive()` | `NotificationEvent` | Waits for the next matching trap or inform |
| `local_address` | `SocketAddress \| None` | Bound local address once the listener is open |
| `__aiter__()` | async iterator | Async iterator-first consumption model |

Behavior:

- trap PDUs are surfaced as events
- inform PDUs are acknowledged automatically before the event is returned
- `communities=None` accepts any SNMPv2c community
- `communities=[...]` acts as an allowlist

Example:

```python
from trishul_snmp import V2cNotificationListener

async with V2cNotificationListener(host="127.0.0.1", port=9162, communities=["public"]) as listener:
    event = await listener.receive()
    print(event.pdu_type, event.community, event.source_address)
```

`NotificationEvent` currently exposes:

| Field | Description |
|---|---|
| `request_id` | SNMP request identifier carried by the trap or inform |
| `community` | Source SNMPv2c community string |
| `source_address` | Remote UDP source address tuple, or `None` for offline decode |
| `pdu_type` | `"snmpv2-trap"` or `"inform-request"` |
| `varbinds` | Tuple of decoded `VarBind` objects |
| `notification_oid` | Numeric notification OID extracted from `snmpTrapOID.0` when present |
| `notification_name` | Bundle-backed symbolic notification name when available |
| `notification_description` | Retained notification description when available |
| `uptime` | Numeric `sysUpTime.0` value when present |
| `member_bindings` | Declared notification members paired with received varbinds |

Convenience properties:

- `source_host`
- `source_port`
- `is_inform`
- `declared_members`

Methods:

- `to_dict()` — returns a JSON-safe `dict` containing all event fields, varbinds, and member bindings

`NotificationMemberBinding` exposes:

| Field | Description |
|---|---|
| `member` | Retained `MibMemberRef` from the compiled JSON notification metadata |
| `varbind` | Matching decoded `VarBind`, or `None` when the notification omitted it |

Convenience property:

- `symbolic`

---

## Offline notification decode

```python
from trishul_snmp import decode_notification, load_bundle

bundle = load_bundle("./mibs-json")
event = decode_notification(raw_bytes, bundle=bundle)

print(event.notification_name)
print(event.member_bindings)
```

`decode_notification()` accepts a BER-encoded SNMPv2c trap or inform message and
returns the same `NotificationEvent` model used by the live listener API.

Notes:

- `source_address` is optional because offline payloads may not have transport metadata
- bundle-backed enrichment is optional; numeric decode still works with no bundle

---

## `V2cResponder`

```python
from trishul_snmp import V2cResponder

responder = V2cResponder(
    host="127.0.0.1",
    port=1161,
    communities=["public"],
)
```

`V2cResponder` is a narrow read-only responder meant for tests, demos, and
simulator-style use. It handles `GET`, `GET_NEXT`, and `GET_BULK`.

Constructor fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Listener bind hostname or IP address |
| `port` | `int` | `161` | Listener UDP port |
| `communities` | `Sequence[str] \| None` | `None` | Optional SNMPv2c community allowlist |
| `source` | `ResponderSource \| None` | `None` | Optional custom data source |
| `objects` | iterable | empty | Initial object seed when using the default in-memory source |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle for symbolic object registration in the default in-memory source |

Available methods and properties:

| Symbol | Returns | Notes |
|---|---|---|
| `serve(count=0)` | `int` | Serves up to `count` requests, or runs until closed when `count=0` |
| `serve_forever()` | `None` | Infinite serve loop until closed |
| `handle_request()` | `None` | Handles the next supported request |
| `local_address` | `SocketAddress \| None` | Bound local address once open |
| `source` | `ResponderSource` | Active data source object |
| `set_object(...)` | `OID` | Convenience mutator for the default in-memory source only |
| `set_objects(...)` | `tuple[OID, ...]` | Convenience bulk mutator for the default in-memory source only |
| `clear_objects()` | `None` | Clears the default in-memory source only |

Behavior:

- `GET` missing objects return `noSuchObject`
- `GET_NEXT` and `GET_BULK` return `endOfMibView` at the end of the object set
- `SET` requests are rejected as `notWritable`
- unsupported inbound PDU types are ignored

Example:

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

## Responder sources

`V2cResponder` uses a small read-only source interface:

- `lookup_exact(oid)` -> `SnmpValueType | None`
- `lookup_next(oid)` -> `tuple[OID, SnmpValueType] | None`

Included helpers:

- `InMemoryObjectSource`
- `CallbackObjectSource`

`InMemoryObjectSource` accepts numeric or symbolic targets when constructed with a
bundle. `CallbackObjectSource` is useful when the simulated values need to be
derived dynamically rather than stored in a static table.

---

## Simulation rules

`InMemoryObjectSource` accepts simulation rules alongside static values. Rules
are evaluated on every `lookup_exact` or `lookup_next` call.

```python
from trishul_snmp import (
    CounterRule, RandomNumericRule, UptimeRule, TimestampRule,
    InMemoryObjectSource,
)

source = InMemoryObjectSource()
source.set_object("1.3.6.1.2.1.1.3.0", UptimeRule())
source.set_object("1.3.6.1.2.1.2.2.1.10.1", CounterRule(increment=1024))
source.set_object("1.3.6.1.2.1.2.2.1.5.1", RandomNumericRule(min=1_000_000, max=1_000_000_000))
```

| Rule | Default value type | Behavior |
|---|---|---|
| `CounterRule(*, start=0, increment=1, value_type=Counter32Value)` | `Counter32Value` | Increments by `increment` on each read |
| `RandomNumericRule(*, min, max, value_type=Gauge32Value)` | `Gauge32Value` | Returns `random.randint(min, max)` on each read |
| `UptimeRule()` | `TimeTicksValue` | Elapsed centiseconds since the rule was constructed |
| `TimestampRule(*, value_type=IntegerValue)` | `IntegerValue` | Current Unix epoch time on each read |

Use `InMemoryObjectSource.from_bundle()` to auto-populate a source from a bundle:

```python
from trishul_snmp import InMemoryObjectSource, load_bundle

bundle = load_bundle("./mibs-json")
source = InMemoryObjectSource.from_bundle(bundle, max_instances=2)
```

This generates scalar `.0` instances and column instances `1..max_instances` for
every accessible, non-obsolete object in the bundle, with syntax-appropriate
default values (`Counter32Value(0)`, `OctetStringValue(b"")`, etc.).
