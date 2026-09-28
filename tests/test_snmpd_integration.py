"""Integration tests against a live net-snmp snmpd agent.

Every test in this module is marked ``@pytest.mark.snmpd``. The main agent
(configured by the CI job and local runs) listens on 127.0.0.1:1161 for
community ``public`` (SNMPv1 + SNMPv2c) and 127.0.0.1:1162 for the SNMPv3
users ``tsnmpuser`` (authPriv SHA-256/AES-256, RFC 7860), ``user224``
(SHA-224/AES-256), ``user384`` (SHA-384/AES-192), ``user512``
(SHA-512/AES-256) and ``userSha256Aes192`` (SHA-256/AES-192).

Two fixtures are self-contained (they do not need the main agent): a
second snmpd instance on 127.0.0.1:1171 that fires coldStart v1/v2c
traps and an inform at startup into a listener bound *before* the agent
starts, and a trishul ``V2cResponder`` driven by the real net-snmp client
tools (``snmpget``/``snmpwalk``). Two further self-contained agents cover
config-driven device/agent-stack variance (issue #26): a VACM-restricted
agent on 127.0.0.1:1173 (a ``view`` bound to both a community and a v3
user) and a v3-only agent on 127.0.0.1:1174 (no ``rocommunity`` at all).
The module skips cleanly when the pieces it needs are absent, so normal
local and CI runs without snmpd stay green.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from collections.abc import Callable, Generator, Sequence
from pathlib import Path

import pytest

from trishul_snmp import ErrorStatus, V1Manager, V2cManager, V2cResponder, V3Manager
from trishul_snmp.errors import RequestTimeoutError, TsnmpError
from trishul_snmp.notify.events import NotificationEvent
from trishul_snmp.notify.listener import V2cNotificationListener
from trishul_snmp.security.usm import AuthProtocol, PrivProtocol, UsmUser
from trishul_snmp.types import (
    EndOfMibViewValue,
    IntegerValue,
    NoSuchObjectValue,
    OctetStringValue,
    TimeTicksValue,
)

pytestmark = pytest.mark.snmpd

SNMPD_HOST = "127.0.0.1"
SNMPD_PORT = 1161
SNMPD_COMMUNITY = "public"
SNMPD_TIMEOUT = 0.5

# v3 users configured on the second agentaddress (see .github/workflows/ci.yml).
SNMPD_V3_PORT = 1162
SNMPD_V3_USERNAME = "tsnmpuser"
SNMPD_V3_AUTH_PASSPHRASE = "authpassword12345"
SNMPD_V3_PRIV_PASSPHRASE = "privpassword12345"

# SNMPv3 auth/priv matrix against the real agent, one GET per combo.
# The AES-192/256 users cover every auth-digest/cipher-key-length mismatch
# net-snmp's default Blumenthal derivation (draft-blumenthal-aes-usm-04)
# exercises: extension (SHA-224 → AES-256) and truncation (SHA-384/512 →
# AES-192/256), plus SHA-256 → AES-192 (issue #30).  net-snmp 5.9 builds
# have no 3DES privacy at all, so 3DES-EDE stays unit-only.
SNMPD_V3_MATRIX = (
    ("user224", AuthProtocol.SHA224, PrivProtocol.AES256),
    ("user384", AuthProtocol.SHA384, PrivProtocol.AES192),
    ("user512", AuthProtocol.SHA512, PrivProtocol.AES256),
    ("userSha256Aes192", AuthProtocol.SHA256, PrivProtocol.AES192),
)

# Dedicated agent for the notification fixtures (coldStart traps + inform) —
# it binds an ephemeral port; only its traps matter.
_COLDSTART_OID = (1, 3, 6, 1, 6, 3, 1, 1, 5, 1)

_SYSTEM_ROOT = (1, 3, 6, 1, 2, 1, 1)


def _open_v1_manager(*, port: int = SNMPD_PORT) -> V1Manager:
    return V1Manager(
        host=SNMPD_HOST,
        port=port,
        community=SNMPD_COMMUNITY,
        timeout=SNMPD_TIMEOUT,
        retries=0,
    )


def _open_v2c_manager(*, port: int = SNMPD_PORT) -> V2cManager:
    return V2cManager(
        host=SNMPD_HOST,
        port=port,
        community=SNMPD_COMMUNITY,
        timeout=SNMPD_TIMEOUT,
        retries=0,
    )


def _open_v3_manager(
    *,
    port: int = SNMPD_V3_PORT,
    username: str = SNMPD_V3_USERNAME,
    auth: AuthProtocol = AuthProtocol.SHA256,
    priv: PrivProtocol = PrivProtocol.AES256,
) -> V3Manager:
    return V3Manager(
        host=SNMPD_HOST,
        port=port,
        user=UsmUser(
            username=username,
            auth_protocol=auth,
            auth_key=SNMPD_V3_AUTH_PASSPHRASE.encode(),
            priv_protocol=priv,
            priv_key=SNMPD_V3_PRIV_PASSPHRASE.encode(),
        ),
        timeout=SNMPD_TIMEOUT,
        retries=0,
    )


def _v3_users() -> tuple[tuple[str, AuthProtocol, PrivProtocol], ...]:
    return (
        (SNMPD_V3_USERNAME, AuthProtocol.SHA256, PrivProtocol.AES256),
        *SNMPD_V3_MATRIX,
    )


def _snmpd_reachable() -> bool:
    async def probe() -> bool:
        try:
            async with _open_v2c_manager() as manager:
                await manager.get("1.3.6.1.2.1.1.3.0")
            return True
        except TsnmpError:
            return False

    return asyncio.run(probe())


def _v3_user_reachable(*, username: str, auth: AuthProtocol, priv: PrivProtocol) -> bool:
    async def probe() -> bool:
        try:
            async with _open_v3_manager(username=username, auth=auth, priv=priv) as manager:
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
def snmpd_v3_agent(snmpd_agent: None) -> None:
    """Every configured v3 user must be reachable once the main agent is up.

    The agent's liveness is covered by ``snmpd_agent`` (skip when absent); a
    missing v3 user here is a config/regression failure and must fail, not
    silently skip — otherwise the RFC 7860 wire coverage would degrade.
    """
    unreachable = [
        username
        for username, auth, priv in _v3_users()
        if not _v3_user_reachable(username=username, auth=auth, priv=priv)
    ]
    if unreachable:
        pytest.fail(
            f"snmpd v3 users unreachable on {SNMPD_HOST}:{SNMPD_V3_PORT}: {sorted(unreachable)}"
        )


# ── SNMPv1 against the real agent ─────────────────────────────────────────────


def test_snmpd_v1_get(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v1_manager() as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())


def test_snmpd_v1_getnext(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v1_manager() as manager:
            response = await manager.get_next(_SYSTEM_ROOT)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid > _SYSTEM_ROOT
        assert not isinstance(response.varbinds[0].value, EndOfMibViewValue)

    asyncio.run(scenario())


def test_snmpd_v1_walk(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v1_manager() as manager:
            walked = await manager.walk(_SYSTEM_ROOT, max_repetitions=10)

        assert len(walked) >= 5
        assert walked[0].oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)  # sysDescr.0
        oids = [varbind.oid for varbind in walked]
        assert all(oid[: len(_SYSTEM_ROOT)] == _SYSTEM_ROOT for oid in oids)
        assert oids == sorted(oids)

    asyncio.run(scenario())


def test_snmpd_v1_getbulk_downgrades_to_getnext(snmpd_agent: None) -> None:
    """SNMPv1 has no GETBULK, so V1Manager.get_bulk must loop GETNEXT.

    The combined result must be the lexicographically correct prefix of the
    GETNEXT walk for the same subtree.
    """

    async def scenario() -> None:
        async with _open_v1_manager() as manager:
            walked = await manager.walk(_SYSTEM_ROOT, max_repetitions=10)
            bulk = await manager.get_bulk(_SYSTEM_ROOT, non_repeaters=0, max_repetitions=10)

        assert bulk.error_status is ErrorStatus.NO_ERROR
        assert len(bulk.varbinds) == 10
        bulk_oids = [varbind.oid for varbind in bulk.varbinds]
        walk_oids = [varbind.oid for varbind in walked]
        assert bulk_oids == walk_oids[: len(bulk_oids)]
        assert bulk_oids == sorted(bulk_oids)
        assert all(not isinstance(varbind.value, EndOfMibViewValue) for varbind in bulk.varbinds)

    asyncio.run(scenario())


# ── SNMPv2c against the real agent ────────────────────────────────────────────


def test_snmpd_get(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v2c_manager() as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == (1, 3, 6, 1, 2, 1, 1, 3, 0)
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())


def test_snmpd_getnext(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v2c_manager() as manager:
            response = await manager.get_next(_SYSTEM_ROOT)

        assert response.error_status is ErrorStatus.NO_ERROR
        # GETNEXT from the system subtree must advance past the target without
        # reaching the end of the MIB view.
        assert response.varbinds[0].oid > _SYSTEM_ROOT
        assert not isinstance(response.varbinds[0].value, EndOfMibViewValue)

    asyncio.run(scenario())


def test_snmpd_getbulk(snmpd_agent: None) -> None:
    async def scenario() -> None:
        async with _open_v2c_manager() as manager:
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
        async with _open_v2c_manager() as manager:
            walked = await manager.walk(_SYSTEM_ROOT, max_repetitions=10)

        assert len(walked) >= 5
        assert walked[0].oid == (1, 3, 6, 1, 2, 1, 1, 1, 0)  # sysDescr.0
        oids = [varbind.oid for varbind in walked]
        assert all(oid[: len(_SYSTEM_ROOT)] == _SYSTEM_ROOT for oid in oids)
        assert oids == sorted(oids)

    asyncio.run(scenario())


# ── SNMPv3 crypto matrix against the real agent ───────────────────────────────


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


@pytest.mark.parametrize(
    ("username", "auth_protocol", "priv_protocol"),
    SNMPD_V3_MATRIX,
    ids=[username for username, _auth, _priv in SNMPD_V3_MATRIX],
)
def test_snmpd_v3_matrix_get(
    snmpd_v3_agent: None,
    username: str,
    auth_protocol: AuthProtocol,
    priv_protocol: PrivProtocol,
) -> None:
    """One live GET per SHA-2 auth protocol against the real agent."""

    async def scenario() -> None:
        async with _open_v3_manager(
            username=username, auth=auth_protocol, priv=priv_protocol
        ) as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())


# ── Notifications from the real agent ────────────────────────────────────────


async def _collect_coldstart_events(
    listener: V2cNotificationListener,
) -> dict[str, NotificationEvent]:
    """Collect the v1 trap, v2c trap and inform fired by the agent's coldStart."""
    events: dict[str, NotificationEvent] = {}
    for _ in range(3):
        event = await asyncio.wait_for(listener.receive(), timeout=5.0)
        events[event.pdu_type] = event
    expected = {"trap", "snmpv2-trap", "inform-request"}
    if set(events) != expected:
        raise AssertionError(
            f"expected coldStart notifications {sorted(expected)}, got {sorted(events)}"
        )
    return events


