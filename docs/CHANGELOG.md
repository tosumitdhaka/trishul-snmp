# Changelog

All notable changes to `trishul-snmp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
