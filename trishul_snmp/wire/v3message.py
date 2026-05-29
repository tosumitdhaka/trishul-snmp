"""SNMPv3 message and USM security parameters codecs."""

from __future__ import annotations

from dataclasses import dataclass

from trishul_snmp.errors import ProtocolError
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end
from trishul_snmp.wire.pdu import Pdu, decode_pdu, encode_pdu

_SEQUENCE_TAG = 0x30
_INTEGER_TAG = 0x02
_OCTET_STRING_TAG = 0x04
_SNMP_V3_VERSION = 3

# msgFlags bits
MSG_FLAG_AUTH = 0x01
MSG_FLAG_PRIV = 0x02
MSG_FLAG_REPORTABLE = 0x04

# securityModel: USM = 3
_SECURITY_MODEL_USM = 3


@dataclass(frozen=True, slots=True)
class UsmParams:
    """Decoded USM security parameters (msgSecurityParameters)."""

    engine_id: bytes
    engine_boots: int
    engine_time: int
    username: bytes
    auth_params: bytes
    priv_params: bytes


@dataclass(slots=True)
class V3MessageView:
    """Decoded SNMPv3 outer message fields."""

    msg_id: int
    msg_max_size: int
    msg_flags: bytes
    msg_security_model: int
    usm_params: UsmParams
    # raw msgData bytes: ScopedPDU SEQUENCE when priv is off, encryptedPDU OCTET STRING when on
    msg_data_bytes: bytes
    # byte offset within the full message where auth_params field content starts;
    # needed so the verifier can zero-fill that field before recomputing HMAC
    auth_params_offset: int


def encode_v3_message(
    msg_id: int,
    msg_max_size: int,
    flags: int,
    usm_params: UsmParams,
    msg_data_bytes: bytes,
) -> bytes:
    """Encode a full SNMPv3 message to BER bytes.

    *msg_data_bytes* must be a ScopedPDU SEQUENCE when privacy is off, or an
    encryptedPDU OCTET STRING when the PRIV flag (0x02) is set.  The caller is
    responsible for filling auth_params inside *usm_params* with the correct
    HMAC before sending (or with 12 zero bytes as a placeholder during MAC
    computation).
    """
    header_data = _encode_header_data(msg_id, msg_max_size, flags)
    usm_bytes = _encode_usm_params(usm_params)
    security_params = encode_tlv(_OCTET_STRING_TAG, usm_bytes)

    content = b"".join(
        [
            _encode_integer(3),  # SNMPv3 version
            header_data,
            security_params,
            msg_data_bytes,
        ]
    )
    return encode_tlv(_SEQUENCE_TAG, content)


