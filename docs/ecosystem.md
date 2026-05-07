# Ecosystem and Compatibility

`tsnmp` is the runtime package in the Trishul SNMP split.
`tsmi` is the optional compiler/enrichment producer.

This page is the canonical summary of how those two packages fit together,
what compatibility is expected today, and where the current ecosystem edges
still are.

---

## Roles

The intended split is deliberate:

- `tsnmp`
  Protocol runtime, transport, manager API, thin CLI, optional enrichment consumer
- `tsmi`
  MIB parser/compiler that produces compiled JSON artifacts

`tsnmp` is designed to work without importing `trishul-smi` at runtime.
Core manager operations must still work when no bundle is loaded and when only
numeric OIDs are used.

---

## Current tested pairing

Latest known tested released pairing:

| Package | Version |
|---|---|
| `trishul-snmp` | `0.1.1` |
| `trishul-smi` | `0.4.2` |

What this pairing currently means in practice:

- `tsnmp` runtime operations work with no `tsmi` package present
- compiled JSON enrichment works when you explicitly load artifacts with `load_bundle(...)`
- a single compiled module JSON file is valid runtime input
- directory sidecars are optional for correctness

This is a compatibility window, not a forever-implicit promise for every future
JSON shape. If upstream JSON IR versioning changes, `tsnmp` should accept that
through an explicit compatibility path rather than by guesswork.

---

## Supported runtime inputs

Today `tsnmp` accepts:

- a single compiled module JSON file such as `IF-MIB.json`
- a directory of compiled module JSON files
- a directory of compiled module JSON files plus `manifest.json`
- a directory of compiled module JSON files plus `manifest.json` and `oid_index.json`

Important rule:

- module JSON is the atomic usable artifact
- `manifest.json` is optional bundle metadata
- `oid_index.json` is optional reverse-lookup acceleration

That means this is a valid and supported runtime flow:

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./IF-MIB.json")
```

and so is this:

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./compiled-mibs")
```

If dependency modules are missing, the expected failure mode is reduced
enrichment fidelity, not runtime breakage of core manager operations.

---

## Recommended user flows

### 1. Numeric-only runtime

Use `tsnmp` alone.

- no compiler required
- no bundle required
- numeric OIDs only

This is the lightest path and the default operational baseline.

### 2. Single-module enrichment

Compile one module and pass the resulting JSON file directly to `tsnmp`.

This is appropriate when you only care about a narrow subtree such as
`IF-MIB::ifTable`.

Example:

```python
from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./IF-MIB.json")
```

### 3. Directory bundle enrichment

Compile a broader module set and load the directory.

This is the better fit when you want:

- broader symbolic translation coverage
- better cross-module display names
- better reverse OID lookup behavior at runtime

---

## Current producer gap

The main ecosystem gap is now on the `tsmi` CLI surface, not on the `tsnmp`
runtime surface.

Current state with `trishul-smi 0.4.2`:

- published Python API can emit `manifest.json`
- published Python API can emit `oid_index.json`
- published CLI compile path emits module JSON files only

So:

- runtime consumption is in good shape
- CLI producer ergonomics are still incomplete

This is tracked upstream in
[`trishul-smi#9`](https://github.com/tosumitdhaka/trishul-smi/issues/9).

---

## What `tsnmp` does not do

To keep the boundary clear, `tsnmp` currently does not do any of the following:

- ingest raw MIB files directly
- ingest raw MIB directories directly
- import `trishul-smi` at runtime
- run compiler workflows internally
- promise broad best-effort support for arbitrary third-party JSON schemas

If non-`tsmi` JSON support becomes important later, it should land as an
explicit adapter contract or normalization layer, not as undocumented
best-effort ingestion.

---

## Practical status

At the current released pairing, the ecosystem is in a usable state:

- runtime usage is viable today
- single-file JSON and directory bundle flows both work
- sidecars improve ergonomics/performance but do not gate correctness
- the main remaining gap is exposing sidecar emission on the published `tsmi` CLI

For deeper details, see:

- [Getting Started](getting-started.md)
- [Python API](python-api.md)
- [Bundle Contract](bundles.md)
- [Architecture](architecture.md)
- [Roadmap](roadmap.md)
