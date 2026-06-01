# Contributing

---

## Setup

```bash
git clone https://github.com/tosumitdhaka/trishul-snmp
cd trishul-snmp
pip install -e ".[dev,v3]"
```

---

## Common commands

```bash
# Run the full test suite
pytest -q

# Run with coverage
pytest --cov=trishul_snmp --cov-report=term-missing:skip-covered --cov-fail-under=95 -q

# Type checking
mypy

# Lint
ruff check .

# Format check
ruff format --check trishul_snmp tests
```

---

## Project conventions

- **Package-first runtime** — the importable Python API is the primary product; the CLI stays thin.
- **No runtime `trishul-smi` dependency** — `tsnmp` consumes compiled JSON artifacts only.
- **Numeric core, optional enrichment** — translation happens before send, enrichment after receive.
- **Async transport, sync helpers** — manager and transport are async; codec and bundle helpers stay simple and synchronous.
- **Keep layer boundaries clean** — `wire` handles protocol, `transport` handles UDP lifecycle, `manager` handles runtime behavior, `mib` handles optional enrichment.
- **Typed public APIs** — keep signatures explicit and maintain strict typing.
- **Tests with behavior changes** — runtime, bundle, CLI, and rendering changes should come with tests.
- **Docs move with the surface** — update docs when API, CLI, or bundle contract behavior changes.

---

## Running the CLI locally

```bash
# After pip install -e ".[dev,v3]"
tsnmp version
tsnmp translate --bundle ./IF-MIB.json IF-MIB::ifDescr.1
tsnmp get --host 127.0.0.1 1.3.6.1.2.1.1.3.0
```

---

## Scope guardrails

Please do not introduce these without explicit design discussion:

- raw MIB file or raw MIB directory ingestion
- direct runtime dependency on `trishul-smi`
- public generic JSON normalization for foreign schemas
- `pysnmp` compatibility shims
- `set`
- full agent framework or writable responder functionality
- SNMPv3 listener (USM-aware inform-ack — separate design needed)
- offline SNMPv3 notification decode and CLI parity for inbound v3 workflows
- DES-CBC privacy (broken cipher, deferred)

Those are not rejected forever, but they are outside the current baseline.

---

## CI

Pull requests should pass the CI gates before merge:

1. **Lint** — `ruff check` and `ruff format --check`
2. **Type-check** — `mypy`
3. **Tests** — `pytest` across Python 3.10 through 3.13 with a `95%` coverage gate

See [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
