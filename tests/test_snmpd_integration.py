"""Integration tests against a live net-snmp snmpd agent.

Every test in this module is marked ``@pytest.mark.snmpd`` and talks to a local
agent on 127.0.0.1:1161 (community ``public``, SNMPv2c) plus a second port
127.0.0.1:1162 carrying the SNMPv3 user ``tsnmpuser`` (authPriv
SHA-256/AES-256, RFC 7860). The module skips cleanly when no snmpd is
listening, so normal local and CI runs without snmpd stay green.
"""

from __future__ import annotations

import asyncio

import pytest

from trishul_snmp import ErrorStatus, V2cManager, V3Manager
from trishul_snmp.errors import TsnmpError
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmUser
from trishul_snmp.types import EndOfMibViewValue, TimeTicksValue

pytestmark = pytest.mark.snmpd

SNMPD_HOST = "127.0.0.1"
SNMPD_PORT = 1161
SNMPD_COMMUNITY = "public"
SNMPD_TIMEOUT = 0.5

# v3 user configured on the second agentaddress (see .github/workflows/ci.yml).
SNMPD_V3_PORT = 1162
SNMPD_V3_USERNAME = "tsnmpuser"
SNMPD_V3_AUTH_PASSPHRASE = "authpassword12345"
SNMPD_V3_PRIV_PASSPHRASE = "privpassword12345"

_SYSTEM_ROOT = (1, 3, 6, 1, 2, 1, 1)


def _open_manager() -> V2cManager:
    return V2cManager(
        host=SNMPD_HOST,
        port=SNMPD_PORT,
        community=SNMPD_COMMUNITY,
        timeout=SNMPD_TIMEOUT,
        retries=0,
    )


def _open_v3_manager() -> V3Manager:
    return V3Manager(
        host=SNMPD_HOST,
        port=SNMPD_V3_PORT,
        user=UsmUser(
            username=SNMPD_V3_USERNAME,
            auth_protocol=AuthProtocol.SHA256,
            auth_key=SNMPD_V3_AUTH_PASSPHRASE.encode(),
            priv_protocol=PrivProtocol.AES256,
            priv_key=SNMPD_V3_PRIV_PASSPHRASE.encode(),
        ),
        timeout=SNMPD_TIMEOUT,
        retries=0,
    )


def _snmpd_reachable() -> bool:
    async def probe() -> bool:
        try:
            async with _open_manager() as manager:
                await manager.get("1.3.6.1.2.1.1.3.0")
            return True
        except TsnmpError:
            return False

    return asyncio.run(probe())


def _snmpd_v3_reachable() -> bool:
    async def probe() -> bool:
        try:
            async with _open_v3_manager() as manager:
                await manager.get("1.3.6.1.2.1.1.3.0")
            return True
        except TsnmpError:
            return False

    return asyncio.run(probe())


@pytest.fixture(scope="module")
def snmpd_agent() -> None:
    if not _snmpd_reachable():
        pytest.skip(f"no snmpd agent reachable at {SNMPD_HOST}:{SNMPD_PORT}")


@pytest.fixture(scope="module")
def snmpd_v3_agent() -> None:
    if not _snmpd_v3_reachable():
        pytest.skip(
            f"no snmpd v3 agent (SHA-256/AES-256 {SNMPD_V3_USERNAME}) reachable at "
            f"{SNMPD_HOST}:{SNMPD_V3_PORT}"
        )


def test_snmpd_get(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_manager() as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())


def test_snmpd_getnext(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_manager() as manager:
            response = await manager.get_next(_SYSTEM_ROOT)

        assert response.error_status is ErrorStatus.NO_ERROR
        # GETNEXT from the system subtree must advance past the target without
        # reaching the end of the MIB view.
        assert response.varbinds[0].oid > _SYSTEM_ROOT
        assert not isinstance(response.varbinds[0].value, EndOfMibViewValue)

    asyncio.run(scenario())


def test_snmpd_getbulk(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_manager() as manager:
            response = await manager.get_bulk(
                _SYSTEM_ROOT,
                non_repeaters=0,
                max_repetitions=5,
            )

        assert response.error_status is ErrorStatus.NO_ERROR
        assert len(response.varbinds) == 5
        assert all(
            not isinstance(varbind.value, EndOfMibViewValue) for varbind in response.varbinds
        )

    asyncio.run(scenario())


def test_snmpd_walk(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_manager() as manager:
            walked = await manager.walk(_SYSTEM_ROOT, max_repetitions=10)

        assert len(walked) >= 5
        assert walked[0].oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)  # sysDescr.0
        oids = [varbind.oid for varbind in walked]
        assert all(oid[: len(_SYSTEM_ROOT)] == _SYSTEM_ROOT for oid in oids)
        assert oids == sorted(oids)

    asyncio.run(scenario())


def test_snmpd_v3_authpriv_sha256_aes256_get(snmpd_v3_agent: None) -> None:
    """A live v3 authPriv SHA-256/AES-256 GET is accepted by net-snmp.

    Regression for issue #28: SHA-2 auth tags (and the msgAuthenticationParameters
    field length) must be the RFC 7860 per-protocol length (24 octets for
    SHA-256, not 12) or standard agents reject the request with
    usmStatsWrongDigests.
    """

    async def scenario() -> None:
        async with _open_v3_manager() as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())
