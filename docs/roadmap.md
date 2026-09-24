# Roadmap

Tracks shipped scope, near-term work, and deferred work.
Status: `planned` | `in progress` | `done` | `deferred`

---

## v0.3.0 — shipped 2026-05-15

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Simulation rule engine | done | `CounterRule`, `RandomNumericRule`, `UptimeRule`, `TimestampRule` plus `SimulationRule` protocol. `InMemoryObjectSource` now stores and evaluates rules alongside static values. |
| 2 | `InMemoryObjectSource.from_bundle()` | done | Auto-populates a source from a `MibBundle` with syntax-appropriate defaults, instance suffix generation, and deprecated-object filtering. |
| 3 | `MibBundle` iteration helpers | done | `iter_objects()`, `iter_notifications()`, and `search()` allow in-memory bundle queries without a separate database layer. |
| 4 | `NotificationEvent.to_dict()` | done | JSON-safe dict serialization for WebSocket broadcast and storage use cases. |

---

## v0.2.0 — shipped 2026-05-08

Tracked by GitHub milestone `0.2.0` and umbrella issue `#7`.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Notification metadata retention and shared plumbing | done | `#2`. `description` and structured `members` are retained, and lower-level request prep helpers are shared across manager and notify paths. |
| 2 | Outbound SNMPv2c trap/inform send APIs | done | `#4`. `V2cNotifier` sends numeric or symbolic notifications and auto-populates standard SNMPv2 notification varbinds. |
| 3 | Inbound SNMPv2c notification listener/server transport | done | `#3`. `V2cNotificationListener` supports bind controls, community allowlists, trap/inform decode, and automatic inform acknowledgement. |
| 4 | Notification event/render/decode/CLI tooling | done | `#5`. `NotificationEvent` now carries notification metadata and member bindings; CLI trap/inform/listen/decode commands are wired. |
| 5 | Narrow read-only responder / simulator layer | done | `#6`. `V2cResponder` plus in-memory and callback-backed sources now cover `GET`, `GET_NEXT`, and `GET_BULK` for tests, demos, and simulator-style use. |

See [v0.2.0 Implementation Prep](v0.2.0-implementation-prep.md) for the
coding sequence, package evolution, and pre-implementation lock decisions.

---

## v0.1.1 — shipped 2026-05-07

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Canonical display rendering for scalar instance aliases | done | Numeric translation and enrichment prefer `MODULE::symbol.0` for scalar `.0` display without changing exact lookup semantics. |
| 2 | Live benchmark harness | done | `scripts/benchmark_snmpd.py` compares raw vs enriched API and CLI paths against a live SNMP agent. |
| 3 | Alias-policy regression fixtures | done | Synthetic bundle fixtures isolate `tsmi` sidecar contract validation from `tsnmp` display-policy behavior. |

---

## v0.1.0 — shipped 2026-05-07

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Async SNMPv2c manager runtime | done | `V2cManager` is the primary public entry point. |
| 2 | Read-only manager operations | done | `get`, `get_next`, `get_bulk`, `walk`, `bulkwalk`. |
| 3 | In-tree wire codec | done | BER / ASN.1 / SNMPv2c message and PDU encode/decode live under `wire/`. |
| 4 | UDP transport and request dispatcher | done | Timeout, retry, community matching, and request-id matching. |
| 5 | Optional compiled-JSON bundle loading | done | Single module JSON or bundle directory; sidecars optional. |
| 6 | Offline translation and live enrichment | done | Symbolic input resolution and display rendering stay optional. |
| 7 | Thin CLI | done | Package wrapper for smoke tests and simple operator workflows. |
| 8 | CI, release automation, and docs baseline | done | Lint, typecheck, tests, coverage, release workflow, and package docs. |

---

## v0.4.0 — shipped 2026-05-28

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Session architecture refactor | done | Extracted shared `UdpClient + Dispatcher + Lock + MibBundle` into `session.py`. Added `security/model.py` (`SecurityModel` protocol) + `security/community.py` (`CommunityModel` for v2c). `dispatcher.py` takes `security=` instead of `community=`. `V2cManager` / `V2cNotifier` are subclasses of new `SnmpManager` / `SnmpNotifier` bases; `V2cNotificationListener` is an alias — no public API breakage. |
| 2 | SNMPv3 USM client stack | done | Shipped noAuthNoPriv + authNoPriv (HMAC-MD5/SHA-1/SHA-256) + authPriv (AES-128-CFB) for manager operations and SNMPv3 informs. DES-CBC intentionally deferred — broken cipher, not present in `cryptography>=41`. Engine discovery via optional async `prepare(dispatcher)` hook on `UsmModel`; `session.py` awaits it on open. Discovery uses a dedicated `dispatcher.send_raw_and_receive(data) -> bytes` path that never surfaces to the normal request flow — REPORT never reaches `send_pdu()` or `response_from_pdu()`. `wrap_pdu`/`unwrap_message` stay synchronous. `security/usm.py` never imports `cryptography` at module level; privacy methods call `_require_cryptography()` which raises `ImportError` with install instructions if the package is absent. `UsmModel` is imported unconditionally in `__init__.py` — it always works; base install covers `noAuthNoPriv` plus `authNoPriv`, while privacy/authPriv flows require `[v3]`. CI installs `.[dev,v3]`. A dedicated test blocks `cryptography` via `patch.dict(sys.modules, {'cryptography': None})` and reimports `usm` to catch top-level import regressions even with `[v3]` installed. `V3Manager` mirrors `V2cManager`. `V3Notifier` supports `send_inform()` only — `send_trap()` raises `ProtocolError` because SNMPv3 traps require the sender's own authoritative engine state (RFC 3412 §7.1.9), which is not available after discovery against the receiver. v3 listener out of scope for this release. Requires `cryptography>=40` (optional extra `[v3]`). |

