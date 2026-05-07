# tsnmp v0.1 Design Plan

Date: 2026-05-06
Status: revised planning baseline
Repo state: greenfield (`README.md` and `LICENSE` only at the time of writing)

## 1. What `tsnmp` Is

`tsnmp` is an importable Python SNMP manager runtime with a thin companion CLI.

The primary product is the Python package:

- importable manager classes and helpers
- BER / ASN.1 wire encode-decode for the supported SNMP subset
- UDP transport and request-response management
- manager-side read operations such as `get`, `getnext`, `getbulk`, `walk`, and `bulkwalk`
- optional MIB-aware translation and rendering from compiled JSON artifacts

The CLI exists for smoke testing, demos, debugging, and parity checks. It is not the primary v0.1 product surface.

`tsnmp` must work with no MIB tooling installed. A user must be able to perform live SNMP manager operations with numeric OIDs and raw typed values even when no MIB bundle is loaded.

`tsnmp` is not trying to replace existing SNMP command-line tools as a primary objective. Those tools already cover operator workflows over raw MIB inputs well. The differentiated goal here is a clean Python runtime.

## 2. Intended Split with `tsmi`

The ownership boundary should stay explicit.

| Concern | Owner |
|---|---|
| ASN.1 / SMI parsing | `tsmi` |
| import resolution across MIB modules | `tsmi` |
| producing compiled JSON artifacts | `tsmi` |
| defining and versioning the JSON IR | `tsmi` |
| loading compiled JSON bundles | `tsnmp` |
| OID and symbol translation at runtime | `tsnmp` |
| BER / SNMP encode-decode | `tsnmp` |
| UDP transport and request handling | `tsnmp` |
| manager API | `tsnmp` |
| optional CLI | `tsnmp` |
| runtime value formatting and enrichment | `tsnmp` |

The important rule is: `tsnmp` consumes `tsmi` output artifacts, but it does not become a compiler frontend in v0.1.

## 3. Goals

- Ship an importable Python runtime that works without a MIB compiler installed.
- Keep the protocol runtime independent from MIB enrichment.
- Support SNMPv2c manager operations first.
- Load compiled `tsmi` JSON artifacts for symbolic lookup and better output.
- Provide a small, explicit async-first public API rather than `pysnmp` compatibility layers.
- Keep the CLI thin and derived from the same Python API.
- Keep the codebase layered so protocol work can evolve without entangling compiler concerns.

## 4. Non-Goals for v0.1

- Full `pysnmp` API parity
- loading generated Python MIB modules
- accepting raw MIB files or raw MIB directories directly
- embedding MIB compile or fetch workflows inside `tsnmp`
- agent or responder functionality
- SNMPv3 USM / VACM / engine management
- full trap receiver / daemon behavior
- shipping a bundled MIB corpus
- publishing a generic third-party JSON ingest schema
- write support (`set`) unless the scope is explicitly expanded later

The point of v0.1 is to prove a clean runtime architecture, not to clone the entire legacy ecosystem.

## 5. Primary User Experience

### 5.1 Package First

The main user journey should be:

1. compile MIBs separately with `tsmi` if symbolic enrichment is desired
2. import `trishul_snmp` in Python
3. create an async manager
4. perform manager operations with numeric or symbolic targets
5. consume raw or enriched responses

The main design artifact is therefore the Python API, not the CLI syntax.

### 5.2 CLI Second

The CLI should remain intentionally small:

- enough to validate bundle loading
- enough to validate live manager behavior
- enough to debug output formatting
- not broad enough to pull the project toward raw-MIB frontend behavior

## 6. Core Design Principles

### 6.1 Numeric at the Core

Inside the manager, transport, and wire layers, requests and responses should be numeric only:

- outgoing requests carry numeric OIDs
- incoming responses produce numeric OIDs plus typed SNMP values
- symbolic resolution happens before send
- enrichment happens after receive

This keeps core SNMP behavior independent of any MIB source.

### 6.2 Artifact-Oriented Enrichment

`tsnmp` should load compiled JSON artifacts without importing `trishul-smi` as a Python package.

That keeps deployment simple:

- the runtime install stays small
- precompiled bundles can be produced elsewhere
- runtime behavior does not depend on compiler availability
- the runtime/compiler split remains enforceable

### 6.3 Async-First Public API

The public package surface should be async-first.

That fits the transport model better than a blocking-first surface:

- UDP request lifecycles are naturally async
- retries and timeouts fit one async client cleanly
- higher-level applications can compose multiple sessions without thread wrappers

A sync facade may be added later, but it is not part of the v0.1 critical path.

### 6.4 Strict Validation at Bundle Boundaries

The current `tsmi` JSON is usable but not yet fully versioned as a downstream contract.

`tsnmp` therefore should:

- validate required fields on load
- reject malformed or incomplete module files
- warn when loading legacy unmanifested bundles
- prefer future manifest and IR-version metadata when upstream issues `#6` and `#7` land

### 6.5 Internal Normalization, One Adapter Only

Inside `tsnmp`, bundle data should be normalized into an internal registry model.

v0.1 should ship only one external adapter:

- current `tsmi` 0.3.x JSON bundle directories

This preserves a future extension point without publishing a generic ingest schema too early.

## 7. Runtime Layering

Recommended layering:

1. `wire/`
   Handles BER TLV parsing, ASN.1 value types, SNMP message parsing, and PDU encode-decode.
2. `transport/`
   Handles UDP sockets, request IDs, timeout behavior, retry behavior, and response matching.
3. `manager/`
   Exposes async manager operations over numeric OIDs and raw SNMP values.
4. `mib/`
   Loads compiled JSON bundle directories, builds indexes, resolves names, and formats values.
5. `cli/`
   Thin wrappers over the same manager and bundle APIs.

Dependency direction should remain one-way:

- `wire` imports nothing from `transport`, `manager`, or `mib`
- `transport` depends on `wire`
- `manager` depends on `transport` and `wire`
- `mib` depends on shared runtime types, but not on `transport`
- `cli` is the composition layer

This is the key feasibility constraint. If `manager` starts importing MIB-specific logic directly, `tsmi` stops being optional in practice.

## 8. Recommended Package Layout

Use a `src/` layout from the start.

```text
src/
  trishul_snmp/
    __init__.py
    errors.py
    types.py

    wire/
      __init__.py
      ber.py
      asn1.py
      message.py
      pdu.py

    transport/
      __init__.py
      udp.py
      dispatcher.py

    manager/
      __init__.py
      client.py
      operations.py
      walk.py

    mib/
      __init__.py
      bundle.py
      loader.py
      registry.py
      render.py
      models.py

    cli/
      __init__.py
      main.py
      common.py
      output.py

tests/
docs/
```

Suggested responsibilities:

- `types.py`
  Public dataclasses and enums such as OID, VarBind, Response, error-status enums, and manager result types.
- `wire/`
  Pure protocol logic only.
- `transport/dispatcher.py`
  Request ID allocation, outstanding request tracking, timeout handling, and retry orchestration.
- `manager/client.py`
  Async client lifecycle and top-level operations.
- `mib/models.py`
  Internal normalized registry records derived from bundle JSON.
- `mib/loader.py`
  Reads a module JSON file or bundle directory and validates module JSON.
- `mib/registry.py`
  Builds symbol indexes, type indexes, and longest-prefix OID lookup structures.
- `mib/render.py`
  Converts raw varbinds into richer output using object metadata, TCs, enums, display hints, and best-effort index rendering.

## 9. Python API Proposal

The public Python API is the primary v0.1 design surface.

Example shape:

```python
from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./mibs-json")  # optional

async with V2cManager(
    host="10.0.0.1",
    community="public",
    timeout=2.0,
    retries=1,
    bundle=bundle,
) as manager:
    response = await manager.get(
        "IF-MIB::ifDescr.1",
        "1.3.6.1.2.1.1.3.0",
    )

for vb in response.varbinds:
    print(vb.oid, vb.display_name, vb.display_value)
```

Recommended public entry points:

