# Bundle Contract

`tsnmp` consumes compiled JSON artifacts only. It does not compile raw MIB files
and it does not import `trishul-smi` at runtime.

---

## Purpose

Bundles provide optional symbolic translation and display enrichment.

Core SNMP manager operations work without bundles. Bundles add:

- symbolic target resolution
- reverse OID lookup
- better display names
- better display values when metadata is available

---

## Supported inputs

`load_bundle(path)` accepts:

- a single compiled module JSON file such as `IF-MIB.json`
- a directory containing compiled module JSON files

A single module JSON file is a valid degenerate bundle.

---

## Atomic contract

| Artifact | Required | Role |
|---|---|---|
| Module JSON (`IF-MIB.json`) | yes | Source of truth for module, object, and type metadata |
| `manifest.json` | no | Optional inventory sidecar for deterministic directory discovery |
| `oid_index.json` | no | Optional reverse-OID lookup accelerator |

The runtime must work when only a single compiled module JSON file is provided.
Directory sidecars improve discovery or performance, but they do not define
correctness.

---

## Directory discovery rules

If `manifest.json` is present:

- its module inventory is used
- referenced module files must exist inside the bundle directory

If `manifest.json` is absent:

- `tsnmp` scans `*.json` files in the directory
- `manifest.json` and `oid_index.json` are ignored as module candidates

If `oid_index.json` is present:

- it is validated and used as a lookup accelerator

If `oid_index.json` is absent:

- reverse lookup falls back to the loaded module records

---

## Validation

On load, `tsnmp` validates:

- top-level module JSON shape
- required fields such as `module` and `generated_by`
- object/type collections
- OID shape
- optional sidecar structure when present

Malformed artifacts raise `BundleValidationError`.

---

## Missing dependency modules

Bundles can still load even if referenced dependency modules are missing.

Effect:

- core SNMP operations still work
- translation may still work for local symbols
- enrichment fidelity may be reduced for imported types or cross-module metadata

This is deliberate. Missing compiled dependencies should not break the runtime
core when the caller intentionally loads a narrow subset such as `IF-MIB.json`.

---

## Relationship with `tsmi`

The split is intentional:

- `tsnmp`
  Runtime, transport, manager API, CLI, optional enrichment consumer
- `tsmi`
  Parser/compiler that produces compiled JSON artifacts

`tsnmp` consumes JSON artifacts only. It does not import or invoke `trishul-smi`
at runtime.

---

## Current compatibility window

Current `v0.1` behavior targets the tested `tsmi` JSON shape.

Still intentionally limited:

- no raw MIB ingestion
- no public compiler integration
- no public generic third-party JSON normalization layer
- no promise of broad schema compatibility beyond the supported contract window

If support for non-`tsmi` JSON schemas adds clear runtime value later, it should
land as an explicit adapter contract rather than ambiguous best-effort ingestion.

---

## Examples

Single module JSON:

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./IF-MIB.json")
```

Directory bundle:

```python
from trishul_snmp import load_bundle

bundle = load_bundle("./mibs-json")
```

---

## Notes for bundle producers

- Each module JSON should be independently loadable.
- Sidecars should remain additive rather than required for correctness.
- Future schema/version fields should be additive and machine-readable.
