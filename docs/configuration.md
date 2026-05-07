# Configuration Reference

All runtime configuration is explicit on `V2cManager` and `load_bundle()`. The
CLI maps directly to these knobs; there is no hidden global config layer in `v0.1`.

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
| `--host` | `V2cManager(host=...)` |
| `--port` | `V2cManager(port=...)` |
| `--community` | `V2cManager(community=...)` |
| `--timeout` | `V2cManager(timeout=...)` |
| `--retries` | `V2cManager(retries=...)` |
| `--bundle` | `load_bundle(path)` and `V2cManager(bundle=...)` |
| `--json` | Output rendering only; no runtime behavior change |
| `--numeric` | Output rendering only; no runtime behavior change |
| `--non-repeaters` | `get_bulk(..., non_repeaters=...)` |
| `--max-repetitions` | `get_bulk(...)`, `walk(...)`, or `bulkwalk(...)` |
| `--no-bulk` | `walk(..., bulk=False)` |

CLI defaults differ slightly from the Python API:

- CLI `--community` defaults to `public`
- Python code must always pass `community` explicitly

---

## Behavioral notes

- The runtime core stays numeric internally.
- Bundles affect only translation at input boundaries and enrichment at output boundaries.
- No environment-variable or config-file layer is part of `v0.1`.
- Raw MIB files are not accepted as runtime input in `v0.1`.
