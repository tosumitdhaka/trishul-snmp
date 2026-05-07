# Changelog

All notable changes to `trishul-snmp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0a0] — 2026-05-06

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

See [v0.1.0a0 alpha release notes](archive/v0.1.0a0-alpha.md) for the fuller
release summary.
