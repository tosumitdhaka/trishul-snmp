# Configuration Reference

All runtime configuration is explicit on `V2cManager`, `V2cNotifier`,
`V2cNotificationListener`, `V2cResponder`, and `load_bundle()`. The CLI maps
directly to these knobs; there is no hidden global config layer.

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

## `V2cNotificationListener` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `0.0.0.0` | Listener bind hostname or IP address |
| `port` | `int` | `162` | Listener UDP port |
| `communities` | `Sequence[str] \| None` | `None` | Optional SNMPv2c community allowlist |
| `bundle` | `MibBundle \| None` | `None` | Optional bundle used for inbound enrichment |

Behavior notes:

- `communities=None` accepts any SNMPv2c community
- empty strings in `communities` are ignored
- informs are acknowledged automatically

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
| `--host` | `V2cManager(...)`, `V2cNotifier(...)`, or `V2cNotificationListener(...)` depending on the command |
| `--port` | `V2cManager(...)`, `V2cNotifier(...)`, or `V2cNotificationListener(...)` depending on the command |
| `--community` | `V2cManager(community=...)`, `V2cNotifier(community=...)`, or listener allowlist entries |
| `--timeout` | `V2cManager(timeout=...)` or `V2cNotifier(timeout=...)` |
| `--retries` | `V2cManager(retries=...)` or `V2cNotifier(retries=...)` |
| `--bundle` | `load_bundle(path)` plus optional runtime bundle attachment |
| `--json` | Output rendering only; no runtime behavior change |
| `--numeric` | Output rendering only; no runtime behavior change |
| `--non-repeaters` | `get_bulk(..., non_repeaters=...)` |
| `--max-repetitions` | `get_bulk(...)`, `walk(...)`, or `bulkwalk(...)` |
| `--no-bulk` | `walk(..., bulk=False)` |
| `--uptime` | `send_trap(..., uptime=...)` or `send_inform(..., uptime=...)` |
| `--varbind` | Notification varbind parsing at the CLI edge before calling `V2cNotifier` |
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