@pytest.fixture(scope="module")
def snmpd_coldstart_notifications(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, NotificationEvent]:
    """Start a dedicated snmpd whose coldStart fires into a bound listener.

    The listener binds *before* the agent starts, so the one-shot coldStart
    v1 trap, v2c trap and inform are all captured. The listener auto-ACKs
    the inform (SnmpNotificationListener._send_inform_ack); snmpd would
    otherwise retry it.
    """
    if shutil.which("snmpd") is None:
        pytest.skip("snmpd binary not installed")
    config_dir = tmp_path_factory.mktemp("snmpd-notifications")
    config_path = config_dir / "snmpd.conf"
    log_path = config_dir / "snmpd.log"

    async def capture() -> dict[str, NotificationEvent]:
        async with V2cNotificationListener(
            host=SNMPD_HOST,
            port=0,
            communities=[SNMPD_COMMUNITY],
        ) as listener:
            local = listener.local_address
            assert local is not None
            sink_port = local[1]
            config_path.write_text(
                f"rocommunity {SNMPD_COMMUNITY} 127.0.0.1\n"
                "agentaddress 127.0.0.1:0\n"  # ephemeral agent port — only the traps matter
                "engineID tsnmpv3notifyengine\n"
                f"trapsink 127.0.0.1:{sink_port} {SNMPD_COMMUNITY}\n"
                f"trap2sink 127.0.0.1:{sink_port} {SNMPD_COMMUNITY}\n"
                f"informsink 127.0.0.1:{sink_port} {SNMPD_COMMUNITY}\n"
            )
            proc = await asyncio.create_subprocess_exec(
                shutil.which("snmpd") or "snmpd",
                "-C",
                "-f",
                "-c",
                str(config_path),
                "-Lf",
                str(log_path),
            )
            try:
                return await _collect_coldstart_events(listener)
            finally:
                if proc.returncode is None:
                    proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)

    return asyncio.run(capture())


