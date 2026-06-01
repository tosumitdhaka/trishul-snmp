"""SNMPv3 USM (User-based Security Model) implementation."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from trishul_snmp.errors import AuthenticationError, ProtocolError
from trishul_snmp.wire.pdu import Pdu, PduType
from trishul_snmp.wire.v3message import (
    MSG_FLAG_AUTH,
    MSG_FLAG_PRIV,
    MSG_FLAG_REPORTABLE,
    UsmParams,
    decode_v3_message,
    encode_scoped_pdu,
    encode_v3_message,
)

if TYPE_CHECKING:
    from trishul_snmp.transport.dispatcher import RequestDispatcher

_AUTH_TAG_LEN = 12  # RFC 3414: HMAC truncated to 12 bytes
_REPORT_PDU_TAG = 0xA8  # SNMPv3 REPORT PDU tag — not in PduType enum


def _require_cryptography() -> None:
    try:
        import cryptography  # noqa: F401
    except ImportError:
        raise ImportError(
            "SNMPv3 auth/priv requires the cryptography package: pip install trishul-snmp[v3]"
        ) from None


class AuthProtocol(Enum):
    """Supported USM authentication protocols."""

    NONE = "none"
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"


class PrivProtocol(Enum):
    """Supported USM privacy protocols."""

    NONE = "none"
    DES = "des"
    AES128 = "aes128"


@dataclass(frozen=True, slots=True)
class UsmLocalEngine:
    """Explicit sender-authoritative engine state for outbound SNMPv3 traps."""

    engine_id: bytes
    engine_boots: int
    engine_time: int


@dataclass(frozen=True, slots=True)
class UsmUser:
    """USM credentials for a single user.

    *auth_key* is normally a passphrase; the RFC 3414 password-to-key
    derivation runs at message time.  Set *auth_key_localized=True* to
    skip derivation and use the key bytes directly (e.g. when supplying
    an already-localized key from an external credential store).
    """

    username: str
    auth_protocol: AuthProtocol = AuthProtocol.NONE
    auth_key: bytes = b""
    auth_key_localized: bool = False
    priv_protocol: PrivProtocol = PrivProtocol.NONE
    priv_key: bytes = b""


@dataclass
class UsmModel:
    """SNMPv3 USM SecurityModel.

    Stateful: caches engine_id / engine_boots / engine_time after discovery.
    ``wrap_pdu`` / ``unwrap_message`` are synchronous.
    ``prepare(dispatcher)`` is async (duck-typed, not in SecurityModel protocol)
    and performs engine discovery via a single RFC 3414 probe.
    """

    user: UsmUser
    context_name: bytes = b""
    local_engine: UsmLocalEngine | None = None

    # peer engine state — populated by prepare()
    _peer_engine_id: bytes = field(default=b"", init=False, repr=False)
    _peer_engine_boots: int = field(default=0, init=False, repr=False)
    _peer_engine_time: int = field(default=0, init=False, repr=False)
    _msg_id_counter: int = field(default=0, init=False, repr=False)

    # ── SecurityModel protocol ────────────────────────────────────────────

    def wrap_pdu(self, pdu: Pdu) -> bytes:
        """Encode a PDU into an SNMPv3 USM message."""
        engine = self._select_outbound_engine(pdu.pdu_type)
        flags = self._msg_flags(pdu.pdu_type)
        self._msg_id_counter += 1
        msg_id = self._msg_id_counter

        scoped_bytes = encode_scoped_pdu(engine.engine_id, self.context_name, pdu)

        if self.user.priv_protocol is not PrivProtocol.NONE:
            _require_cryptography()
            priv_params, scoped_bytes = self._encrypt_scoped_pdu(scoped_bytes, engine)
        else:
            priv_params = b""

        auth_params = b"\x00" * _AUTH_TAG_LEN if self._auth_enabled() else b""

        usm = UsmParams(
            engine_id=engine.engine_id,
            engine_boots=engine.engine_boots,
            engine_time=engine.engine_time,
            username=self.user.username.encode(),
            auth_params=auth_params,
            priv_params=priv_params,
        )
        raw = encode_v3_message(
            msg_id=msg_id,
            msg_max_size=65507,
            flags=flags,
            usm_params=usm,
            msg_data_bytes=scoped_bytes,
        )

        if self._auth_enabled():
            raw = self._stamp_auth(raw, engine.engine_id)

        return raw

    def unwrap_message(self, data: bytes) -> Pdu | None:
        """Decode and authenticate an inbound SNMPv3 USM message.

        Returns ``None`` for messages that belong to a different user or
        engine.  Raises :class:`AuthenticationError` on HMAC failure.
        """
        try:
            view = decode_v3_message(data)
        except ProtocolError:
            return None

        if view.usm_params.username != self.user.username.encode():
            return None

        # Reject messages from a different authoritative engine.
        # Skip the check during discovery (cached engine_id is still empty).
        if self._peer_engine_id and view.usm_params.engine_id != self._peer_engine_id:
            return None

        if self._auth_enabled():
            self._verify_auth(
                data,
                view.auth_params_offset,
                view.usm_params.auth_params,
                view.usm_params.engine_id,
            )

        msg_data = view.msg_data_bytes

        if self.user.priv_protocol is not PrivProtocol.NONE:
            _require_cryptography()
            msg_data = self._decrypt_scoped_pdu(
                msg_data,
                view.usm_params.priv_params,
                view.usm_params.engine_id,
                view.usm_params.engine_boots,
                view.usm_params.engine_time,
            )

        from trishul_snmp.wire.v3message import decode_scoped_pdu

        try:
            _engine_id, _ctx, pdu = decode_scoped_pdu(msg_data)
        except ProtocolError:
            return None

        return pdu

    # ── engine discovery ──────────────────────────────────────────────────

    async def prepare(self, dispatcher: RequestDispatcher) -> None:
        """Perform RFC 3414 engine discovery and cache engine parameters.

        Sends a noAuthNoPriv probe with empty engine_id; parses the REPORT
        response to extract engineID, engineBoots, and engineTime.
        """
        probe = self._build_discovery_probe()
        response_data = await dispatcher.send_raw_and_receive(probe)
        self._parse_discovery_response(response_data)

    # ── compatibility aliases / engine selection ─────────────────────────

    @property
    def _engine_id(self) -> bytes:
        return self._peer_engine_id

    @_engine_id.setter
    def _engine_id(self, value: bytes) -> None:
        self._peer_engine_id = value

    @property
    def _engine_boots(self) -> int:
        return self._peer_engine_boots

    @_engine_boots.setter
    def _engine_boots(self, value: int) -> None:
        self._peer_engine_boots = value

    @property
    def _engine_time(self) -> int:
        return self._peer_engine_time

    @_engine_time.setter
    def _engine_time(self, value: int) -> None:
        self._peer_engine_time = value

    @property
    def peer_engine_discovered(self) -> bool:
        """Whether peer engine discovery has populated authoritative peer state."""
        return bool(self._peer_engine_id)

    def _select_outbound_engine(self, pdu_type: PduType) -> UsmLocalEngine:
        if pdu_type is PduType.SNMPV2_TRAP:
            if self.local_engine is None:
                raise ProtocolError(
                    "SNMPv3 traps require local_engine authoritative state "
                    "(engine_id, engine_boots, engine_time)"
                )
            return self.local_engine
        return UsmLocalEngine(
            engine_id=self._peer_engine_id,
            engine_boots=self._peer_engine_boots,
            engine_time=self._peer_engine_time,
        )

    # ── RFC 3414 key derivation ───────────────────────────────────────────

    def _localize_key(self, password: bytes, engine_id: bytes) -> bytes:
        """Derive a localised key from a passphrase per RFC 3414 §2.6."""
        if self.user.auth_protocol is AuthProtocol.NONE:
            raise ProtocolError("Cannot localize key without an auth protocol")
        h = self._hash_engine()
        # Step 1: hash 1 MB of the password repeated cyclically
        buf = bytearray(1048576)
        plen = len(password)
        for i in range(1048576):
            buf[i] = password[i % plen]
        ku = h(bytes(buf)).digest()
        # Step 2: localise: H(Ku || engineID || Ku)
        return h(ku + engine_id + ku).digest()

    def _msg_flags(self, pdu_type: PduType) -> int:
        # RFC 3412 §7.1.9: reportableFlag set only for confirmed-class PDUs.
        # SNMPV2-TRAP and RESPONSE must have it cleared.
        _unconfirmed = {PduType.SNMPV2_TRAP, PduType.RESPONSE}
        flags = 0 if pdu_type in _unconfirmed else MSG_FLAG_REPORTABLE
        if self._auth_enabled():
            flags |= MSG_FLAG_AUTH
        if self.user.priv_protocol is not PrivProtocol.NONE:
            flags |= MSG_FLAG_PRIV
        return flags

    # ── auth helpers ──────────────────────────────────────────────────────

    def _auth_enabled(self) -> bool:
        return self.user.auth_protocol is not AuthProtocol.NONE

    def _hash_engine(self) -> Callable[[bytes], hashlib._Hash]:
        """Return the hashlib constructor for the configured auth protocol."""
        proto = self.user.auth_protocol
        if proto is AuthProtocol.MD5:
            return lambda data: hashlib.md5(data)  # noqa: S324
        if proto is AuthProtocol.SHA1:
            return lambda data: hashlib.sha1(data)  # noqa: S324
        if proto is AuthProtocol.SHA256:
            return lambda data: hashlib.sha256(data)
        raise ProtocolError(f"Unsupported auth protocol: {proto}")

    def _hmac_key(self, engine_id: bytes | None = None) -> bytes:
        """Return the localised HMAC key."""
        if not self.user.auth_key:
            return b""
        if self.user.auth_key_localized:
            return self.user.auth_key
        selected_engine_id = self._peer_engine_id if engine_id is None else engine_id
        return self._localize_key(self.user.auth_key, selected_engine_id)

    def _compute_auth_tag(self, msg: bytes, engine_id: bytes | None = None) -> bytes:
        """Compute 12-byte HMAC over *msg* using the localised auth key."""
        import hmac as _hmac

        proto = self.user.auth_protocol
        if proto is AuthProtocol.MD5:
            alg = "md5"
        elif proto is AuthProtocol.SHA1:
            alg = "sha1"
        elif proto is AuthProtocol.SHA256:
            alg = "sha256"
        else:
            raise ProtocolError(f"Unsupported auth protocol: {proto}")

        mac = _hmac.new(self._hmac_key(engine_id), msg, alg).digest()
        return mac[:_AUTH_TAG_LEN]

    def _stamp_auth(self, raw: bytes, engine_id: bytes | None = None) -> bytes:
        """Replace the 12-byte zero auth_params placeholder with the real HMAC."""
        tag = self._compute_auth_tag(raw, engine_id)
        # decode to find the auth_params_offset in the just-encoded message
        view = decode_v3_message(raw)
        offset = view.auth_params_offset
        return raw[:offset] + tag + raw[offset + _AUTH_TAG_LEN :]

    def _verify_auth(
        self,
        raw: bytes,
        auth_params_offset: int,
        received_tag: bytes,
        engine_id: bytes,
    ) -> None:
        """Verify the 12-byte auth tag; raise AuthenticationError on mismatch."""
        zeroed = (
            raw[:auth_params_offset]
            + b"\x00" * _AUTH_TAG_LEN
            + raw[auth_params_offset + _AUTH_TAG_LEN :]
        )
        expected = self._compute_auth_tag(zeroed, engine_id)
        import hmac as _hmac

        if not _hmac.compare_digest(expected, received_tag[:_AUTH_TAG_LEN]):
            raise AuthenticationError("USM authentication verification failed")

    # ── priv helpers (stubs — filled in Step 4) ──────────────────────────

    def _encrypt_scoped_pdu(
        self, scoped_bytes: bytes, engine: UsmLocalEngine
    ) -> tuple[bytes, bytes]:
        """Encrypt a ScopedPDU.  Returns (priv_params, encrypted_msg_data_bytes)."""
        _require_cryptography()
        proto = self.user.priv_protocol
        if proto is PrivProtocol.AES128:
            return self._encrypt_aes128(
                scoped_bytes,
                engine.engine_id,
                engine.engine_boots,
                engine.engine_time,
            )
        if proto is PrivProtocol.DES:
            return self._encrypt_des(scoped_bytes)
        raise ProtocolError(f"Unsupported priv protocol: {proto}")

    def _decrypt_scoped_pdu(
        self,
        msg_data: bytes,
        priv_params: bytes,
        engine_id: bytes,
        msg_engine_boots: int,
        msg_engine_time: int,
    ) -> bytes:
        """Decrypt an encryptedPDU.  Returns plain ScopedPDU bytes."""
        _require_cryptography()
        proto = self.user.priv_protocol
        if proto is PrivProtocol.AES128:
            return self._decrypt_aes128(
                msg_data, priv_params, engine_id, msg_engine_boots, msg_engine_time
            )
        if proto is PrivProtocol.DES:
            return self._decrypt_des(msg_data, priv_params)
        raise ProtocolError(f"Unsupported priv protocol: {proto}")

    def _encrypt_aes128(
        self,
        plaintext: bytes,
        engine_id: bytes,
        engine_boots: int,
        engine_time: int,
    ) -> tuple[bytes, bytes]:
        import os
        import struct
        import warnings

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        aes_key = self._priv_key_aes128(engine_id)
        local_iv = os.urandom(8)
        iv = struct.pack(">I", engine_boots) + struct.pack(">I", engine_time) + local_iv
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv))
        enc = cipher.encryptor()
        ciphertext = enc.update(plaintext) + enc.finalize()
        from trishul_snmp.wire.ber import encode_tlv as _enc_tlv

        return local_iv, _enc_tlv(0x04, ciphertext)

    def _decrypt_aes128(
        self,
        msg_data: bytes,
        priv_params: bytes,
        engine_id: bytes,
        msg_engine_boots: int,
        msg_engine_time: int,
    ) -> bytes:
        import struct
        import warnings

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        from trishul_snmp.wire.ber import decode_tlv as _dec_tlv

        tag, ciphertext, _ = _dec_tlv(msg_data, 0)
        if tag != 0x04:
            raise ProtocolError(f"Expected encryptedPDU OCTET STRING, found 0x{tag:02x}")
        if len(priv_params) != 8:
            raise ProtocolError(
                f"AES-128 privacyParameters must be exactly 8 octets, got {len(priv_params)}"
            )

        aes_key = self._priv_key_aes128(engine_id)
        local_iv = priv_params[:8]
        # IV uses boots/time from the inbound message header, not the cached local state.
        iv = struct.pack(">I", msg_engine_boots) + struct.pack(">I", msg_engine_time) + local_iv
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cipher = Cipher(algorithms.AES(aes_key), modes.CFB(iv))
        dec = cipher.decryptor()
        return dec.update(ciphertext) + dec.finalize()

    def _priv_key_aes128(self, engine_id: bytes) -> bytes:
        """Derive the 16-byte AES-128 privacy key (first 16 bytes of the localized priv key)."""
        if self.user.priv_key:
            raw = self._localize_priv_key(self.user.priv_key, engine_id)
            return raw[:16]
        raise ProtocolError("AES-128 privacy requires a priv_key")

    def _localize_priv_key(self, password: bytes, engine_id: bytes) -> bytes:
        """Localize a priv passphrase using the same RFC 3414 KDF as the auth key."""
        if self.user.auth_protocol is AuthProtocol.NONE:
            raise ProtocolError("Cannot derive priv key without an auth protocol")
        h = self._hash_engine()
        buf = bytearray(1048576)
        plen = len(password)
        for i in range(1048576):
            buf[i] = password[i % plen]
        ku = h(bytes(buf)).digest()
        return h(ku + engine_id + ku).digest()

    def _encrypt_des(self, plaintext: bytes) -> tuple[bytes, bytes]:
        raise ProtocolError("DES-CBC is not supported; use AES-128 or upgrade to cryptography>=42")

    def _decrypt_des(self, ciphertext: bytes, priv_params: bytes) -> bytes:
        raise ProtocolError("DES-CBC is not supported; use AES-128 or upgrade to cryptography>=42")

    # ── discovery helpers ─────────────────────────────────────────────────

    def _build_discovery_probe(self) -> bytes:
        """Build a noAuthNoPriv probe with empty engineID (RFC 3414 discovery)."""
        from trishul_snmp.types import NullValue
        from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind

        self._msg_id_counter += 1
        pdu = Pdu(
            pdu_type=PduType.GET,
            request_id=self._msg_id_counter,
            error_status=0,
            error_index=0,
            varbinds=(RawVarBind(oid=(1, 3, 6, 1, 6, 3, 15, 1, 1, 4, 0), value=NullValue()),),
        )
        scoped_bytes = encode_scoped_pdu(b"", b"", pdu)
        usm = UsmParams(
            engine_id=b"",
            engine_boots=0,
            engine_time=0,
            username=b"",
            auth_params=b"",
            priv_params=b"",
        )
        return encode_v3_message(
            msg_id=self._msg_id_counter,
            msg_max_size=65507,
            flags=MSG_FLAG_REPORTABLE,
            usm_params=usm,
            msg_data_bytes=scoped_bytes,
        )

    def _parse_discovery_response(self, data: bytes) -> None:
        """Parse a discovery REPORT and cache engine parameters.

        Raises :class:`ProtocolError` unless the response is a syntactically
        valid SNMPv3 USM message whose ScopedPDU contains a REPORT PDU
        (tag 0xA8).  Any other PDU type indicates a stray datagram and must
        not pollute session state.
        """
        try:
            view = decode_v3_message(data)
        except ProtocolError as exc:
            raise ProtocolError(f"Engine discovery: invalid response: {exc}") from exc

        try:
            _engine_id, _ctx, scoped_content, _offset = _peek_scoped_pdu(view.msg_data_bytes)
        except ProtocolError as exc:
            raise ProtocolError(f"Engine discovery: cannot decode ScopedPDU: {exc}") from exc

        # The PDU inside the ScopedPDU must be a REPORT (0xA8).
        if scoped_content != _REPORT_PDU_TAG:
            raise ProtocolError(
                f"Engine discovery: expected REPORT PDU (0x{_REPORT_PDU_TAG:02x}), "
                f"found 0x{scoped_content:02x}"
            )

        p = view.usm_params
        if not p.engine_id:
            raise ProtocolError("Engine discovery: REPORT contained empty engineID")
        self._peer_engine_id = p.engine_id
        self._peer_engine_boots = p.engine_boots
        self._peer_engine_time = p.engine_time


def _peek_scoped_pdu(msg_data_bytes: bytes) -> tuple[bytes, bytes, int, int]:
    """Decode a ScopedPDU and return (engine_id, context_name, pdu_tag, end_offset).

    Validates that the outer SEQUENCE, the two OCTET STRING fields, and the
    PDU TLV consume exactly all available bytes — no trailing content allowed.
    Used by ``_parse_discovery_response`` to validate the PDU type without
    going through the full ``decode_pdu`` path (REPORT is not in PduType).
    """
    from trishul_snmp.wire.ber import decode_tlv, expect_end

    sequence_tag = 0x30
    octet_string_tag = 0x04

    tag, content, end = decode_tlv(msg_data_bytes, 0)
    if tag != sequence_tag:
        raise ProtocolError(f"Expected ScopedPDU SEQUENCE, found 0x{tag:02x}")
    expect_end(msg_data_bytes, end)

    offset = 0
    eid_tag, engine_id, offset = decode_tlv(content, offset)
    if eid_tag != octet_string_tag:
        raise ProtocolError(f"Expected engineID OCTET STRING, found 0x{eid_tag:02x}")
    ctx_tag, context_name, offset = decode_tlv(content, offset)
    if ctx_tag != octet_string_tag:
        raise ProtocolError(f"Expected contextName OCTET STRING, found 0x{ctx_tag:02x}")
    pdu_tag, pdu_body, pdu_end = decode_tlv(content, offset)
    # No bytes may follow the PDU TLV inside the ScopedPDU SEQUENCE.
    expect_end(content, pdu_end)
    # Validate the REPORT body: request-id INTEGER, error-status INTEGER,
    # error-index INTEGER, VarBindList SEQUENCE — all present, nothing extra.
    _validate_report_body(pdu_body)
    return engine_id, context_name, pdu_tag, end


def _validate_report_body(pdu_body: bytes) -> None:
    """Validate a REPORT PDU body using the same decoders as normal PDUs.

    Delegates to the existing INTEGER and VarBindList decoders in
    ``trishul_snmp.wire.pdu`` so that empty-content INTEGERs, malformed
    varbinds, and trailing bytes are all rejected by the same rules.
    """
    from trishul_snmp.wire.ber import expect_end
    from trishul_snmp.wire.pdu import _decode_integer_from, _decode_varbind_list

    offset = 0
    _, offset = _decode_integer_from(pdu_body, offset)  # request-id
    _, offset = _decode_integer_from(pdu_body, offset)  # error-status
    _, offset = _decode_integer_from(pdu_body, offset)  # error-index
    _, offset = _decode_varbind_list(pdu_body, offset)  # VarBindList
    expect_end(pdu_body, offset)


def _localize_key_rfc3414(password: bytes, engine_id: bytes, auth_protocol: AuthProtocol) -> bytes:
    """Module-level RFC 3414 key localisation for use in tests with known vectors."""
    dummy = UsmModel(
        user=UsmUser(username="", auth_protocol=auth_protocol),
    )
    dummy._engine_id = engine_id
    return dummy._localize_key(password, engine_id)