---

## v0.4.1 — shipped 2026-06-01

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Sender-authoritative SNMPv3 trap support | done | `UsmLocalEngine` is public and `V3Notifier.send_trap()` now works when explicit local authoritative engine state is provided. Trap-capable notifiers no longer depend on a peer discovery roundtrip during `open()`. |
| 2 | Shared CLI v2c/v3 security option model | done | `tsnmp` now accepts explicit `--snmp-version {2c,3}` selection, validates mixed v2c/v3 flag sets early, supports env-backed secrets, and surfaces missing `[v3]` extras for privacy/authPriv flows as ordinary CLI errors. |
| 3 | CLI SNMPv3 manager commands | done | `get`, `getnext`, `getbulk`, `walk`, and `bulkwalk` route through `V3Manager` when `--snmp-version 3` is selected. |
| 4 | CLI SNMPv3 notification send | done | `inform` and `trap` route through `V3Notifier` for `--snmp-version 3`; traps require explicit `--local-engine-id`, `--local-engine-boots`, and `--local-engine-time`. `listen` and `decode-notification` remain SNMPv2c-only. |
| 5 | CLI/docs/test/release parity | done | Docs, tests, and release smoke guidance now reflect the shipped Python and CLI SNMPv3 surface consistently. |

---

## v0.4.2 — shipped 2026-06-05

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | SNMPv3 notification listener | done | `V3NotificationListener` now supports one configured USM user, inbound auth/decrypt, discovery REPORT handling for `V3Notifier.send_inform()`, and automatic v3 inform acknowledgement. The existing `SnmpNotificationListener` / `V2cNotificationListener` surface remains v2c-compatible. |
| 2 | Offline SNMPv3 notification decode | done | `decode_notification(..., user=...)` now performs strict v3 decode, and `tsnmp decode-notification --snmp-version 3` accepts explicit user/auth/priv inputs for offline USM notification analysis. |
| 3 | Notification event model expansion for v3 | done | `NotificationEvent` now carries additive v3 metadata (`username`, `security_level`, context engine/name, authoritative engine state) while keeping current v2c text/JSON output stable. |

---

## v0.4.3 — shipped 2026-09-24

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | USM session-state fixes | done | `#12`. RFC 3414 key-derivation caching (Ku plus localized keys per user/engine), monotonic engine-time advance after discovery, and `usmStatsNotInTimeWindows` REPORT recovery with engine re-adoption and a single automatic manager retry. authPriv throughput is no longer KDF-bound (previously ~0.073s per message). |
| 2 | v3 listener replay protection | done | `#13`. RFC 3414 §3.2.7 receive-side checks: engine boots/time window tracking and a bounded per-user salt cache. Replayed traps are dropped and replayed informs are no longer re-ACKed. Drop reasons are plumbed (verdict enum) for the observability work in `#9`. |
| 3 | Wire codec hardening | done | `#14`. Encode/decode range validation for Counter32/Gauge32/TimeTicks (≤ 2^32-1) and Counter64 (≤ 2^64-1), rejection of non-minimal unsigned BER, `ProtocolError` for OID first/second-arc overflow, and latin-1 fallback for non-UTF-8 community strings. |
| 4 | Dispatcher robustness | done | `#15`. Malformed datagrams no longer abort in-flight requests (behavior now uniform across v2c and v3 security models), request IDs are urandom-derived per RFC 3412, and per-request deadlines cannot be extended by junk datagrams. |
| 5 | Bundle schema-version gate | done | `schema_version` above the supported maximum (`1.1`) is rejected at load time (module payloads and `manifest.json`) with an actionable error — the consumer-side half of the documented `tsmi` bundle-compatibility policy. |
| 6 | `trishul-snmp` CLI entry point | done | Both `tsnmp` and `trishul-snmp` console scripts now install and invoke the same CLI; usage strings reflect the invoked name. |
| 7 | `trishul-smi 0.5.0` compatibility | done | Full ecosystem validation via `scripts/validate_ecosystem.py` (compile, bundle contract, runtime load, CLI translate, live agent, notification, responder) passes against `trishul-smi 0.5.0`. |