def test_snmpd_v1_coldstart_trap_received(
    snmpd_coldstart_notifications: dict[str, NotificationEvent],
) -> None:
    """The agent's coldStart v1 Trap-PDU carries the RFC 1157 metadata."""
    event = snmpd_coldstart_notifications["trap"]

    assert event.pdu_type == "trap"
    assert event.community == SNMPD_COMMUNITY
    assert event.source_host == SNMPD_HOST
    assert event.generic_trap == 0  # coldStart
    assert event.enterprise is not None
    assert event.agent_addr is not None
    assert event.timestamp is not None  # v1 Trap-PDU sysUpTime field


def test_snmpd_v2c_coldstart_trap_received(
    snmpd_coldstart_notifications: dict[str, NotificationEvent],
) -> None:
    event = snmpd_coldstart_notifications["snmpv2-trap"]

    assert event.pdu_type == "snmpv2-trap"
    assert event.community == SNMPD_COMMUNITY
    assert event.notification_oid == _COLDSTART_OID
    assert event.uptime is not None


def test_snmpd_inform_received_and_acked(
    snmpd_coldstart_notifications: dict[str, NotificationEvent],
) -> None:
    """The listener auto-ACKs informs; the event surfacing is the proof.

    If the ACK were not sent, snmpd would retry the inform and a plain
    ``snmpv2-trap`` style flow would not complete. Receiving the inform
    event means the inform path (request + ACK) ran to completion.
    """
    event = snmpd_coldstart_notifications["inform-request"]

    assert event.pdu_type == "inform-request"
    assert event.is_inform is True
    assert event.community == SNMPD_COMMUNITY
    assert event.notification_oid == _COLDSTART_OID
    assert event.uptime is not None


