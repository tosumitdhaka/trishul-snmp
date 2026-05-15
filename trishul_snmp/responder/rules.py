"""Simulation rules for dynamic responder values."""

from __future__ import annotations

import random
import time
from typing import Protocol, runtime_checkable

from trishul_snmp.types import (
    Counter32Value,
    Gauge32Value,
    IntegerValue,
    SnmpValueType,
    TimeTicksValue,
)


class _IntConstructible(Protocol):
    def __call__(self, value: int, /) -> SnmpValueType: ...


@runtime_checkable
class SimulationRule(Protocol):
    """Protocol for dynamic OID value simulation rules."""

    def get_value(self) -> SnmpValueType:
        """Return the current simulated value."""
        ...


class CounterRule:
    """Monotonically increasing counter, incremented on each read."""

    def __init__(
        self,
        *,
        start: int = 0,
        increment: int = 1,
        value_type: _IntConstructible = Counter32Value,
    ) -> None:
        self._current = start
        self._increment = increment
        self._value_type = value_type

    def get_value(self) -> SnmpValueType:
        value = self._current
        self._current += self._increment
        return self._value_type(value)


class RandomNumericRule:
    """Random integer in a range, re-sampled on each read."""

    def __init__(
        self,
        *,
        min: int,
        max: int,
        value_type: _IntConstructible = Gauge32Value,
    ) -> None:
        self._min = min
        self._max = max
        self._value_type = value_type

    def get_value(self) -> SnmpValueType:
        return self._value_type(random.randint(self._min, self._max))


class UptimeRule:
    """Auto-incrementing timeticks (centiseconds) since construction."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def get_value(self) -> SnmpValueType:
        elapsed_cs = int((time.monotonic() - self._start) * 100)
        return TimeTicksValue(elapsed_cs)


class TimestampRule:
    """Current Unix epoch time as a scalar value."""

    def __init__(
        self,
        *,
        value_type: _IntConstructible = IntegerValue,
    ) -> None:
        self._value_type = value_type

    def get_value(self) -> SnmpValueType:
        return self._value_type(int(time.time()))


__all__ = [
    "CounterRule",
    "RandomNumericRule",
    "SimulationRule",
    "TimestampRule",
    "UptimeRule",
]
