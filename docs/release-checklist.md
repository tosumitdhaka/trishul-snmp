# Release Checklist

Follow this checklist for every release. Steps should be completed in order.

---

## 1. Pre-release verification

- [ ] All CI checks green on `main` (lint, typecheck, tests — Python 3.10–3.13)
- [ ] Lint passes with zero errors:
  ```bash
  ruff check trishul_snmp tests scripts
  ```
- [ ] Formatting is clean:
  ```bash
  ruff format trishul_snmp tests scripts --check
  ```
- [ ] Type checking passes with zero errors:
  ```bash
  mypy trishul_snmp
  ```
- [ ] Full test suite passes:
  ```bash
  pytest -q
  ```
- [ ] Coverage meets the project threshold (>= 95%):
  ```bash
  pytest --cov=trishul_snmp --cov-report=term-missing:skip-covered --cov-fail-under=95 -q
  ```
- [ ] No release-blocking issues or milestone items remain unresolved

---

## 2. Version bump

- [ ] Update `version` in `pyproject.toml`
- [ ] Update `__version__` in `trishul_snmp/__init__.py`
- [ ] Add a new section to `docs/CHANGELOG.md` following the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:
  - Date in `YYYY-MM-DD`
  - `### Added` / `### Changed` / `### Fixed` / `### Removed` as applicable
  - `### Known limitations` if deferred issues remain relevant
- [ ] Update `docs/architecture.md` `Last updated` date if the architecture changed
- [ ] Update `docs/roadmap.md` to mark shipped items as `done` and note newly deferred work if needed
- [ ] Update `README.md` if install instructions, public API examples, or docs links changed

---

## 3. Final checks

- [ ] Run the full quality gate on a clean editable install:
  ```bash
  pip install -e ".[dev]"
  ruff check trishul_snmp tests scripts
  ruff format trishul_snmp tests scripts --check
  mypy trishul_snmp
  pytest --cov=trishul_snmp --cov-report=term-missing:skip-covered --cov-fail-under=95 -q
  ```
  Helper:
  ```bash
  python3 scripts/run_release_gate.py
  ```
  This runs the local release gate end to end: lint, format check, mypy, pytest,
  coverage, build, wheel smoke test, and temporary wheel-test venv cleanup.
  Use `--smoke-host 127.0.0.1` to add a live post-install `tsnmp get` smoke test
  against a reachable local agent.

- [ ] Build source and wheel distributions:
  ```bash
  pip install hatch
  hatch build
  ls -lh dist/
  ```

- [ ] Smoke-test the built wheel from a clean venv:
  ```bash
  python -m venv /tmp/tsnmp-release-test
  /tmp/tsnmp-release-test/bin/pip install dist/trishul_snmp-x.y.z-py3-none-any.whl
  /tmp/tsnmp-release-test/bin/tsnmp version
  /tmp/tsnmp-release-test/bin/python -c "from trishul_snmp import V2cManager, load_bundle; print('import ok')"
  ```

- [ ] Verify the wheel has no duplicate entries:
  ```bash
  python -c "
  import zipfile, collections
  z = zipfile.ZipFile('dist/trishul_snmp-x.y.z-py3-none-any.whl')
  dupes = [n for n, c in collections.Counter(z.namelist()).items() if c > 1]
  print('DUPLICATES:', dupes or 'none')
  "
  ```

- [ ] Run ecosystem validation against the intended `tsmi` pairing:
  ```bash
  python3 scripts/validate_ecosystem.py \
    --tsmi-version 0.4.3 \
    --mib-dir /var/lib/mibs/ietf \
    --mib-dir /var/lib/mibs/iana \
    --host 127.0.0.1 \
    --keep-work-dir
  ```
  This validates `tsmi` CLI output shapes, standalone module JSON loading, directory sidecar loading, live manager calls against a real agent, local trap/inform send/listen/decode, and local responder behavior.

- [ ] If a reachable test SNMP agent is available, do one live smoke test from the clean venv:
  ```bash
  /tmp/tsnmp-release-test/bin/tsnmp get --host 127.0.0.1 1.3.6.1.2.1.1.3.0
  ```
  This is optional but useful for catching packaging or runtime issues that unit tests may miss.

---

## 4. Tag and publish

- [ ] Commit the version bump and changelog: `git commit -m "chore: release vx.y.z"`
- [ ] Tag the commit: `git tag vx.y.z`
- [ ] Push the tag: `git push origin vx.y.z`
- [ ] Confirm the `release` GitHub Actions workflow completes successfully:
  - Test before release
  - Build distribution
  - Publish to PyPI
  - Create GitHub Release
- [ ] Verify the package is live:
  ```bash
  pip install trishul-snmp==x.y.z
  tsnmp version
  ```

---

## 5. Post-release

- [ ] Close the milestone on GitHub if one was used
- [ ] Update any open issues resolved by the release
- [ ] Add or archive any standalone release notes under `docs/archive/` if the release warrants them
- [ ] Note any known limitations in the GitHub Release description if they are not already covered in the changelog
