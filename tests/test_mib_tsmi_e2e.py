"""End-to-end: real trishul-smi 0.5.2 bundle consumed by the tsnmp runtime.

Requires trishul-smi to be importable in the active environment; the test is
skipped otherwise (trishul-smi is not a runtime or dev dependency).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from trishul_snmp import IntegerValue, OctetStringValue, VarBind
from trishul_snmp.mib.loader import load_bundle
from trishul_snmp.mib.render import enrich_varbinds

_HAS_TSMI = importlib.util.find_spec("trishul_smi") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_TSMI,
    reason="trishul-smi is not installed in the active environment",
)

_TINY_MIB = """\
TEST-E2E-MIB DEFINITIONS ::= BEGIN

IMPORTS
    MODULE-IDENTITY, OBJECT-TYPE, Integer32, Gauge32, enterprises
        FROM SNMPv2-SMI;

testE2EMib MODULE-IDENTITY
    LAST-UPDATED "202601010000Z"
    ORGANIZATION "Test"
    CONTACT-INFO "none"
    DESCRIPTION "End-to-end rendering test module."
    REVISION "202601010000Z"
    DESCRIPTION "Initial revision."
    ::= { enterprises 99999 }

status OBJECT-TYPE
    SYNTAX INTEGER { up(1), down(2), testing(3) }
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "Status."
    ::= { testE2EMib 1 }

speed OBJECT-TYPE
    SYNTAX Gauge32
    UNITS "bits/second"
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "Speed."
    ::= { testE2EMib 2 }

flags OBJECT-TYPE
    SYNTAX BITS { red(0), green(1), blue(2) }
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "Flags."
    ::= { testE2EMib 3 }

END
"""


def _compile_mib(mib_dir: Path, output_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "trishul_smi",
            "compile",
            "TEST-E2E-MIB",
            "--mib-dir",
            str(mib_dir),
            "-o",
            str(output_dir),
            "--cache-dir",
            "",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (output_dir / "TEST-E2E-MIB.json").exists()


def test_tsmi_compiled_bundle_renders_enum_bits_and_units(tmp_path: Path) -> None:
    mib_dir = tmp_path / "mibs"
    mib_dir.mkdir()
    (mib_dir / "TEST-E2E-MIB.mib").write_text(_TINY_MIB, encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    _compile_mib(mib_dir, output_dir)

    bundle = load_bundle(output_dir / "TEST-E2E-MIB.json")
    enriched = enrich_varbinds(
        bundle,
        (
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 1, 0), value=IntegerValue(1)),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 2, 0), value=IntegerValue(7)),
            VarBind(oid=(1, 3, 6, 1, 4, 1, 99999, 3, 0), value=OctetStringValue(b"\x80")),
        ),
    )

    assert enriched[0].display_name == "TEST-E2E-MIB::status.0"
    assert enriched[0].display_value == "up(1)"
    assert enriched[0].enum_label == "up"
    assert enriched[1].display_value == "7"
    assert enriched[1].units == "bits/second"
    assert enriched[2].display_value == "red(0)"