def decode_v3_message(data: bytes) -> V3MessageView:
    """Decode an SNMPv3 outer message.

    Returns a :class:`V3MessageView` whose *auth_params_offset* gives the
    byte position (relative to *data*) where the auth_params octet-string
    content starts.  The verifier zero-fills those 12 bytes, recomputes
    HMAC, then restores the original.
    """
    tag, content, end = decode_tlv(data, 0)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected SNMPv3 message SEQUENCE, found 0x{tag:02x}")
    expect_end(data, end)

    offset = 0

    version, offset = _decode_integer(content, offset)
    if version != _SNMP_V3_VERSION:
        raise ProtocolError(f"Expected SNMPv3 version 3, found {version}")

    msg_id, msg_max_size, msg_flags, msg_security_model, offset = _decode_header_data(
        content, offset
    )
    if msg_security_model != _SECURITY_MODEL_USM:
        raise ProtocolError(f"Expected USM security model (3), found {msg_security_model}")

    # security parameters: OCTET STRING wrapping BER-encoded UsmSecurityParameters
    sp_tag, sp_content, offset = decode_tlv(content, offset)
    if sp_tag != _OCTET_STRING_TAG:
        raise ProtocolError(f"Expected msgSecurityParameters OCTET STRING, found 0x{sp_tag:02x}")

    # Derive offsets from parser state, not re-encoded lengths, so non-canonical BER
    # length forms (e.g. long-form 0x81 0x7f for a 127-byte value) do not shift the
    # result.  Since expect_end verified the outer SEQUENCE spans all of data, the
    # outer content starts at exactly len(data) - len(content).
    usm_params, auth_params_offset_in_sp = _decode_usm_params_with_offset(sp_content)
    outer_content_start = len(data) - len(content)
    sp_content_start_in_data = outer_content_start + offset - len(sp_content)
    auth_params_offset = sp_content_start_in_data + auth_params_offset_in_sp

    # Validate and capture msgData: tag must match the PRIV flag.
    # PRIV set  → encryptedPDU OCTET STRING (0x04)
    # PRIV clear → ScopedPDU SEQUENCE (0x30)
    priv_set = bool(msg_flags[0] & MSG_FLAG_PRIV)
    expected_data_tag = _OCTET_STRING_TAG if priv_set else _SEQUENCE_TAG
    msg_data_start = offset
    msg_data_tag, _, offset = decode_tlv(content, offset)
    if msg_data_tag != expected_data_tag:
        label = "encryptedPDU OCTET STRING" if priv_set else "ScopedPDU SEQUENCE"
        raise ProtocolError(
            f"Expected msgData as {label} (0x{expected_data_tag:02x}), found 0x{msg_data_tag:02x}"
        )
    expect_end(content, offset)
    msg_data_bytes = content[msg_data_start:offset]

    return V3MessageView(
        msg_id=msg_id,
        msg_max_size=msg_max_size,
        msg_flags=msg_flags,
        msg_security_model=msg_security_model,
        usm_params=usm_params,
        msg_data_bytes=msg_data_bytes,
        auth_params_offset=auth_params_offset,
    )


def encode_scoped_pdu(engine_id: bytes, context_name: bytes, pdu: Pdu) -> bytes:
    """Encode a ScopedPDU to BER bytes."""
    content = b"".join(
        [
            encode_tlv(_OCTET_STRING_TAG, engine_id),
            encode_tlv(_OCTET_STRING_TAG, context_name),
            encode_pdu(pdu),
        ]
    )
    return encode_tlv(_SEQUENCE_TAG, content)


def decode_scoped_pdu(data: bytes) -> tuple[bytes, bytes, Pdu]:
    """Decode a BER-encoded ScopedPDU.

    Returns ``(engine_id, context_name, pdu)``.
    """
    tag, content, end = decode_tlv(data, 0)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected ScopedPDU SEQUENCE, found 0x{tag:02x}")
    expect_end(data, end)

    offset = 0
    engine_id, offset = _decode_octet_bytes(content, offset)
    context_name, offset = _decode_octet_bytes(content, offset)

    pdu_tag, pdu_content, offset = decode_tlv(content, offset)
    pdu = decode_pdu(bytes([pdu_tag]) + _reencode_length_prefixed(pdu_content))
    expect_end(content, offset)

    return engine_id, context_name, pdu


# ── internal helpers ─────────────────────────────────────────────────────────


def _encode_header_data(msg_id: int, msg_max_size: int, flags: int) -> bytes:
    content = b"".join(
        [
            _encode_integer(msg_id),
            _encode_integer(msg_max_size),
            encode_tlv(_OCTET_STRING_TAG, bytes([flags])),
            _encode_integer(_SECURITY_MODEL_USM),
        ]
    )
    return encode_tlv(_SEQUENCE_TAG, content)