# ── Responder inverse direction (real net-snmp clients → trishul responder) ───


_RESPONDER_OBJECTS = (
    ("1.3.6.1.2.1.1.1.0", OctetStringValue(b"trishul-responder integration agent")),
    ("1.3.6.1.2.1.1.3.0", TimeTicksValue(123456)),
    ("1.3.6.1.2.1.2.2.1.1.1", IntegerValue(1)),
    ("1.3.6.1.2.1.2.2.1.1.2", IntegerValue(2)),
    ("1.3.6.1.2.1.2.2.1.2.1", OctetStringValue(b"eth0")),
    ("1.3.6.1.2.1.2.2.1.2.2", OctetStringValue(b"eth1")),
)


@pytest.fixture(scope="module")
def net_snmp_cli_available() -> None:
    if shutil.which("snmpget") is None or shutil.which("snmpwalk") is None:
        pytest.skip("net-snmp client tools (snmpget/snmpwalk) not installed")


async def _run_net_snmp(*args: str) -> tuple[int, bytes]:
    """Run a net-snmp client and return (exit_code, combined output)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    return proc.returncode or 0, out


def _cli_target(port: int) -> str:
    return f"{SNMPD_HOST}:{port}"


def test_responder_real_snmpget(net_snmp_cli_available: None) -> None:
    """A real net-snmp snmpget reads objects served by the trishul responder."""

    async def scenario() -> None:
        async with V2cResponder(
            host=SNMPD_HOST,
            port=0,
            communities=[SNMPD_COMMUNITY],
            objects=_RESPONDER_OBJECTS,
        ) as responder:
            local = responder.local_address
            assert local is not None
            serve_task = asyncio.create_task(responder.serve(count=0))
            code_descr, out_descr = await _run_net_snmp(
                "snmpget",
                "-v2c",
                "-c",
                SNMPD_COMMUNITY,
                "-On",
                "-t",
                "1",
                "-r",
                "0",
                _cli_target(local[1]),
                "1.3.6.1.2.1.1.1.0",
            )
            code_uptime, out_uptime = await _run_net_snmp(
                "snmpget",
                "-v2c",
                "-c",
                SNMPD_COMMUNITY,
                "-On",
                "-t",
                "1",
                "-r",
                "0",
                _cli_target(local[1]),
                "1.3.6.1.2.1.1.3.0",
            )
            await responder.close()
            await serve_task

        assert code_descr == 0
        assert b"trishul-responder integration agent" in out_descr
        assert code_uptime == 0
        assert b"Timeticks: (123456)" in out_uptime

    asyncio.run(scenario())


def test_responder_real_snmpwalk(net_snmp_cli_available: None) -> None:
    """A real net-snmp snmpwalk walks the responder's subtree via GETNEXT."""

    async def scenario() -> None:
        async with V2cResponder(
            host=SNMPD_HOST,
            port=0,
            communities=[SNMPD_COMMUNITY],
            objects=_RESPONDER_OBJECTS,
        ) as responder:
            local = responder.local_address
            assert local is not None
            serve_task = asyncio.create_task(responder.serve(count=0))
            code, out = await _run_net_snmp(
                "snmpwalk",
                "-v2c",
                "-c",
                SNMPD_COMMUNITY,
                "-On",
                "-t",
                "1",
                "-r",
                "0",
                _cli_target(local[1]),
                "1.3.6.1.2.1.2.2.1.1",
            )
            await responder.close()
            await serve_task

        assert code == 0
        assert b".1.3.6.1.2.1.2.2.1.1.1 = INTEGER: 1" in out
        assert b".1.3.6.1.2.1.2.2.1.1.2 = INTEGER: 2" in out

    asyncio.run(scenario())


