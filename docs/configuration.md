# Configuration Reference

All runtime configuration is explicit on the manager, notifier, listener, and responder
constructors and `load_bundle()`. The CLI maps directly to these knobs; there is no hidden
global config layer.

```python
from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./IF-MIB.json")
manager = V2cManager(
    host="10.0.0.10",
    community="public",
    timeout=2.0,
    retries=1,
    bundle=bundle,
)
```

---

## `V2cManager` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target hostname or IP address |
| `community` | `str` | required | SNMPv2c community string |
| `port` | `int` | `161` | Target UDP port |
| `timeout` | `float` | `2.0` | Per-request timeout in seconds |
| `retries` | `int` | `1` | Retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for symbolic translation and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum UDP datagram size for receive operations |

Validation notes:

- `timeout` must be greater than `0`
- `retries` cannot be negative
- symbolic targets require a loaded bundle

---

## `V1Manager` fields

`V1Manager` uses the same fields as `V2cManager`:

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target hostname or IP address |
| `community` | `str` | required | SNMPv1 community string |
| `port` | `int` | `161` | Target UDP port |
| `timeout` | `float` | `2.0` | Per-request timeout in seconds |
| `retries` | `int` | `1` | Retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for symbolic translation and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum UDP datagram size for receive operations |

Behavior notes:

- SNMPv1 has no GETBULK PDU: `get_bulk()` and `bulkwalk()` downgrade to GETNEXT loops
- `walk()` always uses GETNEXT; the `bulk` argument is accepted for interface
  compatibility but ignored

---

## `V3Manager` fields

Base install covers `noAuthNoPriv` and `authNoPriv`; add
`pip install "trishul-snmp[v3]"` for AES privacy/authPriv.

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target hostname or IP address |
| `user` | `UsmUser` | required | USM credentials (`UsmUser` dataclass) |
| `port` | `int` | `161` | Target UDP port |
| `timeout` | `float` | `2.0` | Per-request timeout in seconds |
| `retries` | `int` | `1` | Retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle for symbolic resolution and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum UDP datagram size for receive operations |
| `context_name` | `bytes` | `b""` | SNMPv3 context name |

`UsmUser` fields: `username` (str), `auth_protocol` (AuthProtocol), `auth_key` (bytes),
`auth_key_localized` (bool), `priv_protocol` (PrivProtocol), `priv_key` (bytes).

`UsmUser` validation:

- a non-`NONE` `auth_protocol` or `priv_protocol` with empty/missing key material
  raises `ProtocolError` at construction
- a localized auth key (`auth_key_localized=True`) must be exactly the protocol
  digest length: MD5 16, SHA-1 20, SHA-224 28, SHA-256 32, SHA-384 48,
  SHA-512 64 octets

`AuthProtocol`: `NONE`, `MD5`, `SHA1`, `SHA224`, `SHA256`, `SHA384`, `SHA512`
`PrivProtocol`: `NONE`, `DES`, `AES128`, `AES192`, `AES256`, `THREEDES_EDE` (DES raises `ProtocolError`)

---

## `V3Notifier` fields

Same as `V3Manager` except `port` defaults to `162` and
`local_engine: UsmLocalEngine | None = None` may be supplied for SNMPv3 traps.

Base install covers `noAuthNoPriv` and `authNoPriv`; add
`pip install "trishul-snmp[v3]"` for AES privacy/authPriv.

Behavior notes:

- `send_inform()` discovers peer engine state lazily on first use
- `send_trap()` requires `local_engine`
- trap-capable `V3Notifier.open()` does not depend on peer discovery

---

## `V2cNotifier` fields

`V2cNotifier` uses the same core connection and bundle knobs as `V2cManager`,
but defaults `port` to `162`.

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | required | Target notification receiver hostname or IP address |
| `community` | `str` | required | SNMPv2c community string |
| `port` | `int` | `162` | Target UDP port |
| `timeout` | `float` | `2.0` | Inform request timeout in seconds |
| `retries` | `int` | `1` | Inform retry count after the first attempt |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for symbolic translation and enrichment |
| `max_datagram_size` | `int` | `65535` | Maximum UDP datagram size for receive operations |

Validation notes:

- `timeout` must be greater than `0`
- `retries` cannot be negative
- symbolic notification or varbind targets require a loaded bundle

---

## `V1Notifier` fields

`V1Notifier` uses the same fields as `V2cNotifier` (`host`, `community`, `port`
defaulting to `162`, `timeout`, `retries`, `bundle`, `max_datagram_size`).

Behavior notes:

- `send_trap()` targets the SNMPv1 Trap-PDU fields — `enterprise` (required),
  `agent_addr`, `generic_trap`, `specific_trap`, `timestamp` — and returns the
  trap timestamp rather than a request id
- `send_inform()` always raises `ProtocolError`: SNMPv1 has no inform concept

---

## `V2cNotificationListener` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Listener bind hostname or IP address |
| `port` | `int` | `162` | Listener UDP port |
| `communities` | `Sequence[str] \| None` | `None` | Optional community allowlist (v2c traps/informs and SNMPv1 traps) |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for inbound enrichment |
| `on_error` | `Callable[[DropReason, SocketAddress, bytes], None] \| None` | `None` | Optional callback invoked with `(reason, source_address, data_prefix)` for each dropped datagram |
| `clock` | `Callable[[], float]` | `time.monotonic` | Time source used for drop-log throttling |