- `load_bundle(path) -> MibBundle`
- `V2cManager(...)`
- `await manager.get(*targets)`
- `await manager.get_next(*targets)`
- `await manager.get_bulk(*targets, non_repeaters=0, max_repetitions=10)`
- `await manager.walk(root, *, bulk=True, max_repetitions=10)`
- `bundle.translate(target)`

Recommended behavior:

- numeric OIDs are always accepted
- symbolic targets are accepted only when a bundle is loaded
- `load_bundle(path)` accepts either a single compiled module JSON file or a directory of compiled module JSON files
- the manager normalizes all targets to numeric OIDs before send
- the response object remains useful even when no bundle is loaded

Recommended result model:

- `Response`
  Carries request metadata, SNMP error status, and `varbinds`.
- `VarBind`
  Always carries numeric OID and raw typed value.
  When enrichment is available, it also carries resolved name and display text.
- `MibBundle`
  Exposes translation and reverse-lookup services used by both API and CLI.

Sync API guidance:

- do not make a sync facade part of the v0.1 critical path
- if added later, keep it thin over the async implementation

## 10. How Optional `tsmi` Enrichment Should Fit

### 10.1 Runtime Contract

The runtime-facing enrichment abstraction should stay small, even if v0.1 only ships one adapter.

Required capabilities:

- resolve symbolic input to numeric OIDs
- reverse-resolve numeric OIDs to the closest known object
- look up object and TC metadata
- render values for API and CLI output

This boundary may stay internal at first, but it should be real in the code.

### 10.2 v0.1 Enrichment Input Contract

v0.1 should accept:

- a single compiled module JSON file
- a directory of compiled module JSON files

v0.1 should not accept:

- raw MIB files
- raw MIB directories
- direct `tsmi` runtime imports
- direct compiler invocation from `tsmp`

Sidecars are optional:

- `manifest.json` is optional bundle metadata
- `oid_index.json` is optional performance metadata

That keeps the runtime/compiler split explicit, avoids input ambiguity, and prevents sidecars from becoming correctness requirements.

### 10.3 Current `tsmi` JSON Reality

Today, `tsmi` emits one JSON file per module and includes enough information for runtime use:

- absolute `oid` and `oid_path`
- `object_type`, `class`, and `nodetype`
- `syntax`, `constraints`, `max_access`, `status`
- `index` and `augments`
- `notifications.*.members`
- `types.*.base_type`, `display_hint`, and `constraints`
- `module_metadata`

That is already enough for:

- offline translation
- longest-prefix object matching
- common TC-based rendering
- walk output enrichment

### 10.4 Loader Behavior for v0.1

Recommended load behavior:

1. Accept either a single module JSON file path or a directory path.
2. If the path is a single module JSON file, load it as a one-module bundle.
3. If the path is a directory and a manifest exists later, use it.
4. Otherwise scan `*.json` files in the directory and ignore obvious sidecars.
5. Validate module payload shape and `generated_by`.
6. Normalize payloads into internal registry records.
7. Build:
   - `(module, symbol) -> object` index
   - `oid_path -> object` exact index
   - longest-prefix lookup structure for instance OIDs
   - type metadata lookup
8. If `oid_index.json` exists, use it as a reverse-lookup accelerator only.
9. Expose a single in-memory bundle/registry object to the API and CLI.

The important rule is progressive enrichment, not all-or-nothing bundle validity. Missing sidecars must not prevent basic use, and missing dependency module JSON files may reduce enrichment fidelity without blocking core manager operations.

### 10.5 Compatibility Strategy Until `tsmi` Issues `#5`, `#6`, and `#7` Land

The upstream issues matter directly to `tsnmp`:

- `#5` `oid_index.json`
  Useful for faster reverse lookup, but not a blocker because `tsnmp` can build its own in-memory indexes.
- `#6` bundle manifest
  Strongly preferred, because deterministic bundle loading is cleaner than directory heuristics.
- `#7` JSON IR versioning
  The most important contract issue. Without it, downstream compatibility is only "tested against known `tsmi` versions".

Recommended v0.1 position:

- support the current `tsmi` 0.3.x JSON shape explicitly
- treat a single module JSON file as a valid degenerate bundle
- document it as provisional compatibility
- adopt manifest and IR-version validation as soon as upstream provides them
- do not publish a public generic third-party JSON schema in v0.1

