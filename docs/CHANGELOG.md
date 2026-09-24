# Changelog

All notable changes to `trishul-snmp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.1] — 2026-09-24

### Fixed

- **`UsmUser` key-material validation (#16)** — construction-time `ProtocolError` for empty/missing auth/priv key material (messages name the field, the problem, and the protocol) and for localized auth keys of the wrong length (MD5 16 … SHA-512 64). The silent empty-key HMAC misconfiguration is no longer constructible.
- **Engine-recovery latency (#18)** — a `usmStatsNotInTimeWindows` REPORT now surfaces immediately as `EngineRecoveryReportError` (newly exported) instead of costing a full request timeout, and `V3Notifier.send_inform` now retries once after engine re-adoption, matching the manager.
- **v3 listener decode dedup (#17)** — each inbound datagram is BER-decoded exactly once (`V3DecodedDatagram` threaded through verification); previously the v3 path decoded 2–3 times per datagram. No behavior change to drop taxonomy, replay checks, or event payloads.

---

## [0.5.0] — 2026-09-24

### Added

- **SNMPv1 support (#8)** — `V1Manager` (GET/GETNEXT with GETBULK downgraded to GETNEXT loops), `V1Notifier` v1 trap send (enterprise/agent-addr/generic/specific/timestamp), v1 trap receive on the community listener (one allowlist serves both v1 and v2c datagrams), and `decode_notification` v1 support with the trap metadata on `NotificationEvent` and `to_dict()`. CLI: `--snmp-version 1` across manager, trap, listen, and decode-notification commands.
- **USM crypto parity (#10)** — SHA-224/SHA-384/SHA-512 auth (RFC 7860), AES-192/AES-256 privacy with Reeder key derivation, and 3DES-EDE privacy. Blumenthal (RFC 8963) variants remain deferred.
- **Listener observability (#9)** — shared `DropReason` taxonomy (including the v0.4.3 replay verdicts), drop counters (`dropped`, `drop_counts`), rate-limited warning logging, and `on_error` callbacks on both the community and v3 listeners.
- **Decoder fuzz/property tests and snmpd CI** — `hypothesis` property tests asserting the BER decoder never crashes on arbitrary input (no decoder bugs found), plus snmpd-backed live integration tests (`pytest -m snmpd`) with a dedicated CI job.

### Known limitations

- **DES-CBC (#11) remains unimplemented** — empirically blocked: the `cryptography` backend (48.0.0) exposes no single-DES primitive (TripleDES only). `PrivProtocol.DES` and the CLI `--priv-protocol des` selection fail fast with accurate errors instead of wire-time surprises.
- SNMPv1 has no inform operations; `inform --snmp-version 1` fails fast.

---

## [0.4.3] — 2026-09-24

### Fixed

- **USM session state (#12)** — RFC 3414 key derivation is now cached per user/engine instead of re-running the 1 MiB password-to-key loop for every message; engine time advances monotonically after discovery; and a `usmStatsNotInTimeWindows` REPORT now triggers engine re-adoption with a single automatic manager retry instead of leaving the session permanently broken.
- **v3 listener replay protection (#13)** — the v3 notification path now enforces RFC 3414 §3.2.7 receive checks (engine boots/time window plus a bounded per-user salt cache). Replayed traps are dropped and replayed informs are no longer acknowledged.
- **Wire codec hardening (#14)** — unsigned integer ranges are validated on encode and decode (Counter32/Gauge32/TimeTicks ≤ 2^32-1, Counter64 ≤ 2^64-1), non-minimal unsigned BER is rejected, OID arc overflow raises `ProtocolError` instead of `ValueError`, and non-UTF-8 community strings round-trip via latin-1 fallback.
- **Dispatcher robustness (#15)** — malformed datagrams no longer abort in-flight requests for v2c (matching v3 behavior), request IDs are urandom-derived per RFC 3412, and per-request deadlines cannot be extended by junk datagrams.

### Added

- **Bundle schema-version gate** — `schema_version` above the supported maximum (`1.1`) is rejected at load time (module payloads and `manifest.json`) with an actionable error, implementing the consumer-side half of the documented `tsmi` bundle-compatibility policy.
- **`trishul-snmp` CLI entry point** — the package now installs both `tsnmp` and `trishul-snmp` console scripts targeting the same CLI.

### Changed

- CLI usage strings now display the invoked command name (`tsnmp` or `trishul-snmp`).

### Compatibility

- Validated end-to-end against `trishul-smi 0.5.0` via `scripts/validate_ecosystem.py` (compile, bundle contract, runtime load, CLI translate, live agent, notification, responder).

---

## [0.4.2] — 2026-06-05

### Added

- **SNMPv3 notification listener** — `V3NotificationListener` now handles one configured USM user, inbound auth/decrypt, discovery REPORT replies for notifier engine discovery, and automatic v3 inform acknowledgement.
- **Offline SNMPv3 notification decode** — `decode_notification(..., user=...)` and `tsnmp decode-notification --snmp-version 3` now support strict USM-backed v3 notification decode.

### Changed

- **Notification event model and rendering** — `NotificationEvent` now carries additive v3 metadata (`username`, `security_level`, context engine/name, authoritative engine state); CLI text/JSON rendering stays stable for v2c and emits the extra v3 metadata when present.
- **CLI inbound notification coverage** — `tsnmp listen --snmp-version 3` now routes through `V3NotificationListener` and requires explicit `--local-engine-id`, `--local-engine-boots`, and `--local-engine-time`.

---

## [0.4.1] — 2026-06-01

### Added

- **Sender-authoritative SNMPv3 traps** — `UsmLocalEngine` is now public and `V3Notifier.send_trap()` is supported when the caller supplies explicit local authoritative engine state (`engine_id`, `engine_boots`, `engine_time`).
- **SNMPv3 live CLI support** — `tsnmp` now supports SNMPv3 `get`, `getnext`, `getbulk`, `walk`, `bulkwalk`, `trap`, and `inform` through explicit `--snmp-version {2c,3}` selection.
- **CLI SNMPv3 security parsing** — `--username`, auth/priv protocol and secret inputs, `--context-name`, and trap-only `--local-engine-*` options are now validated before any network I/O.

### Changed

- **`V3Notifier` behavior** — `send_inform()` discovers peer engine state lazily on first use, while trap-capable notifiers no longer depend on a discovery roundtrip during `open()`.
- **CLI error handling** — missing `[v3]` extras for privacy/authPriv workflows now surface as ordinary CLI errors with the install hint instead of a Python traceback.
- **Documentation and release guidance** — package docs now describe the shipped SNMPv3 CLI surface and the `V3Notifier.send_trap()` local-engine requirement.

### Known limitations

- `listen` and `decode-notification` remain SNMPv2c-only in `0.4.1`; SNMPv3 inbound/offline notification work is deferred to `0.4.2`.
- DES-CBC privacy remains deferred; `PrivProtocol.DES` is retained only for wire-level identification and still raises `ProtocolError` at runtime.

---

## [0.4.0] — 2026-05-28

### Added

- **SNMPv3 USM** — full noAuthNoPriv, authNoPriv (HMAC-MD5 / SHA-1 / SHA-256), and authPriv (AES-128-CFB) support. DES-CBC intentionally omitted — broken cipher, not present in `cryptography>=41`.
- **Engine discovery** — `UsmModel.prepare(dispatcher)` sends an RFC 3414 probe and caches engineID / engineBoots / engineTime; `SnmpSession.open()` awaits it automatically when the security model exposes the method.
- **`V3Manager`** — thin subclass of `SnmpManager` that accepts a `UsmUser` and wires a `UsmModel` internally, mirroring the `V2cManager` pattern.
- **`V3Notifier`** — `send_inform()` supported; `send_trap()` raises `ProtocolError`. SNMPv3 traps require the sender's own authoritative engine state (RFC 3412 §7.1.9), which is unavailable after engine discovery against the receiver.
- **`AuthenticationError`** — new exception raised on HMAC verification failure; subclass of `ProtocolError`.
- **`cryptography>=40` optional extra** — `pip install trishul-snmp[v3]`; the package imports and works without it, `noAuthNoPriv` and `authNoPriv` stay available, and privacy/authPriv calls fail with a clear install hint when the extra is absent.

### Changed

- **CI and release workflows** now install `.[dev,v3]` so the full test suite runs with crypto support.
- **`dispatcher.py`** gained `send_raw_and_receive(data) -> bytes` for the USM discovery path; never used by normal `send_pdu` / `send_only` flows.

---

## [0.3.1] — 2026-05-15

### Fixed

- **`from_bundle()` now assigns simulation rules for dynamic syntax types** — counters (`Counter32`, `Counter64`, and variants) get a `CounterRule` that increments on every poll, timetick/timestamp syntaxes (`TimeTicks`, `TimeStamp`, `TimeInterval`) get an `UptimeRule`, and gauges (`Gauge32`, `Unsigned32`) get a `RandomNumericRule(min=0, max=1000)`. Previously all three were frozen at `0` as static values, making the simulator non-responsive over time.

---

## [0.3.0] — 2026-05-15

### Added

- **Simulation rule engine** — `CounterRule`, `RandomNumericRule`, `UptimeRule`, and `TimestampRule` let `InMemoryObjectSource` serve dynamic OID values (monotonically-increasing counters, random gauges, auto-incrementing timeticks, epoch timestamps) without any application-side callback code. The `SimulationRule` protocol is public for custom rules.
- **`InMemoryObjectSource.from_bundle()`** — class method that auto-populates a source from a `MibBundle`, generating scalar `.0` instances and column instances up to `max_instances`, with syntax-appropriate default values and optional deprecated-object filtering.
- **`MibBundle` iteration helpers** — `iter_objects()`, `iter_notifications()`, and `search()` allow callers to iterate or substring-search bundle nodes in memory without a separate database, enabling browser UIs and catalog features to query the bundle directly.
- **`NotificationEvent.to_dict()`** — returns a fully JSON-safe `dict` representation of a notification event, including varbinds and member bindings, suitable for WebSocket broadcast or storage without additional application-side serialization.

---

## [0.2.0] — 2026-05-08

### Added

- **SNMPv2c notification runtime** — `V2cNotifier` now supports outbound trap and inform send, and `V2cNotificationListener` supports inbound trap/inform receive with automatic inform acknowledgement.
- **Offline notification decode** — `decode_notification()` turns captured BER payloads into the same public `NotificationEvent` model used by the live listener.
- **Narrow read-only responder / simulator** — `V2cResponder`, `InMemoryObjectSource`, and `CallbackObjectSource` now cover `GET`, `GET_NEXT`, and `GET_BULK` for tests, demos, and simulator-style use.
- **Ecosystem validation harness** — `scripts/validate_ecosystem.py` now creates an isolated venv, validates `tsmi` CLI bundle output, exercises live manager flows against a real agent, and checks local notification and responder behavior end to end.

### Changed

- **Notification metadata retention and rendering** — `NotificationEvent` now carries notification OID/name/description, uptime, and declared member bindings derived from compiled JSON metadata when available.
- **CLI surface expanded** — `tsnmp` now includes `trap`, `inform`, `listen`, and `decode-notification` in addition to the manager polling commands.
- **Documentation refreshed for the current runtime surface** — README and package docs now describe notification and responder support rather than a manager-only baseline.
- **Release validation guidance expanded** — the release checklist now includes the dedicated ecosystem validation flow and host MIB directory guidance for real-world pairing checks.

---

## [0.1.1] — 2026-05-07

### Added

- **Live benchmark harness** — `scripts/benchmark_snmpd.py` compares raw vs enriched API and CLI paths against a live SNMP agent.
- **Alias-policy regression fixtures** — dedicated tests now separate `tsmi` sidecar contract validation from `tsnmp` display-policy behavior.

### Changed

- **Canonical display rendering for scalar instance aliases** — numeric translation and enrichment now prefer `MODULE::symbol.0` when an exact `.0` alias is an `OBJECT IDENTIFIER` for a scalar `OBJECT-TYPE`, without changing low-level exact lookup semantics.

---

## [0.1.0] — 2026-05-07

### Added

- **Async-first SNMPv2c manager runtime** — `V2cManager` is the primary public API.
- **Read-only manager operations** — `get`, `get_next`, `get_bulk`, `walk`, and `bulkwalk`.
- **In-tree wire codec** — BER / ASN.1 / SNMPv2c message and PDU encode/decode.
- **UDP transport and request dispatcher** — timeout, retry, community filtering, and request-id matching.
- **Optional compiled-JSON bundle loading** — single module JSON file or directory of module JSON files.
- **Optional symbolic translation and response enrichment** — bundle-backed input resolution and display rendering.
- **Thin CLI** — `translate`, `get`, `getnext`, `getbulk`, `walk`, `bulkwalk`, and `version`.
- **Project automation** — CI, release workflow, and package documentation baseline.

### Known limitations

- manager-only
- SNMPv2c-only
- read-only operations only
- package-first Python API first, CLI second
- no raw MIB ingestion or runtime compiler dependency
- no public generic JSON normalization layer for foreign schemas

See [v0.1.0 release notes](archive/v0.1.0.md) for the fuller
release summary.