Behavior notes:

- `communities=None` accepts any community string
- empty strings in `communities` are ignored
- informs are acknowledged automatically
- the same listener also receives SNMPv1 Trap-PDUs, and the `communities`
  allowlist gates both versions

---

## `V3NotificationListener` fields

Base install covers `noAuthNoPriv` and `authNoPriv` listeners; add
`pip install "trishul-snmp[v3]"` for AES privacy/authPriv listeners.

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Listener bind hostname or IP address |
| `port` | `int` | `162` | Listener UDP port |
| `user` | `UsmUser` | required | USM credentials for one configured inbound user |
| `local_engine` | `UsmLocalEngine` | required | Local authoritative engine state used for discovery REPORTs and inform acknowledgements |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for inbound enrichment |
| `on_error` | `Callable[[DropReason, SocketAddress, bytes], None] \| None` | `None` | Optional callback invoked with `(reason, source_address, data_prefix)` for each dropped datagram |
| `clock` | `Callable[[], float]` | `time.monotonic` | Time source used for drop-log throttling |

Behavior notes:

- one listener instance handles one configured USM user
- v3 informs are acknowledged automatically
- discovery probes are answered automatically so `V3Notifier.send_inform()` works against the listener

---

## `V2cResponder` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Responder bind hostname or IP address |
| `port` | `int` | `161` | Responder UDP port |
| `communities` | `Sequence[str] \| None` | `None` | Optional SNMPv2c community allowlist |
| `source` | `ResponderSource \| None` | `None` | Optional custom read-only source |
| `objects` | iterable | empty | Initial object seed for the default in-memory source |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle for symbolic object registration in the default in-memory source |

Behavior notes:

- when `source` is omitted, `V2cResponder` creates an `InMemoryObjectSource`
- `objects` cannot be combined with a custom `source`
- `GET` misses return `noSuchObject`
- `GET_NEXT` and `GET_BULK` exhaustion returns `endOfMibView`
- `SET` requests are rejected as read-only

---

## Bundle loading

`load_bundle(path)` accepts the following inputs:

| Input | Example | Notes |
|---|---|---|
| Single module JSON file | `./IF-MIB.json` | Valid standalone input for narrow use cases |
| Directory of module JSON files | `./mibs-json` | Can use optional sidecars for inventory and lookup acceleration |

Optional directory sidecars:

| File | Required | Purpose |
|---|---|---|
| `manifest.json` | no | Deterministic module inventory |
| `oid_index.json` | no | Faster reverse OID lookup |

If a directory has no `manifest.json`, `tsnmp` scans `*.json` files and ignores
known sidecar names as module candidates.

---

## CLI mapping

The CLI is a direct wrapper over the same runtime configuration:

| CLI option | Runtime mapping |
|---|---|
| `--host` | Manager, notifier, or listener constructor `host=...` depending on the command |
| `--port` | Manager, notifier, or listener constructor `port=...` depending on the command |
| `--snmp-version` | Chooses the v1/v2c/v3 manager, notifier, listener, or decode path |
| `--community` | `V2cManager(community=...)`, `V2cNotifier(community=...)`, or v2c listener allowlist entries |
| `--username` | `UsmUser(username=...)` for SNMPv3 manager/notifier/listener/decode commands |
| `--auth-protocol` | `UsmUser(auth_protocol=...)` |
| `--auth-key` / `--auth-key-env` | `UsmUser(auth_key=...)` |
| `--priv-protocol` | `UsmUser(priv_protocol=...)` |
| `--priv-key` / `--priv-key-env` | `UsmUser(priv_key=...)` |
| `--context-name` | `V3Manager(context_name=...)` or `V3Notifier(context_name=...)` |
| `--local-engine-id` / `--local-engine-boots` / `--local-engine-time` | `V3Notifier(local_engine=UsmLocalEngine(...))` for SNMPv3 trap, or `V3NotificationListener(local_engine=UsmLocalEngine(...))` for SNMPv3 listen |
| `--timeout` | Manager or notifier `timeout=...` |
| `--retries` | Manager or notifier `retries=...` |
| `--bundle` | `load_bundle(path)` plus optional runtime bundle attachment |
| `--json` | Output rendering only; no runtime behavior change |
| `--numeric` | Output rendering only; no runtime behavior change |
| `--non-repeaters` | `get_bulk(..., non_repeaters=...)` |
| `--max-repetitions` | `get_bulk(...)`, `walk(...)`, or `bulkwalk(...)` |
| `--no-bulk` | `walk(..., bulk=False)` |
| `--uptime` | `send_trap(..., uptime=...)` or `send_inform(..., uptime=...)` |
| `--varbind` | Notification varbind parsing at the CLI edge before calling the notifier |
| `--count` | Listener receive loop exit condition only |

CLI defaults differ slightly from the Python API:

- CLI `--community` defaults to `public`
- Python code must always pass `community` explicitly
- CLI notification send defaults `--port` to `162`
- CLI listener defaults `--host` to `0.0.0.0` and `--count` to `0`

---

## Behavioral notes

- The runtime core stays numeric internally.
- Bundles affect only translation at input boundaries and enrichment at output boundaries.
- No environment-variable or config-file layer is part of the runtime.
- Raw MIB files are not accepted as runtime input.
- The responder is intentionally narrow and simulator-oriented, not a full agent framework.