## 11. CLI Surface Proposal

The CLI is a secondary interface over the same Python API and bundle loader.

Recommended initial CLI:

| Command | Purpose |
|---|---|
| `tsnmp translate TARGET` | Translate numeric OID to symbol, or symbol to numeric OID |
| `tsnmp get TARGET [TARGET ...]` | Single request for one or more objects |
| `tsnmp getnext TARGET [TARGET ...]` | Next-object retrieval |
| `tsnmp getbulk TARGET [TARGET ...]` | Raw bulk retrieval |
| `tsnmp walk ROOT` | Sequential walk, defaulting to bulk when available |
| `tsnmp bulkwalk ROOT` | Explicit bulk walk |
| `tsnmp version` | Print version |

Suggested common options for live commands:

- `--host`
- `--port` default `161`
- `--community`
- `--timeout`
- `--retries`
- `--bundle PATH`
- `--numeric` to suppress symbolic rendering even when a bundle is present
- `--json` for machine-readable output

Specific command notes:

- `translate`
  Works offline with only `--bundle`, where the path may be a single module JSON file or a directory.
- `get` and `getnext`
  Accept either numeric or symbolic input. If symbolic input is used without a bundle, fail clearly.
- `walk` and `bulkwalk`
  Print one varbind per line by default and support `--json`.
- `getbulk`
  Needs `--non-repeaters` and `--max-repetitions`.

Deliberate exclusions from the initial CLI:

- no `set`
- no `trap-listen`
- no `mib compile`
- no raw MIB file or directory ingestion

## 12. End-to-End Call Flows

### 12.1 Offline Translation with Bundle

1. user compiles MIBs separately with `tsmi`
2. user calls `load_bundle("./mibs-json")`, `load_bundle("./IF-MIB.json")`, or `tsnmp translate --bundle ...`
3. `mib.loader` loads either a single module JSON file or scans a directory and validates module JSON
4. `mib.registry` builds symbol and OID indexes
5. bundle translation resolves:
   - `MODULE::symbol` -> numeric OID
   - numeric OID -> resolved object name
6. API or CLI returns the translated result

There is no SNMP traffic in this flow. It validates the enrichment boundary before runtime code is involved.

### 12.2 Raw Live `get` with No Bundle

1. caller passes a numeric OID target
2. `V2cManager.get()` accepts the numeric target directly
3. `manager` builds request varbinds
4. `transport.dispatcher` allocates a request ID and timeout tracking
5. `wire.pdu` and `wire.message` encode an SNMPv2c request
6. `transport.udp` sends the datagram
7. response is received and decoded back to numeric OIDs and typed values
8. `Response` and `VarBind` objects are returned with no enrichment fields populated

The numeric-only runtime starts before encode and stays numeric until return.

### 12.3 Enriched Live `get` with Bundle

1. caller loads a bundle and passes a symbolic or numeric target
2. symbolic input is resolved to a numeric OID before send
3. the manager, transport, and wire layers run exactly as in the raw flow
4. decoded varbinds come back as numeric OIDs and typed values
5. `mib.render` reverse-resolves OIDs and applies formatting where metadata exists
6. `Response` and `VarBind` objects are returned with both raw and enriched fields

The runtime stays numeric internally. Enrichment happens only after receive.

### 12.4 `walk` and `bulkwalk`

1. caller provides a root target
2. if symbolic, it is resolved to a numeric subtree root before the first request
3. `manager.walk()` repeatedly issues `getbulk` or `getnext`
4. each returned varbind is checked against subtree bounds
5. the walk stops on:
   - `endOfMibView`
   - OID leaving the requested subtree
   - non-increasing or invalid continuation
6. each varbind is optionally enriched after decode
7. results are returned through the API or formatted by the CLI

### 12.5 Bundle Load and Index Build

1. a module JSON file path or bundle directory path is provided
2. if the path is a file, it becomes a one-module bundle
3. if the path is a directory and a manifest exists, the loader uses it
4. otherwise `mib.loader` reads `*.json` and ignores sidecars
5. module payloads are validated and normalized
6. `mib.registry` builds:
   - `(module, symbol) -> object`
   - exact `oid_path -> object`
   - longest-prefix instance lookup
   - type metadata lookup
