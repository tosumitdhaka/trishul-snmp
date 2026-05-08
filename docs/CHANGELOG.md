# Changelog

All notable changes to `trishul-snmp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
