from __future__ import annotations

import pytest

from trishul_snmp.errors import UnknownSymbolError
from trishul_snmp.manager.operations import normalize_targets


def test_normalize_targets_requires_at_least_one_target() -> None:
    with pytest.raises(ValueError, match="At least one target is required"):
        normalize_targets((), bundle=None)


def test_normalize_targets_rejects_symbolic_target_without_bundle() -> None:
    with pytest.raises(UnknownSymbolError, match="Symbolic target requires a loaded bundle"):
        normalize_targets(("IF-MIB::ifDescr.1",), bundle=None)


def test_normalize_targets_accepts_numeric_oid_text_without_bundle() -> None:
    assert normalize_targets((" 1.3.6.1.2.1.1.3.0 ",), bundle=None) == (
        (1, 3, 6, 1, 2, 1, 1, 3, 0),
    )


def test_normalize_targets_rejects_unrecognized_text() -> None:
    with pytest.raises(UnknownSymbolError, match="Unrecognized target format: not-an-oid"):
        normalize_targets(("not-an-oid",), bundle=None)