def _decode_header_data(data: bytes, offset: int) -> tuple[int, int, bytes, int, int]:
    tag, content, offset = decode_tlv(data, offset)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected msgGlobalData SEQUENCE, found 0x{tag:02x}")

    inner = 0
    msg_id, inner = _decode_integer(content, inner)
    msg_max_size, inner = _decode_integer(content, inner)

    flags_tag, flags_content, inner = decode_tlv(content, inner)
    if flags_tag != _OCTET_STRING_TAG:
        raise ProtocolError(f"Expected msgFlags OCTET STRING, found 0x{flags_tag:02x}")
    if len(flags_content) != 1:
        raise ProtocolError("msgFlags must be exactly one octet")

    security_model, inner = _decode_integer(content, inner)
    expect_end(content, inner)
    return msg_id, msg_max_size, flags_content, security_model, offset


def _encode_usm_params(p: UsmParams) -> bytes:
    content = b"".join(
        [
            encode_tlv(_OCTET_STRING_TAG, p.engine_id),
            _encode_integer(p.engine_boots),
            _encode_integer(p.engine_time),
            encode_tlv(_OCTET_STRING_TAG, p.username),
            encode_tlv(_OCTET_STRING_TAG, p.auth_params),
            encode_tlv(_OCTET_STRING_TAG, p.priv_params),
        ]
    )
    return encode_tlv(_SEQUENCE_TAG, content)


def _decode_usm_params_with_offset(data: bytes) -> tuple[UsmParams, int]:
    """Decode UsmSecurityParameters BER bytes.

    Returns ``(UsmParams, auth_params_content_offset)`` where
    *auth_params_content_offset* is the byte offset of the auth_params
    octet-string *content* (past the tag+length) within *data*.
    """
    tag, content, end = decode_tlv(data, 0)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected UsmSecurityParameters SEQUENCE, found 0x{tag:02x}")
    expect_end(data, end)

    # content starts at len(data) - len(content); derive all offsets from parser state
    # so non-canonical length encodings do not shift the auth_params pointer.
    content_start = len(data) - len(content)

    offset = 0  # offset within content

    engine_id, offset = _decode_octet_bytes(content, offset)
    engine_boots, offset = _decode_integer(content, offset)
    engine_time, offset = _decode_integer(content, offset)
    username, offset = _decode_octet_bytes(content, offset)

    # auth_params: record offset of its content within data using parser positions
    auth_tag, auth_content, auth_end = decode_tlv(content, offset)
    if auth_tag != _OCTET_STRING_TAG:
        raise ProtocolError(
            f"Expected msgAuthenticationParameters OCTET STRING, found 0x{auth_tag:02x}"
        )
    # auth_content starts at auth_end - len(auth_content) within content,
    # which maps to content_start + (auth_end - len(auth_content)) within data.
    auth_params_content_offset_in_data = content_start + auth_end - len(auth_content)
    offset = auth_end

    priv_params, offset = _decode_octet_bytes(content, offset)
    expect_end(content, offset)

    return (
        UsmParams(
            engine_id=engine_id,
            engine_boots=engine_boots,
            engine_time=engine_time,
            username=username,
            auth_params=auth_content,
            priv_params=priv_params,
        ),
        auth_params_content_offset_in_data,
    )


def _encode_integer(value: int) -> bytes:
    from trishul_snmp.types import IntegerValue
    from trishul_snmp.wire.asn1 import encode_value

    return encode_value(IntegerValue(value))


def _decode_integer(data: bytes, offset: int) -> tuple[int, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _INTEGER_TAG:
        raise ProtocolError(f"Expected INTEGER, found 0x{tag:02x}")
    if not content:
        raise ProtocolError("INTEGER content cannot be empty")
    return int.from_bytes(content, "big", signed=True), new_offset


def _decode_octet_bytes(data: bytes, offset: int) -> tuple[bytes, int]:
    tag, content, new_offset = decode_tlv(data, offset)
    if tag != _OCTET_STRING_TAG:
        raise ProtocolError(f"Expected OCTET STRING, found 0x{tag:02x}")
    return content, new_offset


def _reencode_length_prefixed(content: bytes) -> bytes:
    from trishul_snmp.wire.ber import encode_length

    return encode_length(len(content)) + content
