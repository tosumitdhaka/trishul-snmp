# trishul-snmp — Architecture

> **Last updated:** 2026-05-29

---

## 1. Overview

`trishul-snmp` is a package-first SNMP runtime. The core runtime handles wire
codec, UDP transport, request dispatch, manager operations, outbound
notification send, inbound notification receive, and a narrow read-only
responder with no MIB compiler dependency. Optional compiled-JSON artifacts add
symbolic translation and richer display.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                             Python API / CLI                                 │
│  V2cManager / V3Manager  ·  V2cNotifier / V3Notifier                        │
│  V2cNotificationListener  ·  V2cResponder  ·  decode_notification()          │
├──────────────────────────────────────────────────────────────────────────────┤
│ manager/      target normalization, request shaping, walk logic              │
│ notify/       send, listen, and offline notification decode                  │
│ responder/    read-only request handling and simulator sources               │
│ security/     SecurityModel protocol · CommunityModel · UsmModel (v3 USM)   │
│ session.py    shared UdpClient + Dispatcher + Lock + MibBundle               │
│ transport/    UDP client/server, request matching, retries                   │
│ wire/         BER / ASN.1 / SNMPv2c + SNMPv3 message + PDU codec            │
│ mib/          optional bundle loading, registry, rendering                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The CLI is intentionally thin. It does not define a second architecture.

---

## 2. Package structure

```text
trishul_snmp/
├── __init__.py          ← public package surface + version
├── __main__.py          ← `python -m trishul_snmp`
├── errors.py            ← exception hierarchy (incl. AuthenticationError)
├── types.py             ← public response and SNMP value models
├── session.py           ← shared UdpClient + Dispatcher + Lock + MibBundle
│
├── security/
│   ├── model.py         ← SecurityModel protocol (structural)
│   ├── community.py     ← CommunityModel for SNMPv2c
│   └── usm.py           ← UsmModel, UsmUser, AuthProtocol, PrivProtocol (v3 USM)
│
├── wire/
│   ├── ber.py           ← BER primitives
│   ├── asn1.py          ← ASN.1 value encoding helpers
│   ├── message.py       ← SNMPv2c message encode/decode
│   ├── v3message.py     ← SNMPv3 outer message + ScopedPDU + USM params codec
│   └── pdu.py           ← PDU models and PDU encode/decode
│
├── transport/
│   ├── udp.py           ← connected UDP client
│   └── dispatcher.py    ← request ids, timeout/retry, response matching
│
├── manager/
│   ├── client.py        ← SnmpManager base · V2cManager · V3Manager
│   ├── operations.py    ← target normalization and response shaping
│   └── walk.py          ← subtree walk stop rules and iteration
│
├── notify/
│   ├── client.py        ← SnmpNotifier base · V2cNotifier · V3Notifier
│   ├── listener.py      ← V2cNotificationListener public receive API
│   ├── events.py        ← notification event model + live/offline decode
│   └── __init__.py      ← notification package export
│
├── responder/
│   ├── server.py        ← V2cResponder public API
│   ├── sources.py       ← in-memory and callback-backed data sources
│   ├── rules.py         ← simulation rules for dynamic OID values
│   └── __init__.py      ← responder package export
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
    ├── common.py        ← shared options, bundle loading, value parsing
    └── output.py        ← manager and notification text/JSON rendering
```

---

## 3. Layer responsibilities

### 3.1 `wire/`

Pure protocol codec. Responsibilities:

- BER primitives
- ASN.1 value encoding/decoding
- SNMPv2c and SNMPv3 message and PDU encode/decode
- SNMPv3 outer message framing, ScopedPDU, and USM security parameters codec (`v3message.py`)

Non-responsibilities:

- no UDP socket handling
- no retry/timeout logic
- no bundle translation or enrichment
- no cryptography (`security/` owns auth/priv)

### 3.1a `security/`

Security model abstraction. Responsibilities:

- `SecurityModel` structural protocol: `wrap_pdu(pdu) -> bytes`, `unwrap_message(data) -> Pdu | None`
- `CommunityModel`: SNMPv2c community string wrapping/matching
- `UsmModel`: SNMPv3 USM — RFC 3414 key derivation, HMAC auth, AES-128-CFB privacy, engine discovery
- `UsmUser`: immutable credential dataclass (username, auth protocol/key, priv protocol/key)

`UsmModel` imports `cryptography` lazily inside auth/priv methods only; the class is always
importable without the `[v3]` extra.

### 3.2 `transport/`

Owns request/response transport behavior:

- connected UDP client behavior for manager/notifier flows
- bound UDP server behavior for listener/responder flows
- timeout and retry handling for request/response paths
- request-id matching in dispatcher-managed flows

### 3.3 `manager/`

Owns the public runtime behavior:

