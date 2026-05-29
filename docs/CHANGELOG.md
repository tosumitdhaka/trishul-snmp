# Changelog

All notable changes to `trishul-snmp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.4.0] — 2026-05-28

### Added

- **SNMPv3 USM** — full noAuthNoPriv, authNoPriv (HMAC-MD5 / SHA-1 / SHA-256), and authPriv (AES-128-CFB) support. DES-CBC intentionally omitted — broken cipher, not present in `cryptography>=41`.
- **Engine discovery** — `UsmModel.prepare(dispatcher)` sends an RFC 3414 probe and caches engineID / engineBoots / engineTime; `SnmpSession.open()` awaits it automatically when the security model exposes the method.
- **`V3Manager`** — thin subclass of `SnmpManager` that accepts a `UsmUser` and wires a `UsmModel` internally, mirroring the `V2cManager` pattern.
- **`V3Notifier`** — `send_inform()` supported; `send_trap()` raises `ProtocolError`. SNMPv3 traps require the sender's own authoritative engine state (RFC 3412 §7.1.9), which is unavailable after engine discovery against the receiver.
- **`AuthenticationError`** — new exception raised on HMAC verification failure; subclass of `ProtocolError`.
- **`cryptography>=40` optional extra** — `pip install trishul-snmp[v3]`; the package imports and works without it, only auth/priv method calls fail with a clear install hint.

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
