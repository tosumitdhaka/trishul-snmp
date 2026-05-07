# trishul-snmp — Architecture

> **Last updated:** 2026-05-07

---

## 1. Overview

`trishul-snmp` is a package-first SNMP manager runtime. The core runtime handles
wire codec, UDP transport, request dispatch, and manager operations with no MIB
compiler dependency. Optional compiled-JSON artifacts add symbolic translation
and richer display.

```text
┌────────────────────────────────────────────────────────────────────┐
│                       Python API / CLI                             │
│                 V2cManager + load_bundle()                         │
├────────────────────────────────────────────────────────────────────┤
│ manager/      target normalization, request shaping, walk logic    │
│ transport/    UDP client, request/response matching, retries       │
│ wire/         BER / ASN.1 / SNMPv2c message + PDU codec            │
│ mib/          optional bundle loading, registry, rendering         │
└────────────────────────────────────────────────────────────────────┘
```

The CLI is intentionally thin. It does not define a second architecture.

---

## 2. Package structure

```text
trishul_snmp/
├── __init__.py          ← public package surface + version
├── __main__.py          ← `python -m trishul_snmp`
├── errors.py            ← exception hierarchy
├── types.py             ← public response and SNMP value models
│
├── wire/
│   ├── ber.py           ← BER primitives
│   ├── asn1.py          ← ASN.1 value encoding helpers
│   ├── message.py       ← SNMP message encode/decode
│   └── pdu.py           ← PDU models and PDU encode/decode
│
├── transport/
│   ├── udp.py           ← connected UDP client
│   └── dispatcher.py    ← request ids, timeout/retry, response matching
│
├── manager/
│   ├── client.py        ← V2cManager public runtime API
│   ├── operations.py    ← target normalization and response shaping
│   └── walk.py          ← subtree walk stop rules and iteration
│
├── mib/
│   ├── loader.py        ← bundle file/directory loading
│   ├── bundle.py        ← public MibBundle abstraction
│   ├── registry.py      ← symbol and OID lookup registry
│   ├── models.py        ← normalized compiled-JSON records
│   └── render.py        ← varbind enrichment and display rendering
│
└── cli/
    ├── main.py          ← argument parser and command handlers
    ├── common.py        ← shared options and bundle loading
    └── output.py        ← text and JSON rendering
```

---

## 3. Layer responsibilities

### 3.1 `wire/`

Pure protocol codec. Responsibilities:

- BER primitives
- ASN.1 value encoding/decoding
- SNMP message and PDU encode/decode

Non-responsibilities:

- no UDP socket handling
- no retry/timeout logic
- no bundle translation or enrichment

### 3.2 `transport/`

Owns request/response transport behavior:

- UDP socket open/close/send/receive
- timeout and retry handling
- community-string filtering
- request-id matching

### 3.3 `manager/`

Owns the public runtime behavior:

- normalize numeric or symbolic targets to numeric OIDs
- construct request varbinds
- issue GET / GETNEXT / GETBULK requests
- implement subtree walk logic and stop rules
- shape public `Response` and `VarBind` models

### 3.4 `mib/`

Owns optional symbolic services:

- load a single compiled module JSON file or bundle directory
- validate module JSON and optional sidecars
- resolve `MODULE::symbol` input
- reverse-lookup numeric OIDs for enrichment
- render display names and values

### 3.5 `cli/`

Owns command-line UX only:

- parse arguments
- load the optional bundle
- call the same Python API as library users
- render text or JSON output

---

## 4. End-to-end call flows

### 4.1 Numeric GET with no bundle

1. Caller invokes `await manager.get("1.3.6.1.2.1.1.3.0")`.
2. `normalize_targets()` parses the numeric OID.
3. `build_request_varbinds()` creates NULL placeholder varbinds.
4. `RequestDispatcher.send_pdu()` assigns a request id, encodes the SNMP message, and sends it over UDP.
5. `UdpClient.receive()` waits for a matching response with timeout/retry handling.
6. `decode_message()` decodes the response and `response_from_pdu()` builds the public `Response`.
7. With no bundle loaded, enrichment is effectively pass-through.

### 4.2 Symbolic GET with a bundle

1. Caller loads a bundle once via `load_bundle(path)`.
2. `normalize_targets()` resolves `MODULE::symbol` input through `MibBundle.resolve()`.
3. Network I/O remains numeric only.
4. After response decode, `enrich_varbinds()` uses bundle lookup and render helpers to populate `display_name` and `display_value`.

### 4.3 Walk / bulkwalk

1. `walk()` resolves the root once at the API boundary.
2. `walk_subtree()` iterates via GETNEXT or GETBULK.
3. Walk stops when the response leaves the subtree, repeats or decreases OIDs, or returns `endOfMibView`.
4. The final result is a tuple of `VarBind` objects, optionally enriched by the bundle.

### 4.4 Offline translation

1. `load_bundle()` builds a `MibRegistry` from compiled JSON artifacts.
2. `bundle.translate()`, `bundle.resolve()`, and `bundle.lookup()` operate with no network I/O.
3. A single module JSON file is sufficient for narrow translation use cases.

---

## 5. Bundle boundary

The runtime/compiler split is a deliberate architectural boundary:

- `tsnmp` does not import `trishul-smi` at runtime
- a single module JSON file must be enough for core enrichment use cases
- `manifest.json` and `oid_index.json` are optional accelerators, not correctness requirements
- module JSON is the source of truth
- public generic third-party schema normalization is not part of `v0.1`

This keeps deployment simple and lets callers supply only the compiled JSON they
actually need.

---

## 6. Scope guardrails

`v0.1` is intentionally narrow:

- manager-only
- SNMPv2c-only
- read-only operations only
- async-first package API first, CLI second
- not attempting a full `pysnmp` replacement in the first release

Raw MIB ingestion, compiler workflows, `set`, SNMPv3, traps/listener behavior,
and agent/responder support remain outside the current architecture.
