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
| 2 | SNMPv3 USM client stack | done | Shipped noAuthNoPriv + authNoPriv (HMAC-MD5/SHA-1/SHA-256) + authPriv (AES-128-CFB) for manager operations and SNMPv3 informs. DES-CBC intentionally deferred — broken cipher, not present in `cryptography>=41`. Engine discovery via optional async `prepare(dispatcher)` hook on `UsmModel`; `session.py` awaits it on open. Discovery uses a dedicated `dispatcher.send_raw_and_receive(data) -> bytes` path that never surfaces to the normal request flow — REPORT never reaches `send_pdu()` or `response_from_pdu()`. `wrap_pdu`/`unwrap_message` stay synchronous. `security/usm.py` never imports `cryptography` at module level; auth/priv methods call `_require_cryptography()` which raises `ImportError` with install instructions if the package is absent. `UsmModel` is imported unconditionally in `__init__.py` — it always works; only calling auth/priv methods without `[v3]` fails. CI installs `.[dev,v3]`. A dedicated test blocks `cryptography` via `patch.dict(sys.modules, {'cryptography': None})` and reimports `usm` to catch top-level import regressions even with `[v3]` installed. `V3Manager` mirrors `V2cManager`. `V3Notifier` supports `send_inform()` only — `send_trap()` raises `ProtocolError` because SNMPv3 traps require the sender's own authoritative engine state (RFC 3412 §7.1.9), which is not available after discovery against the receiver. v3 listener out of scope for this release. Requires `cryptography>=40` (optional extra `[v3]`). |

---

## v0.4.1 — shipped 2026-06-01

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Sender-authoritative SNMPv3 trap support | done | `UsmLocalEngine` is public and `V3Notifier.send_trap()` now works when explicit local authoritative engine state is provided. Trap-capable notifiers no longer depend on a peer discovery roundtrip during `open()`. |
| 2 | Shared CLI v2c/v3 security option model | done | `tsnmp` now accepts explicit `--snmp-version {2c,3}` selection, validates mixed v2c/v3 flag sets early, supports env-backed secrets, and surfaces missing `[v3]` extras as ordinary CLI errors. |
| 3 | CLI SNMPv3 manager commands | done | `get`, `getnext`, `getbulk`, `walk`, and `bulkwalk` route through `V3Manager` when `--snmp-version 3` is selected. |
| 4 | CLI SNMPv3 notification send | done | `inform` and `trap` route through `V3Notifier` for `--snmp-version 3`; traps require explicit `--local-engine-id`, `--local-engine-boots`, and `--local-engine-time`. `listen` and `decode-notification` remain SNMPv2c-only. |
| 5 | CLI/docs/test/release parity | done | Docs, tests, and release smoke guidance now reflect the shipped Python and CLI SNMPv3 surface consistently. |

---

## v0.4.2 — planned

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | SNMPv3 notification listener | planned | Add a `V3NotificationListener` with explicit user/security configuration, inbound USM auth/decrypt, and correct v3 inform acknowledgement behavior. This is server-side SNMPv3 work and intentionally follows the `v0.4.1` client/CLI release. |
| 2 | Offline SNMPv3 notification decode | planned | Extend the offline notification tooling and `decode-notification` CLI path with a v3-aware decode flow that accepts explicit security context rather than assuming v2c community-based decode. |
| 3 | Notification event model expansion for v3 | planned | Add the security metadata needed for inbound v3 events and offline decode without regressing the current v2c event shape. |

## Near-term hardening

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Forward-compatibility with future `tsmi` IR version fields | planned | Accept explicit schema/version metadata once upstream lands it without making sidecars mandatory. |
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
| 6 | SNMPv1 manager support | deferred | Not required for the initial modern runtime baseline. |
| 7 | Broader SNMPv3 server-side/runtime work beyond `v0.4.2` | deferred | `v0.4.2` is expected to cover the inbound listener and offline decode path. Larger server-side SNMPv3 work such as responder/agent behavior and deeper state-management infrastructure remains follow-on. |
| 8 | `set` | deferred | Write operations need separate safety and API design. |
| 9 | Daemon/service packaging for long-running listeners | deferred | Library-level listener and responder APIs exist on main branch; daemonization is still out of scope. |
| 10 | Full agent framework or writable responder support | deferred | `v0.2.0` only targets a narrow read-only simulator/responder. |
| 11 | Native codec experiment | deferred | Pure codec microbenchmarks improved, but end-to-end manager and responder paths did not justify the extra Rust build, packaging, and dual-implementation maintenance cost. Revisit only if a broader native hot-path effort is planned. |
| 12 | DES-CBC privacy (USM) | deferred | DES is a broken cipher (56-bit key). Not present in `cryptography>=41`; the `PrivProtocol.DES` enum value is retained for wire-level identification but `_encrypt_des`/`_decrypt_des` raise `ProtocolError`. Revisit only if required for a legacy-device integration with no alternative. |