def test_responder_real_snmpget_missing_oid(net_snmp_cli_available: None) -> None:
    """A GET for an absent OID surfaces noSuchObject to a real net-snmp client."""

    async def scenario() -> None:
        async with V2cResponder(
            host=SNMPD_HOST,
            port=0,
            communities=[SNMPD_COMMUNITY],
            objects=_RESPONDER_OBJECTS,
        ) as responder:
            local = responder.local_address
            assert local is not None
            serve_task = asyncio.create_task(responder.serve(count=0))
            code, out = await _run_net_snmp(
                "snmpget",
                "-v2c",
                "-c",
                SNMPD_COMMUNITY,
                "-On",
                "-t",
                "1",
                "-r",
                "0",
                _cli_target(local[1]),
                "1.3.6.1.2.1.1.1.99",
            )
            await responder.close()
            await serve_task

        assert code == 0
        assert b"No Such Object" in out

    asyncio.run(scenario())


# ── Restricted VACM views (dedicated agent) ──────────────────────────────────
#
# Version variance (net-snmp 5.8.x) — assessed, deliberately NOT added:
# issue #26 asked for a bounded assessment of a 5.8.x lane. Empirically
# (net-snmp v5.8 from the upstream GitHub tag: configure --with-defaults +
# make -j2 in ~1.5 min, then the built snmpd running the configs below):
#   * the 5.8 build only compiles against OpenSSL 3 with heavy deprecation
#     warnings, and the only upstream 5.8.1 tags are rc1/pre2 — no clean
#     release tag — so building in CI is a genuine flakiness surface;
#   * every outcome this suite pins is IDENTICAL on 5.8 and the 5.9.4 that
#     apt provides on CI/local: in-view GETs succeed, out-of-view GETs are
#     noSuchObject (v2c/v3) / noSuchName (v1), and unauthorized-community
#     requests are silently dropped.
# A 5.8.x CI lane would add configure+build time and flakiness risk for zero
# behavioral divergence to catch, so it is not added; the variance window
# covered here is 5.9.x.
#
# The restricted agent uses the explicit com2sec/group/access VACM route
# rather than the documented ``rocommunity public -V view`` shorthand: this
# 5.9.4 build rejects the ``-V`` option token at parse time (it is treated
# as a source hostname), so the long form is the only reliable spelling.
_SNMPD_VIEW_PORT = 1173
_SNMPD_VIEW_USERNAME = "v3view"

_VIEW_INSIDE_OID = (1, 3, 6, 1, 2, 1, 1, 1, 0)  # sysDescr.0 — inside the view
_VIEW_OUTSIDE_OID = (1, 3, 6, 1, 2, 1, 2, 2, 1, 1, 1)  # ifIndex.1 — outside

# engineID "restrictedVACM" pins the authoritative engine to the same
# format-4 value the createUser -e keys are localized against (like the main
# agent in ci.yml); without it the agent has no matching v3 user.
_SNMPD_VIEW_CONFIG = (
    f"agentaddress {SNMPD_HOST}:{_SNMPD_VIEW_PORT}\n"
    "engineID restrictedVACM\n"
    "view restricted included 1.3.6.1.2.1.1\n"
    "com2sec restsec 127.0.0.1 public\n"
    "group restgroup v1 restsec\n"
    "group restgroup v2c restsec\n"
    "group restgroup usm v3view\n"
    'access restgroup "" any noauth exact restricted none none\n'
    "createUser -e 0x80001f8804726573747269637465645641434d "
    f"{_SNMPD_VIEW_USERNAME} SHA-256 "
    f'"{SNMPD_V3_AUTH_PASSPHRASE}" AES-128 "{SNMPD_V3_PRIV_PASSPHRASE}"\n'
)

# ── v3-only agent (dedicated, no community at all) ───────────────────────────

