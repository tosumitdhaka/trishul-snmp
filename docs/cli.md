# CLI Reference

The CLI is a thin wrapper over the Python API. It is useful for smoke testing,
offline translation, notification debugging, and simple operator workflows, but
it is not the primary product surface.

Current CLI coverage includes SNMPv1/v2c plus SNMPv3 `get`, `getnext`, `getbulk`,
`walk`, `bulkwalk`, `trap`, `inform`, `listen`, and `decode-notification`.

---

## Common manager options

All live commands (`get`, `getnext`, `getbulk`, `walk`, `bulkwalk`) share these
options:

| Option | Default | Description |
|---|---|---|
| `--host` | required | Target agent hostname or IP address |
| `--port` | `161` | Target UDP port |
| `--snmp-version {1,2c,3}` | `2c` | Explicit live protocol version selection |
| `--community` | `public` when omitted | SNMPv1/v2c community string; valid with `--snmp-version 1` and `2c` |
| `--username` | — | SNMPv3 username; required with `--snmp-version 3` |
| `--auth-protocol {none,md5,sha1,sha224,sha256,sha384,sha512}` | `none` | SNMPv3 auth protocol (RFC 7860 SHA-2 family included) |
| `--auth-key` / `--auth-key-env` | — | Exactly one required when auth is enabled |
| `--priv-protocol {none,aes128,aes192,aes256,3des-ede,des}` | `none` | SNMPv3 privacy protocol; AES-192/256 use Reeder key derivation, `des` fails fast with an accurate error (no single-DES primitive in the `cryptography` backend) |
| `--priv-key` / `--priv-key-env` | — | Exactly one required when privacy is enabled |
| `--context-name` | empty | SNMPv3 context name (UTF-8 text) |
| `--timeout` | `2.0` | Request timeout in seconds |
| `--retries` | `1` | Retry count per request |
| `--bundle` | — | Compiled module JSON file or bundle directory |
| `--numeric` | off | Render numeric OIDs in text output even when a bundle is loaded |
| `--json` | off | Emit machine-readable JSON output |

**Exit codes:** `0` success, `1` runtime/translation/protocol failure or non-zero
SNMP error status, `2` invalid CLI usage from `argparse`.

---

## Common notification send options

The outbound notification commands (`trap`, `inform`) share these options:

| Option | Default | Description |
|---|---|---|
| `--host` | required | Target notification receiver hostname or IP address |
| `--port` | `162` | Target UDP port |
| `--snmp-version {1,2c,3}` | `2c` | Explicit live protocol version selection |
| `--community` | `public` when omitted | SNMPv1/v2c community string; valid with `--snmp-version 1` and `2c` |
| `--username` | — | SNMPv3 username; required with `--snmp-version 3` |
| `--auth-protocol {none,md5,sha1,sha224,sha256,sha384,sha512}` | `none` | SNMPv3 auth protocol (RFC 7860 SHA-2 family included) |
| `--auth-key` / `--auth-key-env` | — | Exactly one required when auth is enabled |
| `--priv-protocol {none,aes128,aes192,aes256,3des-ede,des}` | `none` | SNMPv3 privacy protocol; AES-192/256 use Reeder key derivation, `des` fails fast with an accurate error (no single-DES primitive in the `cryptography` backend) |
| `--priv-key` / `--priv-key-env` | — | Exactly one required when privacy is enabled |
| `--context-name` | empty | SNMPv3 context name (UTF-8 text) |
| `--timeout` | `2.0` | Request timeout in seconds |
| `--retries` | `1` | Retry count per request |
| `--bundle` | — | Compiled module JSON file or bundle directory |
| `--uptime` | `0` | `sysUpTime.0` value in centiseconds (v2c/v3 traps and informs) |
| `--enterprise` | — | SNMPv1 trap: enterprise OID; required for `trap --snmp-version 1` |
| `--agent-addr` | `0.0.0.0` | SNMPv1 trap: originating agent address |
| `--generic-trap` | `6` | SNMPv1 trap: generic trap number (0-6) |
| `--specific-trap` | `0` | SNMPv1 trap: specific trap code (with generic trap 6) |
| `--timestamp` | `0` | SNMPv1 trap: time-stamp in centiseconds |
| `--varbind` | repeatable | Notification payload varbind in `OID=TYPE:VALUE` form |
| `--json` | off | Emit machine-readable JSON output |

Supported `TYPE` values for `--varbind`:

- `int`
- `string`
- `hex`
- `oid`
- `ip`
- `counter32`
- `gauge32`
- `timeticks`
- `opaque`
- `counter64`
- `null`

`oid` values may be numeric or symbolic. Symbolic OIDs require `--bundle`.

Trap-only SNMPv3 options:

| Option | Description |
|---|---|
| `--local-engine-id` | Sender authoritative engine-id as hex bytes |
| `--local-engine-boots` | Sender authoritative `engineBoots` |
| `--local-engine-time` | Sender authoritative `engineTime` |

Validation rules:

- `--community` is invalid with `--snmp-version 3` (valid with `1` and `2c`)
- `--username` is required with `--snmp-version 3`
- `--snmp-version 1` accepts `--community` only; mixing v1 with v3 flags fails early
- `trap --snmp-version 1` requires `--enterprise` and rejects a non-zero `--uptime`
- `inform --snmp-version 1` fails fast: SNMPv1 has no inform operations — use `trap`
- auth requires exactly one of `--auth-key` or `--auth-key-env`
- privacy requires auth plus exactly one of `--priv-key` or `--priv-key-env`
- `trap --snmp-version 3` requires all three `--local-engine-*` options
- `inform --snmp-version 3` rejects `--local-engine-*` as unused
- privacy/authPriv CLI flows require `pip install "trishul-snmp[v3]"`; `noAuthNoPriv`
  and `authNoPriv` v3 flows do not

---

## `tsnmp translate`

```
tsnmp translate --bundle PATH TARGET
```

Offline translation only.

| Argument | Description |
|---|---|
| `TARGET` | Numeric OID or `MODULE::symbol[.suffix]` target |

| Option | Description |
|---|---|
| `--bundle` | Compiled module JSON file or bundle directory |

Examples:

```bash
tsnmp translate --bundle ./IF-MIB.json IF-MIB::ifDescr.1
tsnmp translate --bundle ./mibs-json 1.3.6.1.2.1.2.2.1.2.1
```

---

## `tsnmp get`

```
tsnmp get [OPTIONS] TARGET [TARGET ...]
```

Examples:

```bash
tsnmp get --host 10.0.0.10 1.3.6.1.2.1.1.3.0
tsnmp get --host 10.0.0.10 --bundle ./IF-MIB.json IF-MIB::ifDescr.1
tsnmp get --host 10.0.0.10 --json 1.3.6.1.2.1.1.3.0
```

---

## `tsnmp getnext`

```
tsnmp getnext [OPTIONS] TARGET [TARGET ...]
```

Examples:

```bash
tsnmp getnext --host 10.0.0.10 1.3.6.1.2.1.2.2
tsnmp getnext --host 10.0.0.10 --bundle ./IF-MIB.json IF-MIB::ifTable
```

---

## `tsnmp getbulk`

```
tsnmp getbulk [OPTIONS] TARGET [TARGET ...]
```

Additional options:

| Option | Default | Description |
|---|---|---|
| `--non-repeaters` | `0` | Number of non-repeaters |
| `--max-repetitions` | `10` | Maximum repetitions per repeating target |

Examples:

```bash
tsnmp getbulk --host 10.0.0.10 --non-repeaters 0 --max-repetitions 10 1.3.6.1.2.1.2.2
tsnmp getbulk --host 10.0.0.10 --bundle ./mibs-json IF-MIB::ifTable
```

---

## `tsnmp walk`

```
tsnmp walk [OPTIONS] ROOT
```

Uses GETBULK by default.

Additional options:

| Option | Default | Description |
|---|---|---|
| `--max-repetitions` | `10` | Maximum repetitions per bulk step |
| `--no-bulk` | off | Use GETNEXT rather than GETBULK |

Examples:

```bash
tsnmp walk --host 10.0.0.10 --bundle ./mibs-json IF-MIB::ifTable
tsnmp walk --host 10.0.0.10 --no-bulk 1.3.6.1.2.1.2.2
```

---

## `tsnmp bulkwalk`

```
tsnmp bulkwalk [OPTIONS] ROOT
```

Additional options:

| Option | Default | Description |
|---|---|---|
| `--max-repetitions` | `10` | Maximum repetitions per bulk request |

Examples:

```bash
tsnmp bulkwalk --host 10.0.0.10 --bundle ./mibs-json IF-MIB::ifTable
```

---

## `tsnmp trap`

```
tsnmp trap [OPTIONS] [NOTIFICATION]
```

Sends an SNMP trap and prints the assigned request id. `NOTIFICATION` is
optional: with `--snmp-version 1` no positional is used — the trap is targeted
via `--enterprise` — and the printed value is the trap timestamp rather than a
request id (v1 Trap-PDUs carry no request id).

Examples:

```bash
tsnmp trap --host 10.0.0.20 1.3.6.1.6.3.1.1.5.3
tsnmp trap --host 10.0.0.20 --bundle ./mibs-json IF-MIB::linkDown \
  --uptime 123 \
  --varbind IF-MIB::ifIndex.7=int:7
tsnmp trap --host 10.0.0.20 --snmp-version 3 --username notify \
  --local-engine-id 8000010203 --local-engine-boots 7 --local-engine-time 99 \
  1.3.6.1.6.3.1.1.5.3
```

---

## `tsnmp inform`

```
tsnmp inform [OPTIONS] NOTIFICATION
```

Sends an SNMP inform and prints the response varbinds.

Additional option:

| Option | Default | Description |
|---|---|---|
| `--numeric` | off | Render numeric OIDs in text output even when a bundle is loaded |

Examples:

```bash
tsnmp inform --host 10.0.0.20 1.3.6.1.6.3.1.1.5.3
tsnmp inform --host 10.0.0.20 --bundle ./mibs-json IF-MIB::linkDown \
  --varbind IF-MIB::ifIndex.7=int:7
tsnmp inform --host 10.0.0.20 --snmp-version 3 --username notify \
  --auth-protocol sha256 --auth-key-env TSNMP_AUTH \
  1.3.6.1.6.3.1.1.5.3
```

