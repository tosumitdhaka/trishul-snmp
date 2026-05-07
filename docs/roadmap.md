# Roadmap

Tracks shipped scope, near-term work, and deferred work.
Status: `planned` | `in progress` | `done` | `deferred`

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
| 7 | SNMPv3 | deferred | Significant auth/privacy scope increase; not justified for `v0.1`. |
| 8 | `set` | deferred | Write operations need separate safety and API design. |
| 9 | Trap receiver / listener | deferred | Different runtime model and lifecycle from manager-side polling. |
| 10 | Agent / responder support | deferred | Separate product scope from the manager runtime. |