7. if `oid_index.json` exists, it may be used as an accelerator only
8. `MibBundle` exposes the resulting registry to translation and rendering logic

### 12.6 Future Compatibility Path

Today:

- loader supports the current `tsmi` 0.3.x module JSON shape from either a single file or a directory

Later:

- if a manifest exists, loader should prefer it
- if an IR version exists, loader should validate compatibility before indexing

## 13. v0.1 Scope

### 13.1 In Scope

- SNMPv2c manager runtime
- BER / ASN.1 support for the SNMP types required by v2c manager operations
- UDP request-response transport with timeout and retry controls
- offline bundle loading from `tsmi` JSON file or directory output
- offline translation:
  - numeric OID -> symbolic object name
  - symbolic object name -> numeric OID
- live operations:
  - `get`
  - `getnext`
  - `getbulk`
  - `walk`
  - `bulkwalk`
- raw operation without any MIB bundle
- enriched output when a MIB bundle is present
- common value formatting:
  - integers and enums
  - octet strings
  - object identifiers
  - counters and gauges
  - `TimeTicks`
  - `IpAddress`
  - SNMP exception values (`noSuchObject`, `noSuchInstance`, `endOfMibView`)

### 13.2 Nice to Have Only If Schedule Allows

- best-effort table index rendering for simple integer-based indexes
- offline decode of a captured SNMPv2 trap PDU
- sync convenience wrapper over the async API

These are acceptable only if they do not put the main package and runtime milestones at risk.

### 13.3 Deferred

- `set`
- SNMPv1 manager support
- SNMPv3
- trap receiver / listener
- INFORM send / receive flows
- complete notification pipeline
- aggressive walk optimizations beyond basic `getbulk`
- full TC and INDEX edge-case fidelity
- direct `tsmi` invocation from `tsnmp`
- raw MIB file or directory ingestion
- public generic third-party JSON ingest support

Deferring raw MIB ingestion is deliberate. Existing SNMP CLI tools already cover that user journey, and adding it here would blur the runtime/compiler split without improving the primary Python API.

## 14. Dependency and Build Choices

Recommended baseline:

- Python `>=3.10`
  Chosen to align with `trishul-smi` and avoid unnecessary environment fragmentation.
- `hatchling`
  Keeps packaging consistent with `tsmi`.
- `src/` layout
- `pytest`, `pytest-asyncio`, `mypy`, `ruff`
- stdlib `argparse` for the initial thin CLI
- plain text and JSON output in v0.1, with richer terminal formatting deferred unless the CLI grows

Recommended runtime dependency posture:

- no dependency on `pysnmp`
- no required dependency on `trishul-smi`
- no required dependency on `orjson`

Codec recommendation:

- implement the required BER / SNMP manager subset in-tree under `wire/`
- keep the subset narrow and explicit
- do not attempt generic ASN.1 support beyond SNMP needs

This is a pragmatic middle ground:

- cleaner than binding `pysnmp`
- smaller than trying to reproduce all of `pysnmp`
- controllable enough for the manager-only v0.1 target

## 15. Key Risks and Tradeoffs

### 15.1 Highest-Risk Items

1. Upstream JSON contract stability
   `tsmi` issue `#7` is the biggest architectural risk. Until IR versioning exists, `tsnmp` can only support a tested schema window, not a formally stable contract.
2. Bundle load performance on large MIB sets
   Without `oid_index.json` and manifest support, first load may be slower and more heuristic than desired.
3. BER correctness and malformed-packet handling
   The wire layer must be strict about lengths, tags, integer handling, and bounds.
4. Walk behavior against device quirks
   Some agents return non-increasing OIDs or odd `getbulk` behavior. The walk implementation needs clear stop rules.

### 15.2 Secondary Tradeoffs

