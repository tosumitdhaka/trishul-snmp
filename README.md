# trishul-snmp

[![CI](https://github.com/tosumitdhaka/trishul-snmp/actions/workflows/ci.yml/badge.svg)](https://github.com/tosumitdhaka/trishul-snmp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](#development)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/tosumitdhaka/trishul-snmp?style=flat)](https://github.com/tosumitdhaka/trishul-snmp/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/tosumitdhaka/trishul-snmp?style=flat)](https://github.com/tosumitdhaka/trishul-snmp/forks)
[![GitHub Issues](https://img.shields.io/github/issues/tosumitdhaka/trishul-snmp)](https://github.com/tosumitdhaka/trishul-snmp/issues)

> A modern SNMP runtime and manager written in Python.

`trishul-snmp` (`tsnmp`) is a package-first SNMP runtime for manager-side use.
It keeps the protocol runtime independent from MIB compilation and uses compiled
JSON artifacts only when symbolic enrichment is desired.

The split with `trishul-smi` (`tsmi`) is intentional:

- `tsnmp`
  Runtime, transport, manager API, thin CLI, optional enrichment consumer
- `tsmi`
  Parser/compiler that produces compiled JSON artifacts

The primary product is the importable Python package. The CLI is intentionally
thin and secondary.

## Features

- async-first Python API
- manager-only SNMPv2c runtime
- read-only operations:
  - `get`
  - `get_next`
  - `get_bulk`
  - `walk`
  - `bulkwalk`
- in-tree BER / ASN.1 / SNMPv2c wire codec
- UDP transport and request dispatcher
- optional symbolic translation and display enrichment from compiled JSON MIB artifacts
- works with numeric OIDs and no MIB bundle loaded

## Scope

Current v0.1 baseline:

- manager-only
- SNMPv2c-only
- read-only operations only
- async-first Python API first, CLI second
- optional compiled-JSON enrichment via `tsmi` artifacts
- no runtime dependency on `trishul-smi`

Deliberately deferred:

- raw MIB file or raw MIB directory ingestion
- `pysnmp` API compatibility shims
- direct runtime dependency on the `trishul-smi` Python package
- sync wrapper
- SNMPv1
- SNMPv3
- `set`
- traps / listener
- agent/responder support
- compiler workflows inside `tsnmp`

## Installation

```bash
pip install trishul-snmp
```

For local development:

```bash
pip install -e .[dev]
```

Requires Python `>=3.10`.

## Quick Start

Numeric GET with no bundle:

```python
import asyncio

from trishul_snmp import V2cManager


async def main() -> None:
    async with V2cManager(host="10.0.0.10", community="public") as manager:
        response = await manager.get("1.3.6.1.2.1.1.3.0")
        for varbind in response.varbinds:
            print(varbind.oid_str, varbind.value_type, varbind.display_value)


asyncio.run(main())
```

Symbolic GET with a compiled JSON bundle:

```python
import asyncio

from trishul_snmp import V2cManager, load_bundle

bundle = load_bundle("./IF-MIB.json")


async def main() -> None:
    async with V2cManager(
        host="10.0.0.10",
        community="public",
        bundle=bundle,
    ) as manager:
        response = await manager.get("IF-MIB::ifDescr.1")
        for varbind in response.varbinds:
            print(varbind.display_name, "=", varbind.display_value)


asyncio.run(main())
```

## Documentation

- [Documentation Index](docs/index.md) — entry point for package docs
- [Getting Started](docs/getting-started.md) — install, first requests, and runtime flows
- [Python API](docs/python-api.md) — `V2cManager`, `load_bundle`, and public types
- [CLI Reference](docs/cli.md) — commands, options, exit codes, and examples
- [Configuration](docs/configuration.md) — manager constructor and bundle/runtime knobs
- [Architecture](docs/architecture.md) — layering, package structure, and call flows
- [Bundle Contract](docs/bundles.md) — compiled JSON inputs, sidecars, validation, scope
- [Roadmap](docs/roadmap.md) — shipped scope and deferred work
- [Contributing](docs/contributing.md) — dev setup and quality gates
- [Changelog](docs/CHANGELOG.md) — version history
- [v0.1.0a0 Alpha Release Notes](docs/archive/v0.1.0a0-alpha.md) — archived alpha notes
- [v0.1 Design Plan](docs/archive/tsnmp-v0.1-design.md) — historical planning and design doc

## Repository Layout

- `trishul_snmp/`
  Package source
- `tests/`
  Test suite
- `docs/`
  Application and design documentation
- `docs/archive/`
  Archived planning and historical release notes
- `README.md`
  Repository/GitHub landing page

## Community

Canonical package docs live under [`docs/`](docs/). GitHub/community entry
points live under [`.github/`](.github/).

- [Contributing Guide](.github/CONTRIBUTING.md)
- [Contributors](.github/CONTRIBUTORS.md)
- [Funding](.github/FUNDING.md)

## Development

Checks used in this repo:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m ruff format --check trishul_snmp tests
python3 -m mypy
```

## License

MIT — see [LICENSE](LICENSE).
