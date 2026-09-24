"""Unit tests for the SNMPv3 receive-side replay and time-window guard."""

from __future__ import annotations

from trishul_snmp.notify.v3 import V3ReceiveVerdict, V3ReplayGuard

_ENGINE_ID = b"\x80\x00\x01\x02\x03" + b"\x44" * 12
_USER = "listener"
_SALT_A = b"\x01\x02\x03\x04\x05\x06\x07\x08"
_SALT_B = b"\x11\x12\x13\x14\x15\x16\x17\x18"
_SALT_C = b"\x21\x22\x23\x24\x25\x26\x27\x28"


class _FakeClock:
    def __init__(self, *, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _check(
    guard: V3ReplayGuard,
    *,
    boots: int,
    time: int,
    salt: bytes = b"",
) -> V3ReceiveVerdict:
    return guard.check(
        engine_id=_ENGINE_ID,
        engine_boots=boots,
        engine_time=time,
        username=_USER,
        salt=salt,
    )


def test_replay_guard_accepts_first_seen_engine() -> None:
    guard = V3ReplayGuard(clock=_FakeClock())

    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT


def test_replay_guard_rejects_engine_boots_going_backwards() -> None:
    guard = V3ReplayGuard(clock=_FakeClock())
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT

    assert _check(guard, boots=4, time=200) is V3ReceiveVerdict.ENGINE_BOOTS_REPLAY


def test_replay_guard_rejects_time_outside_window() -> None:
    clock = _FakeClock()
    guard = V3ReplayGuard(clock=clock)
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT

    clock.advance(1.0)
    assert _check(guard, boots=5, time=1100) is V3ReceiveVerdict.OUTSIDE_TIME_WINDOW


def test_replay_guard_accepts_time_advancing_with_monotonic_clock() -> None:
    clock = _FakeClock()
    guard = V3ReplayGuard(clock=clock)
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT

    clock.advance(1.0)
    assert _check(guard, boots=5, time=101) is V3ReceiveVerdict.ACCEPT
    assert _check(guard, boots=5, time=99) is V3ReceiveVerdict.ACCEPT


def test_replay_guard_accepts_higher_boots_as_reboot() -> None:
    clock = _FakeClock()
    guard = V3ReplayGuard(clock=clock)
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT

    clock.advance(2.0)
    assert _check(guard, boots=6, time=200) is V3ReceiveVerdict.ACCEPT

    # baseline is rebased to the reboot snapshot
    clock.advance(1.0)
    assert _check(guard, boots=6, time=201) is V3ReceiveVerdict.ACCEPT
    assert _check(guard, boots=5, time=999) is V3ReceiveVerdict.ENGINE_BOOTS_REPLAY


def test_replay_guard_rejects_duplicate_salt_for_same_boots_time() -> None:
    guard = V3ReplayGuard(clock=_FakeClock())
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT

    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.DUPLICATE_SALT


def test_replay_guard_accepts_distinct_salt_for_same_boots_time() -> None:
    guard = V3ReplayGuard(clock=_FakeClock())
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT

    assert _check(guard, boots=5, time=100, salt=_SALT_B) is V3ReceiveVerdict.ACCEPT


def test_replay_guard_accepts_same_salt_after_time_advances() -> None:
    clock = _FakeClock()
    guard = V3ReplayGuard(clock=clock)
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT

    clock.advance(1.0)
    assert _check(guard, boots=5, time=101, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT


def test_replay_guard_reboot_clears_salt_cache() -> None:
    guard = V3ReplayGuard(clock=_FakeClock(), salt_cache_size=2)
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT

    # a reboot may legitimately reuse a pre-reboot salt
    assert _check(guard, boots=6, time=200, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT

    # ... and the post-reboot salt is now protected against replay
    assert _check(guard, boots=6, time=200, salt=_SALT_A) is V3ReceiveVerdict.DUPLICATE_SALT


def test_replay_guard_ignores_empty_salt_for_unencrypted_messages() -> None:
    guard = V3ReplayGuard(clock=_FakeClock())
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT

    # no privacy salt to fingerprint, so an identical unencrypted datagram is
    # only bounded by the boots/time window check
    assert _check(guard, boots=5, time=100) is V3ReceiveVerdict.ACCEPT


def test_replay_guard_salt_cache_is_bounded() -> None:
    guard = V3ReplayGuard(clock=_FakeClock(), salt_cache_size=2)
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT
    assert _check(guard, boots=5, time=100, salt=_SALT_B) is V3ReceiveVerdict.ACCEPT

    # inserting a third salt evicts _SALT_A, which is then indistinguishable
    # from a fresh salt
    assert _check(guard, boots=5, time=100, salt=_SALT_C) is V3ReceiveVerdict.ACCEPT
    assert _check(guard, boots=5, time=100, salt=_SALT_A) is V3ReceiveVerdict.ACCEPT
