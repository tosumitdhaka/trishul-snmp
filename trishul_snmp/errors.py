"""Project exception hierarchy."""

from __future__ import annotations

from pathlib import Path


class TsnmpError(Exception):
    """Base exception for trishul-snmp."""


class BundleError(TsnmpError):
    """Raised for bundle loading or validation failures."""


class BundleValidationError(BundleError):
    """Raised when a module or bundle artifact is structurally invalid."""

    def __init__(self, message: str, *, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            message = f"{message}: {self.path}"
        super().__init__(message)


class TranslationError(BundleError):
    """Raised when symbolic or numeric translation fails."""


class InvalidOidError(TranslationError):
    """Raised when an OID string or path is malformed."""


class UnknownSymbolError(TranslationError):
    """Raised when a symbolic identifier cannot be resolved."""


class UnknownOidError(TranslationError):
    """Raised when a numeric OID cannot be resolved."""


class ProtocolError(TsnmpError):
    """Raised when an SNMP message is malformed or unsupported."""


class TransportError(TsnmpError):
    """Raised for socket or network transport failures."""


class RequestTimeoutError(TransportError):
    """Raised when a request does not receive a matching response in time."""


class EngineRecoveryReportError(TsnmpError):
    """Raised when a usmStatsNotInTimeWindows REPORT arrives for an in-flight request.

    The USM model has already adopted the peer's authoritative engine state
    and set the engine-recovery flag; the caller should consume the flag and
    retry the request once instead of waiting out the full timeout.
    """

    def __init__(self, message: str, *, report: bytes) -> None:
        self.report = report
        super().__init__(message)


class AuthenticationError(ProtocolError):
    """Raised when SNMPv3 USM message authentication verification fails."""
