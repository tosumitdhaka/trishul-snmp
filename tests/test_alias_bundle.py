from __future__ import annotations

from pathlib import Path

from tests._bundle_fixtures import write_scalar_instance_alias_bundle
from trishul_snmp import TimeTicksValue, VarBind, load_bundle
from trishul_snmp.mib.render import enrich_varbinds


def test_alias_bundle_keeps_exact_lookup_semantics(tmp_path: Path) -> None:
    bundle = load_bundle(write_scalar_instance_alias_bundle(tmp_path))

    scalar = bundle.lookup("1.3.6.1.2.1.1.3")
    exact_instance = bundle.lookup("1.3.6.1.2.1.1.3.0")

    assert scalar.symbolic == "SNMPv2-MIB::sysUpTime"
    assert scalar.object_type == "OBJECT-TYPE"
    assert exact_instance.symbolic == "DISMAN-EXPRESSION-MIB::sysUpTimeInstance"
    assert exact_instance.object_type == "OBJECT IDENTIFIER"
    assert bundle.translate("SNMPv2-MIB::sysUpTime.0") == "1.3.6.1.2.1.1.3.0"
    assert bundle.translate("1.3.6.1.2.1.1.3.0") == "SNMPv2-MIB::sysUpTime.0"


def test_alias_bundle_prefers_parent_scalar_for_display_name(tmp_path: Path) -> None:
    bundle = load_bundle(write_scalar_instance_alias_bundle(tmp_path))
    varbinds = (
        VarBind(
            oid=(1, 3, 6, 1, 2, 1, 1, 3, 0),
            value=TimeTicksValue(123),
        ),
    )

    enriched = enrich_varbinds(bundle, varbinds)

    assert enriched[0].display_name == "SNMPv2-MIB::sysUpTime.0"
    assert enriched[0].display_value == "123"