---

## `tsnmp listen`

```
tsnmp listen [OPTIONS]
```

Listens for inbound SNMP notifications. Use `--snmp-version 2c` with optional
repeated `--community` allowlists — the community listener also receives SNMPv1
traps from the same allowlist (`--snmp-version 1` is accepted as an alias for
the community listener path) — or `--snmp-version 3` with explicit
username/auth/priv inputs plus required local authoritative engine state.

Options:

| Option | Default | Description |
|---|---|---|
| `--host` | `0.0.0.0` | Listener bind hostname or IP address |
| `--port` | `162` | Listener UDP port |
| `--snmp-version {1,2c,3}` | `2c` | Inbound notification protocol version |
| `--community` | repeatable | Optional community allowlist entry (v1 and v2c traps share it); invalid with `--snmp-version 3` |
| `--username` | — | SNMPv3 username; required with `--snmp-version 3` |
| `--auth-protocol {none,md5,sha1,sha224,sha256,sha384,sha512}` | `none` | SNMPv3 auth protocol (RFC 7860 SHA-2 family included) |
| `--auth-key` / `--auth-key-env` | — | Exactly one required when auth is enabled |
| `--priv-protocol {none,aes128,aes192,aes256,3des-ede,des}` | `none` | SNMPv3 privacy protocol; AES-192/256 use Reeder key derivation, `des` fails fast with an accurate error (no single-DES primitive in the `cryptography` backend) |
| `--priv-key` / `--priv-key-env` | — | Exactly one required when privacy is enabled |
| `--local-engine-id` / `--local-engine-boots` / `--local-engine-time` | — | Required for `listen --snmp-version 3` |
| `--bundle` | — | Compiled module JSON file or bundle directory |
| `--count` | `0` | Number of notifications to receive before exit; `0` means run until interrupted |
| `--numeric` | off | Render numeric OIDs in text output even when a bundle is loaded |
| `--json` | off | Emit one JSON object per received notification |

Examples:

```bash
tsnmp listen --host 127.0.0.1 --port 9162 --count 1
tsnmp listen --bundle ./mibs-json --community public --community traps --json
tsnmp listen --snmp-version 3 --username notify \
  --auth-protocol sha256 --auth-key-env TSNMP_AUTH \
  --local-engine-id 8000010203 --local-engine-boots 7 --local-engine-time 99
```

---

## `tsnmp decode-notification`

```
tsnmp decode-notification [OPTIONS]
```

Offline decode for BER-encoded SNMP notifications. Use `--snmp-version 3` with
explicit user/auth/priv inputs when decoding captured USM notifications.

Options:

| Option | Default | Description |
|---|---|---|
| `--snmp-version {1,2c,3}` | `2c` | Protocol version of the captured notification |
| `--username` | — | SNMPv3 username; required with `--snmp-version 3` |
| `--auth-protocol {none,md5,sha1,sha224,sha256,sha384,sha512}` | `none` | SNMPv3 auth protocol (RFC 7860 SHA-2 family included) |
| `--auth-key` / `--auth-key-env` | — | Exactly one required when auth is enabled |
| `--priv-protocol {none,aes128,aes192,aes256,3des-ede,des}` | `none` | SNMPv3 privacy protocol; AES-192/256 use Reeder key derivation, `des` fails fast with an accurate error (no single-DES primitive in the `cryptography` backend) |
| `--priv-key` / `--priv-key-env` | — | Exactly one required when privacy is enabled |
| `--hex` | mutually exclusive | Hex-encoded SNMP message bytes |
| `--file` | mutually exclusive | Path to raw BER-encoded SNMP message bytes |
| `--bundle` | — | Compiled module JSON file or bundle directory |
| `--numeric` | off | Render numeric OIDs in text output even when a bundle is loaded |
| `--json` | off | Emit machine-readable JSON output |

Examples:

```bash
tsnmp decode-notification --hex 302602010104067075626c6963...
tsnmp decode-notification --file ./trap.ber --bundle ./mibs-json
tsnmp decode-notification --snmp-version 3 --username notify \
  --auth-protocol sha256 --auth-key-env TSNMP_AUTH --file ./inform-v3.ber
```

---

## `tsnmp version`

```
tsnmp version
```

Print the installed package version and exit.

---

## Output modes

Default output is line-oriented text:

```text
IF-MIB::ifDescr.1 = eth0
```

Machine-readable mode:

```bash
tsnmp get --host 10.0.0.10 --json 1.3.6.1.2.1.1.3.0
```

Numeric rendering even when a bundle is loaded:

```bash
tsnmp get --host 10.0.0.10 --bundle ./mibs-json --numeric IF-MIB::ifDescr.1
```

Listener JSON mode emits one JSON object per line so it can stream indefinitely.

---

## Scope limits

Deliberately still not included:

- `set`
- compile workflows
- raw MIB file or directory ingestion

If you need rich runtime usage, prefer the Python API.