_SNMPD_V3ONLY_PORT = 1174
_SNMPD_V3ONLY_USERNAME = "v3only"

_SNMPD_V3ONLY_CONFIG = (
    f"agentaddress {SNMPD_HOST}:{_SNMPD_V3ONLY_PORT}\n"
    "engineID v3onlyengine\n"
    "createUser -e 0x80001f880476336f6e6c79656e67696e65 "
    f"{_SNMPD_V3ONLY_USERNAME} SHA-256 "
    f'"{SNMPD_V3_AUTH_PASSPHRASE}" AES-128 "{SNMPD_V3_PRIV_PASSPHRASE}"\n'
    "rouser v3only\n"
)


def _start_snmpd_agent(
    config_text: str,
    *,
    config_path: Path,
    log_path: Path,
    pid_path: Path,
) -> subprocess.Popen[bytes]:
    """Start a foreground (-f) snmpd with a self-contained config."""
    config_path.write_text(config_text)
    return subprocess.Popen(
        [
            shutil.which("snmpd") or "snmpd",
            "-C",
            "-f",
            "-c",
            str(config_path),
            "-p",
            str(pid_path),
            "-Lf",
            str(log_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_agent(proc: subprocess.Popen[bytes]) -> None:
    """Terminate a foreground agent and reap it — no orphans."""
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)


def _wait_for_agent(
    proc: subprocess.Popen[bytes],
    probe: Callable[[], bool],
    *,
    what: str,
    log_path: Path,
    deadline: float = 12.0,
) -> None:
    """Poll *probe* until it succeeds, or fail hard with agent diagnostics.

    A self-contained agent that never becomes responsive is a fixture/config
    regression and must fail loudly rather than silently skip coverage.
    """
    waited_until = time.monotonic() + deadline
    while time.monotonic() < waited_until:
        if proc.poll() is not None:
            break
        if probe():
            return
        time.sleep(0.2)
    tail = ""
    if log_path.exists():
        tail = "\n".join(log_path.read_text().splitlines()[-15:])
    raise AssertionError(
        f"snmpd agent [{what}] never became responsive (exit={proc.poll()!r}); log tail:\n{tail}"
    )


def _probe_v2c_get(port: int, target: str | Sequence[int]) -> bool:
    async def probe() -> bool:
        try:
            async with _open_v2c_manager(port=port) as manager:
                await manager.get(target)
            return True
        except TsnmpError:
            return False

    return asyncio.run(probe())


def _probe_v3_get(
    port: int,
    *,
    username: str,
    auth: AuthProtocol,
    priv: PrivProtocol,
) -> bool:
    async def probe() -> bool:
        try:
            async with _open_v3_manager(
                port=port, username=username, auth=auth, priv=priv
            ) as manager:
                await manager.get("1.3.6.1.2.1.1.3.0")
            return True
        except TsnmpError:
            return False

    return asyncio.run(probe())


@pytest.fixture(scope="module")
def snmpd_view_agent(tmp_path_factory: pytest.TempPathFactory) -> Generator[None, None, None]:
    """A dedicated snmpd whose VACM view exposes only the system subtree.

    Self-contained: owns its config, agent process and cleanup. Skips only
    when the snmpd binary is absent; a config regression (agent up but the
    view semantics wrong) fails hard here instead of degrading into skips.
    """
    if shutil.which("snmpd") is None:
        pytest.skip("snmpd binary not installed")
    config_dir = tmp_path_factory.mktemp("snmpd-view")
    config_path = config_dir / "snmpd.conf"
    log_path = config_dir / "snmpd.log"
    pid_path = config_dir / "snmpd.pid"
    proc = _start_snmpd_agent(
        _SNMPD_VIEW_CONFIG,
        config_path=config_path,
        log_path=log_path,
        pid_path=pid_path,
    )
    try:
        _wait_for_agent(
            proc,
            lambda: _probe_v2c_get(_SNMPD_VIEW_PORT, _VIEW_INSIDE_OID),
            what="restricted view agent",
            log_path=log_path,
        )

        async def verify_view() -> None:
            async with _open_v2c_manager(port=_SNMPD_VIEW_PORT) as manager:
                inside = await manager.get(_VIEW_INSIDE_OID)
                outside = await manager.get(_VIEW_OUTSIDE_OID)
            if inside.error_status is not ErrorStatus.NO_ERROR or isinstance(
                inside.varbinds[0].value, (NoSuchObjectValue, EndOfMibViewValue)
            ):
                raise AssertionError(
                    f"restricted view agent did not serve inside-view OID "
                    f"{inside.varbinds[0].oid_str}"
                )
            if outside.error_status is not ErrorStatus.NO_ERROR or not isinstance(
                outside.varbinds[0].value, NoSuchObjectValue
            ):
                raise AssertionError(
                    f"restricted view agent did not restrict outside-view OID "
                    f"{outside.varbinds[0].oid_str}"
                )

        # The view must already be in effect before the per-version tests run:
        # a broken view directive would otherwise surface as confusing failures.
        asyncio.run(verify_view())
        yield
    finally:
        _stop_agent(proc)


def test_snmpd_view_v2c_get_inside(snmpd_view_agent: None) -> None:
    """A v2c GET inside the restricted view succeeds with a real value."""

    async def scenario() -> None:
        async with _open_v2c_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get(_VIEW_INSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == _VIEW_INSIDE_OID
        assert isinstance(response.varbinds[0].value, OctetStringValue)

    asyncio.run(scenario())


def test_snmpd_view_v2c_get_outside_no_such_object(snmpd_view_agent: None) -> None:
    """A v2c GET outside the view answers noSuchObject, not an error-status PDU.

    net-snmp 5.9.4 surfaces a VACM miss in v2c as a noSuchObject exception
    in the varbind at the requested OID; tsnmp must present that as
    NO_ERROR + NoSuchObjectValue — value-or-error semantics, not a timeout.
    """

    async def scenario() -> None:
        async with _open_v2c_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get(_VIEW_OUTSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.error_index == 0
        assert response.varbinds[0].oid == _VIEW_OUTSIDE_OID
        assert isinstance(response.varbinds[0].value, NoSuchObjectValue)

    asyncio.run(scenario())


def test_snmpd_view_v2c_getnext_outside_end_of_mib_view(snmpd_view_agent: None) -> None:
    """A v2c GETNEXT past the view boundary answers endOfMibView."""

    async def scenario() -> None:
        async with _open_v2c_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get_next(_VIEW_OUTSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert response.varbinds[0].oid == _VIEW_OUTSIDE_OID
        assert isinstance(response.varbinds[0].value, EndOfMibViewValue)

    asyncio.run(scenario())


def test_snmpd_view_v1_get_inside(snmpd_view_agent: None) -> None:
    """An SNMPv1 GET inside the restricted view succeeds."""

    async def scenario() -> None:
        async with _open_v1_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get(_VIEW_INSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert isinstance(response.varbinds[0].value, OctetStringValue)

    asyncio.run(scenario())


def test_snmpd_view_v1_get_outside_no_such_name(snmpd_view_agent: None) -> None:
    """An SNMPv1 GET outside the view answers error-status noSuchName.

    SNMPv1 has no exception values, so the agent reports the miss as
    noSuchName with error_index 1; tsnmp surfaces the error-status verbatim
    (still value-or-error, never a timeout).
    """

    async def scenario() -> None:
        async with _open_v1_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get(_VIEW_OUTSIDE_OID)

        assert response.error_status is ErrorStatus.NO_SUCH_NAME
        assert response.error_index == 1
        assert response.varbinds[0].oid == _VIEW_OUTSIDE_OID

    asyncio.run(scenario())


def test_snmpd_view_v1_getnext_outside_no_such_name(snmpd_view_agent: None) -> None:
    """An SNMPv1 GETNEXT past the view boundary also answers noSuchName."""

    async def scenario() -> None:
        async with _open_v1_manager(port=_SNMPD_VIEW_PORT) as manager:
            response = await manager.get_next(_VIEW_OUTSIDE_OID)

        assert response.error_status is ErrorStatus.NO_SUCH_NAME
        assert response.error_index == 1

    asyncio.run(scenario())


def test_snmpd_view_v3_get_inside(snmpd_view_agent: None) -> None:
    """The v3 user bound to the same view still serves in-view GETs."""

    async def scenario() -> None:
        async with _open_v3_manager(
            port=_SNMPD_VIEW_PORT,
            username=_SNMPD_VIEW_USERNAME,
            auth=AuthProtocol.SHA256,
            priv=PrivProtocol.AES128,
        ) as manager:
            response = await manager.get(_VIEW_INSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert isinstance(response.varbinds[0].value, OctetStringValue)

    asyncio.run(scenario())


def test_snmpd_view_v3_get_outside_no_such_object(snmpd_view_agent: None) -> None:
    """The v3 user outside the view gets the same noSuchObject as v2c."""

    async def scenario() -> None:
        async with _open_v3_manager(
            port=_SNMPD_VIEW_PORT,
            username=_SNMPD_VIEW_USERNAME,
            auth=AuthProtocol.SHA256,
            priv=PrivProtocol.AES128,
        ) as manager:
            response = await manager.get(_VIEW_OUTSIDE_OID)

        assert response.error_status is ErrorStatus.NO_ERROR
        assert isinstance(response.varbinds[0].value, NoSuchObjectValue)

    asyncio.run(scenario())


def test_snmpd_view_walk_stops_at_view_boundary(snmpd_view_agent: None) -> None:
    """A v2c walk rooted above the view is truncated to the visible subtree.

    GETBULK from mib-2 returns only the system subtree; the agent ends the
    walk with endOfMibView and tsnmp's walk machinery terminates cleanly
    instead of looping or erroring.
    """

    async def scenario() -> None:
        async with _open_v2c_manager(port=_SNMPD_VIEW_PORT) as manager:
            walked = await manager.walk((1, 3, 6, 1, 2, 1))

        assert walked
        assert walked[0].oid == _VIEW_INSIDE_OID  # sysDescr.0
        assert all(varbind.oid[: len(_SYSTEM_ROOT)] == _SYSTEM_ROOT for varbind in walked)

    asyncio.run(scenario())


@pytest.fixture(scope="module")
def snmpd_v3only_agent(tmp_path_factory: pytest.TempPathFactory) -> Generator[None, None, None]:
    """A dedicated snmpd configured with no community at all (v3 only).

    The reachability probe must use v3 — v2c is exactly what must not work.
    Skips only when the snmpd binary is absent.
    """
    if shutil.which("snmpd") is None:
        pytest.skip("snmpd binary not installed")
    config_dir = tmp_path_factory.mktemp("snmpd-v3only")
    config_path = config_dir / "snmpd.conf"
    log_path = config_dir / "snmpd.log"
    pid_path = config_dir / "snmpd.pid"
    proc = _start_snmpd_agent(
        _SNMPD_V3ONLY_CONFIG,
        config_path=config_path,
        log_path=log_path,
        pid_path=pid_path,
    )
    try:
        _wait_for_agent(
            proc,
            lambda: _probe_v3_get(
                _SNMPD_V3ONLY_PORT,
                username=_SNMPD_V3ONLY_USERNAME,
                auth=AuthProtocol.SHA256,
                priv=PrivProtocol.AES128,
            ),
            what="v3-only agent",
            log_path=log_path,
        )
        yield
    finally:
        _stop_agent(proc)


def test_snmpd_v3only_v2c_request_times_out(snmpd_v3only_agent: None) -> None:
    """net-snmp silently drops unauthorized community requests.

    A v2c GET against a v3-only agent gets no response at all, so tsnmp
    must surface a clean RequestTimeoutError — not a protocol error, not a
    spurious value, and not an error-status PDU.
    """

    async def scenario() -> None:
        async with _open_v2c_manager(port=_SNMPD_V3ONLY_PORT) as manager:
            with pytest.raises(RequestTimeoutError):
                await manager.get("1.3.6.1.2.1.1.3.0")

    asyncio.run(scenario())


def test_snmpd_v3only_v1_request_times_out(snmpd_v3only_agent: None) -> None:
    """The same silent drop applies to SNMPv1 community requests."""

    async def scenario() -> None:
        async with _open_v1_manager(port=_SNMPD_V3ONLY_PORT) as manager:
            with pytest.raises(RequestTimeoutError):
                await manager.get("1.3.6.1.2.1.1.3.0")

    asyncio.run(scenario())


def test_snmpd_v3only_v3_still_works(snmpd_v3only_agent: None) -> None:
    """The v3-only agent still serves v3: the drop is community-scoped.

    Proves the agent is alive and the previous timeouts are the intended
    community-drop behavior rather than a dead or misconfigured agent.
    """

    async def scenario() -> None:
        async with _open_v3_manager(
            port=_SNMPD_V3ONLY_PORT,
            username=_SNMPD_V3ONLY_USERNAME,
            auth=AuthProtocol.SHA256,
            priv=PrivProtocol.AES128,
        ) as manager:
            response = await manager.get("1.3.6.1.2.1.1.3.0")

        assert response.error_status is ErrorStatus.NO_ERROR
        assert isinstance(response.varbinds[0].value, TimeTicksValue)

    asyncio.run(scenario())