- table index rendering will be incomplete if v0.1 only does best-effort suffix formatting
- users may expect `set` because this is a manager package; the scope cut must be documented clearly
- `tsmi` bug issues `#1` through `#4` are not architectural blockers, but they do affect trust in the artifacts users hand to `tsnmp`
- deferring a sync wrapper keeps the API cleaner, but raises the bar for synchronous consumers until a later release

## 16. Milestone-by-Milestone Plan

### Milestone 0: Lock Contracts and Skeleton

Deliverables:

- confirm scope and non-goals
- confirm Python baseline and packaging
- create package skeleton, test scaffold, and public error/result model
- document supported `tsmi` bundle contract for v0.1

Exit criteria:

- no unresolved ambiguity around package-first, v2c-only, manager-only, read-only scope

### Milestone 1: Bundle Loader and Library Translation

Deliverables:

- load current `tsmi` JSON module files and bundle directories
- validate module files
- normalize them into internal registry records
- build symbol and OID indexes
- expose `load_bundle()` and `bundle.translate()`

Exit criteria:

- offline translation works through the Python API with no network and no SNMP traffic
- symbolic input can be normalized to numeric OIDs
- numeric OIDs can be reverse-resolved to the closest known object

This is the first real proof point because it validates the `tsmi` boundary before wire work begins.

### Milestone 2: Core Wire and Transport Runtime

Deliverables:

- BER / ASN.1 encode-decode for required SNMP value types
- SNMPv2c message and PDU encode-decode
- UDP transport and request dispatcher
- raw async `get`, `getnext`, and `getbulk` over numeric OIDs

Exit criteria:

- live manager operations work through the Python API with no MIB bundle loaded
- failures are surfaced with explicit timeout, decode, or protocol errors

### Milestone 3: Enriched API and Walks

Deliverables:

- manager integration with bundle-backed translation
- enriched varbind rendering
- `walk` and `bulkwalk`
- the initial `V2cManager` package surface

Exit criteria:

- the same live operations work with symbolic input and enriched output
- raw mode still works and remains the fallback behavior

### Milestone 4: Thin CLI, Hardening, and Release Prep

Deliverables:

- thin CLI wrappers over `load_bundle()` and `V2cManager`
- protocol tests with malformed packets and device-like edge cases
- CLI polish and docs
- packaging metadata and versioning
- release notes for the explicit v0.1 scope

Exit criteria:

- the package is coherent as a manager-only alpha release
- the CLI is useful but visibly secondary
- deferred items are documented instead of half-implemented

## 17. Decisions to Lock Before Implementation Starts

1. `tsnmp` v0.1 is a Python package first and a CLI second.
2. `tsnmp` v0.1 is manager-only.
3. `tsnmp` v0.1 supports SNMPv2c only.
4. Core runtime works with numeric OIDs and no MIB bundle.
5. `tsmi` is optional and is consumed only as compiled JSON artifacts, not as a required runtime import.
6. v0.1 enrichment input is a compiled module JSON file or a directory of compiled module JSON files.
7. v0.1 does not accept raw MIB files or raw MIB directories.
8. Symbolic resolution happens only at the API and CLI edges; the runtime core stays numeric.
9. v0.1 ships read operations only: `translate`, `get`, `getnext`, `getbulk`, `walk`, and `bulkwalk`.
10. `set`, trap receiver support, SNMPv3, and agent functionality are deferred.
11. The project does not pursue `pysnmp` API parity in v0.1.
12. The codebase uses a `src/` layout and an async-first Python API.
13. The initial `tsmi` compatibility target is the current 0.3.x JSON shape, with a plan to adopt manifest and IR-version validation when upstream lands them.
14. `tsnmp` may normalize external artifacts internally, but it does not publish a generic third-party JSON ingest contract in v0.1.

## 18. Bottom Line

`tsnmp` is feasible as a clean, package-first manager runtime with optional JSON-backed MIB enrichment.

The strongest v0.1 architecture is:

- async-first Python API as the primary product surface
- numeric SNMP runtime at the core
- optional compiled-JSON enrichment at the edges
- CLI as a thin wrapper, not the center of the design
- aggressive scope control to avoid recreating `pysnmp`

That delivers a useful foundation without pulling `tsnmp` into compiler responsibilities or raw-MIB frontend behavior.