---

## v0.5.0 — shipped 2026-09-24

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | SNMPv1 support | done | `#8`. v1 message/PDU codec (0xa0–0xa4 incl. Trap-PDU), `V1Manager` GET/GETNEXT (GETBULK downgrades to GETNEXT loops), `V1Notifier` trap send, v1 trap receive on the community listener, and `decode_notification` v1 support with enterprise/agent-addr/generic/specific/timestamp metadata on `NotificationEvent`. CLI `--snmp-version 1` across manager/trap/listen/decode. |
| 2 | USM crypto parity (Reeder) | done | `#10`. SHA-224/384/512 auth (RFC 7860), AES-192/256 with Reeder key derivation, and 3DES-EDE. Blumenthal (RFC 8963) variants stay deferred until a concrete deployment requires them. |
| 3 | DES-CBC privacy | deferred | `#11`. Attempted, empirically blocked: `cryptography` 48.0.0 exposes no single-DES primitive (TripleDES only) and vendoring crypto is out of the question. `PrivProtocol.DES` and the CLI selection fail fast with accurate errors instead of wire-time surprises. |
| 4 | Listener observability | done | `#9`. Shared `DropReason` taxonomy (including the v0.4.3 replay verdicts), drop counters, rate-limited warnings, and `on_error` callbacks on both community and v3 listeners. |
| 5 | Decoder fuzz/property tests and real-agent CI | done | `hypothesis` property/fuzz coverage for the untrusted-input BER decode path (no decoder bugs found: 700+ arbitrary inputs, only `ProtocolError` or clean decodes) plus snmpd-backed integration tests (`-m snmpd`) with a CI job on 127.0.0.1:1161. |

## Near-term hardening

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Forward-compatibility with future `tsmi` IR version fields | done | Landed in `v0.4.3`: explicit `schema_version` metadata is read and enforced at load time (accept ≤ `1.1`, reject newer with an actionable error) without making sidecars mandatory. |
| 2 | Better optional rendering fidelity from bundle metadata | planned | Improve display names and values when metadata is available without moving compiler logic into `tsnmp`. |
| 3 | Broader live-agent compatibility coverage | planned | Expand UDP integration coverage around walk behavior and device quirks. |

---

## Explicitly deferred

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Raw MIB file or raw MIB directory ingestion | deferred | Keep the runtime/compiler split clear; use compiled JSON only. |
| 2 | Direct runtime dependency on `trishul-smi` | deferred | `tsnmp` consumes artifacts, not the compiler package. |
| 3 | Public generic JSON normalization layer for non-`tsmi` schemas | deferred | Only add with an explicit adapter contract and real cross-schema use cases. |
| 4 | `pysnmp` API compatibility layer | deferred | Avoid carrying legacy surface area in `v0.1`. |
| 5 | Sync wrapper | deferred | Async-first package API remains the primary runtime surface. |
| 6 | Broader SNMPv3 server-side/runtime work beyond `v0.4.2` | deferred | `v0.4.2` covers the inbound listener and offline decode path. Larger server-side SNMPv3 work such as responder/agent behavior, multi-user listeners, and deeper state-management infrastructure remains follow-on. |
| 7 | `set` | deferred | Write operations need separate safety and API design. |
| 8 | Daemon/service packaging for long-running listeners | deferred | Library-level listener and responder APIs exist on main branch; daemonization is still out of scope. |
| 9 | Full agent framework or writable responder support | deferred | `v0.2.0` only targets a narrow read-only simulator/responder. |
| 10 | Native codec experiment | deferred | Pure codec microbenchmarks improved, but end-to-end manager and responder paths did not justify the extra Rust build, packaging, and dual-implementation maintenance cost. Revisit only if a broader native hot-path effort is planned. The v0.4.3 USM key-caching work removed the main end-to-end performance motivation. |
| 11 | Blumenthal AES-192/256 key derivation (RFC 8963) | deferred | The v0.5.0 crypto-parity work (`#10`) ships the Reeder variants first — dominant in field AES-192/256 device configs. Blumenthal variants are added only if a concrete deployment requires them. |
| 12 | DES-CBC privacy (single DES) | deferred | Empirically blocked (v0.5.0, `#11`): the `cryptography` backend exposes no single-DES primitive (TripleDES only, in `decrepit`). `PrivProtocol.DES` fails fast with an accurate error; revisit only if a legacy device absolutely requires single-DES and a supported backend appears. |
