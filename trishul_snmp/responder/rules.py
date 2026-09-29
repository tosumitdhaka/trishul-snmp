"""Simulation rules for dynamic responder values."""

from __future__ import annotations

import random
import time
from typing import Protocol, runtime_checkable

from trishul_snmp.types import (
    Counter32Value,
    Counter64Value,
    Gauge32Value,
    IntegerValue,
    SnmpValueType,
    TimeTicksValue,
)


class _IntConstructible(Protocol):
    def __call__(self, value: int, /) -> SnmpValueType: ...


def _wire_modulus(value_type: _IntConstructible) -> int | None:
    """Return the wire modulus for *value_type*, or ``None`` when unbounded.

    Counter32, Gauge32, and TimeTicks share the 32-bit unsigned limit;
    Counter64 uses 64 bits. Types without a wire modulus (e.g. plain
    ``IntegerValue``) never wrap.
    """
    if value_type in (Counter32Value, Gauge32Value, TimeTicksValue):
        return 2**32
    if value_type is Counter64Value:
        return 2**64
    return None


@runtime_checkable
class SimulationRule(Protocol):
    """Protocol for dynamic OID value simulation rules."""

    def get_value(self) -> SnmpValueType:
        """Return the current simulated value."""
        ...


class CounterRule:
    """Monotonically increasing counter, incremented on each read.

    Values wrap at the wire modulus of the configured value type so a
    long-running simulation never produces a value that cannot be encoded
    on the wire: a Counter32 at ``2**32 - 1`` wraps to ``0`` on the next
    read, and a Counter64 wraps at ``2**64``.
    """

    def __init__(
        self,
        *,
        start: int = 0,
        increment: int = 1,
        value_type: _IntConstructible = Counter32Value,
    ) -> None:
        if start < 0:
            raise ValueError("CounterRule start cannot be negative")
        if increment < 0:
            raise ValueError("CounterRule increment cannot be negative")
        modulus = _wire_modulus(value_type)
        if modulus is not None and start >= modulus:
            raise ValueError(
                "CounterRule start must be below the wire modulus "
                f"{modulus} of {getattr(value_type, '__name__', str(value_type))}"
            )
        self._current = start
        self._increment = increment
        self._value_type = value_type
        self._modulus = modulus

    def get_value(self) -> SnmpValueType:
        value = self._current
        self._current += self._increment
        if self._modulus is not None and self._current >= self._modulus:
            self._current %= self._modulus
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
    """Auto-incrementing timeticks (centiseconds) since construction.

    The value wraps at the TimeTicks wire modulus (``2**32``) so a
    long-running simulation never produces an unencodable value.
    """

    def __init__(self) -> None:
        self._start = time.monotonic()

    def get_value(self) -> SnmpValueType:
        elapsed_cs = int((time.monotonic() - self._start) * 100) % 2**32
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