- normalize numeric or symbolic targets to numeric OIDs
- construct request varbinds
- issue GET / GETNEXT / GETBULK requests
- implement subtree walk logic and stop rules
- shape public `Response` and `VarBind` models

### 3.4 `notify/`

Owns notification-specific runtime behavior:

- normalize numeric or symbolic notification OIDs
- normalize explicit varbind OIDs for outbound notifications
- auto-populate `sysUpTime.0` and `snmpTrapOID.0`
- send traps as fire-and-forget
- send informs and wait for matching responses
- receive trap and inform PDUs as structured events
- decode BER-encoded trap/inform messages offline into the same public event model
- auto-acknowledge informs on the listener path
- apply optional community allowlists on the listener path
- map notification member metadata to received varbinds when a bundle is present

### 3.5 `responder/`

Owns the narrow read-only simulator behavior:

- receive `GET`, `GET_NEXT`, and `GET_BULK` over UDP
- resolve exact and next lexicographic objects from a pluggable source
- synthesize `noSuchObject` and `endOfMibView` where appropriate
- keep source interfaces small enough for fixtures and callback-backed simulation
- simulation rules (`CounterRule`, `RandomNumericRule`, `UptimeRule`, `TimestampRule`) generate dynamic values on each lookup without application-side callbacks
- `InMemoryObjectSource.from_bundle()` populates a source from compiled JSON metadata with sensible defaults

### 3.6 `mib/`

Owns optional symbolic services:

- load a single compiled module JSON file or bundle directory
- validate module JSON and optional sidecars
- resolve `MODULE::symbol` input
- reverse-lookup numeric OIDs for enrichment
- render display names and values
- `MibBundle.iter_objects()`, `iter_notifications()`, and `search()` provide in-memory iteration and substring search over loaded nodes

### 3.7 `cli/`

Owns command-line UX only:

- parse arguments
- load the optional bundle
- call the same Python API as library users
- render text or JSON output
- current live-command protocol coverage in `v0.4.0` is SNMPv2c only; SNMPv3 CLI support is follow-on work

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

This flow is shown with `V2cManager`. `V3Manager` follows the same request path after
`SnmpSession.open()` performs engine discovery and `UsmModel` wraps/unwraps the PDU.

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

### 4.5 Outbound trap/inform send

1. Caller invokes `await V2cNotifier.send_trap(...)`, `await V2cNotifier.send_inform(...)`, or `await V3Notifier.send_inform(...)`.
2. Numeric or symbolic notification OIDs are normalized at the API edge.
3. `sysUpTime.0` and `snmpTrapOID.0` are inserted first unless explicitly provided.
4. The notification PDU is encoded and sent over UDP.
5. SNMPv2c trap send stops after send; SNMPv2c and SNMPv3 inform send wait for a matching `RESPONSE` PDU.
6. `V3Notifier.send_trap()` intentionally raises `ProtocolError` in `v0.4.0` because SNMPv3 traps require the sender's local authoritative engine state, which is not tracked yet.

### 4.6 Inbound trap/inform receive

1. Caller opens `V2cNotificationListener(...)`.
2. `UdpServer` binds the requested host and port.
3. The listener receives inbound datagrams and decodes SNMP messages.
4. Non-notification PDUs and filtered communities are ignored.
5. Informs are acknowledged automatically with a matching `RESPONSE` PDU.
6. The listener returns a `NotificationEvent` carrying source address, community, PDU kind, decoded varbinds, notification metadata, and optional declared-member bindings.

### 4.7 Offline trap/inform decode

1. Caller invokes `decode_notification(raw_bytes, bundle=...)`.
2. `decode_message()` decodes the SNMPv2c envelope and notification PDU.
3. `notification_event_from_message()` builds the public `NotificationEvent`.
4. If a bundle is loaded, `snmpTrapOID.0` is reverse-looked-up into `notification_name` and declared `member_bindings`.
5. No UDP transport or dispatcher code is involved.

### 4.8 Read-only responder flow

1. Caller configures `V2cResponder` with an in-memory or callback-backed source.
2. `UdpServer` binds the requested host and port.
3. The responder receives inbound SNMPv2c messages and filters by community.
4. `GET`, `GET_NEXT`, and `GET_BULK` are answered from the configured source using lexicographic OID ordering.
5. Missing exact objects become `noSuchObject`; next/bulk exhaustion becomes `endOfMibView`.
6. The responder sends a matching `RESPONSE` PDU back to the request source address.

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

The current main-branch scope is still intentionally narrower than a full SNMP
stack:

- SNMPv2c and SNMPv3 USM (noAuthNoPriv, authNoPriv, authPriv AES-128)
- async-first package API first, CLI second
- manager operations plus notification send/receive and narrow read-only response
- not attempting a full `pysnmp` replacement

Raw MIB ingestion, compiler workflows, writable `set`, SNMPv1, and full
agent framework support remain outside the current implemented architecture.
