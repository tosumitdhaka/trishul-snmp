# trishul-snmp

[![CI](https://github.com/tosumitdhaka/trishul-snmp/actions/workflows/ci.yml/badge.svg)](https://github.com/tosumitdhaka/trishul-snmp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](#development)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/tosumitdhaka/trishul-snmp?style=flat)](https://github.com/tosumitdhaka/trishul-snmp/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/tosumitdhaka/trishul-snmp?style=flat)](https://github.com/tosumitdhaka/trishul-snmp/forks)
[![GitHub Issues](https://img.shields.io/github/issues/tosumitdhaka/trishul-snmp)](https://github.com/tosumitdhaka/trishul-snmp/issues)

> A modern SNMP runtime, manager, and simulator toolkit written in Python.

`trishul-snmp` (`tsnmp`) is a package-first SNMP runtime for manager-side use,
notification handling, and narrow simulator-style responder flows. It keeps the
protocol runtime independent from MIB compilation and uses compiled JSON
artifacts only when symbolic enrichment is desired.

For the canonical `tsnmp`/`tsmi` split, tested version pairing, and current
ecosystem status, see [Ecosystem and Compatibility](docs/ecosystem.md).

The split with `trishul-smi` (`tsmi`) is intentional:

- `tsnmp`
  Runtime, transport, manager API, thin CLI, optional enrichment consumer
- `tsmi`
  Parser/compiler that produces compiled JSON artifacts

The primary product is the importable Python package. The CLI is intentionally
thin and secondary. It installs as both `tsnmp` and `trishul-snmp` console
scripts (same command surface); usage output reflects whichever name was invoked.

## Features

- async-first Python API
- SNMPv1 manager runtime (`V1Manager`; GETBULK downgrades to GETNEXT loops)
- SNMPv2c manager runtime
- SNMPv3 USM manager runtime (`V3Manager`; noAuthNoPriv, authNoPriv HMAC-MD5/SHA-1/SHA-224/SHA-256/SHA-384/SHA-512, authPriv AES-128/192/256 (Reeder) and 3DES-EDE)
- read-only operations:
  - `get`
  - `get_next`
  - `get_bulk`
  - `walk`
  - `bulkwalk`
- outbound SNMPv1 trap send (`V1Notifier`; enterprise/generic/specific fields)
- outbound SNMPv2c trap and inform send
- outbound SNMPv3 USM trap and inform send (`V3Notifier`; traps require `UsmLocalEngine`)
- inbound SNMPv1, SNMPv2c, and SNMPv3 USM trap and inform listen (`V3NotificationListener` handles one configured user) with drop counters, rate-limited warnings, and `on_error` hooks
- offline SNMPv1, SNMPv2c, and strict SNMPv3 USM notification decode
- narrow read-only SNMPv2c responder / simulator
- simulation rules for dynamic OID values (counters, gauges, uptime, timestamps)
- bundle-backed auto-population of simulator object sets
- in-memory MIB bundle iteration and substring search
- JSON-safe notification event serialization
- in-tree BER / ASN.1 / SNMPv2c + SNMPv3 wire/security codec
- UDP transport and request dispatcher
- optional symbolic translation and display enrichment from compiled JSON MIB artifacts
- works with numeric OIDs and no MIB bundle loaded
- live CLI commands cover SNMPv1, SNMPv2c, plus SNMPv3 manager, notification send, notification listen, and offline decode

## Scope

Current main-branch baseline:

- manager operations plus notification send/listen/decode
- narrow read-only responder / simulator support
- SNMPv1 (community), SNMPv2c, and SNMPv3 USM (noAuthNoPriv, authNoPriv HMAC-MD5/SHA-1/SHA-224/SHA-256/SHA-384/SHA-512, authPriv AES-128/192/256 Reeder and 3DES-EDE)
- read-only operations only
- async-first Python API first, CLI second
- optional compiled-JSON enrichment via `tsmi` artifacts
- no runtime dependency on `trishul-smi`

Deliberately deferred:

- raw MIB file or raw MIB directory ingestion
- `pysnmp` API compatibility shims
- direct runtime dependency on the `trishul-smi` Python package
- sync wrapper
- DES-CBC privacy (no single-DES primitive in the `cryptography` backend; `PrivProtocol.DES` fails fast with an accurate error)
- `set`
- full agent framework
- writable responder support
- compiler workflows inside `tsnmp`

## Installation

```bash
pip install trishul-snmp
```

For SNMPv3 privacy/authPriv support (AES-128/192/256-CFB and 3DES-EDE encryption):

```bash
pip install "trishul-snmp[v3]"
```

The base package covers SNMPv1, SNMPv2c, plus SNMPv3 `noAuthNoPriv` and
`authNoPriv`. Install `[v3]` only for privacy/authPriv flows.

For local development:

```bash
pip install -e ".[dev,v3]"
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

SNMPv3 USM GET:

```python
import asyncio

from trishul_snmp import AuthProtocol, UsmUser, V3Manager

user = UsmUser(
    username="monitor",
    auth_protocol=AuthProtocol.SHA256,
    auth_key=b"authpass123",
)


async def main() -> None:
    async with V3Manager(host="10.0.0.10", user=user) as manager:
        response = await manager.get("1.3.6.1.2.1.1.3.0")
        for varbind in response.varbinds:
            print(varbind.oid_str, varbind.value_type, varbind.display_value)


asyncio.run(main())
```

Current CLI coverage includes SNMPv1, SNMPv2c, plus SNMPv3 `get`, `getnext`,
`getbulk`, `walk`, `bulkwalk`, `trap`, `inform`, `listen`, and
`decode-notification` via explicit `--snmp-version {1,2c,3}` selection. SNMPv3
`listen` requires explicit `--local-engine-id`, `--local-engine-boots`, and
`--local-engine-time`. SNMPv3 `decode-notification` requires explicit
user/auth/priv inputs.

## Documentation

- [Documentation Index](docs/index.md) — entry point for package docs
- [Getting Started](docs/getting-started.md) — install, first requests, and runtime flows
- [Ecosystem and Compatibility](docs/ecosystem.md) — `tsnmp`/`tsmi` split, tested pairing, bundle inputs, ecosystem status
- [Python API](docs/python-api.md) — manager, notify, responder, and public runtime types
- [CLI Reference](docs/cli.md) — polling, notification, and offline decode commands
- [Configuration](docs/configuration.md) — manager, notify, responder, and bundle/runtime knobs
- [Architecture](docs/architecture.md) — layering, package structure, and call flows
- [Bundle Contract](docs/bundles.md) — compiled JSON inputs, sidecars, validation, scope
- [Roadmap](docs/roadmap.md) — shipped scope and deferred work
- [Contributing](docs/contributing.md) — dev setup and quality gates
- [Changelog](docs/CHANGELOG.md) — version history
- [v0.1.0 Release Notes](docs/archive/v0.1.0.md) — archived initial release notes
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
