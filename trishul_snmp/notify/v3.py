"""Listener-side SNMPv3 notification helpers."""

from __future__ import annotations

from dataclasses import dataclass

from trishul_snmp.errors import ProtocolError
from trishul_snmp.security.usm import (
    AuthProtocol,
    PrivProtocol,
    UsmLocalEngine,
    UsmModel,
    UsmUser,
)
from trishul_snmp.types import Counter32Value, NullValue
from trishul_snmp.wire.asn1 import encode_value
from trishul_snmp.wire.ber import decode_tlv, encode_length, encode_tlv, expect_end
from trishul_snmp.wire.pdu import Pdu, PduType, RawVarBind, decode_pdu
from trishul_snmp.wire.v3message import (
    MSG_FLAG_AUTH,
    MSG_FLAG_PRIV,
    MSG_FLAG_REPORTABLE,
    UsmParams,
    V3MessageView,
    decode_v3_message,
    encode_scoped_pdu,
    encode_v3_message,
)

_AUTH_TAG_LEN = 12
_MAX_MSG_SIZE = 65507
_REPORT_PDU_TAG = 0xA8
_SEQUENCE_TAG = 0x30
_OCTET_STRING_TAG = 0x04
_DISCOVERY_PROBE_OID = (1, 3, 6, 1, 6, 3, 15, 1, 1, 4, 0)
_NOTIFICATION_PDU_TAGS = {int(PduType.SNMPV2_TRAP), int(PduType.INFORM_REQUEST)}


@dataclass(frozen=True, slots=True)
class V3NotificationEnvelope:
    """Decoded inbound SNMPv3 notification plus v3 metadata."""

    view: V3MessageView
    pdu: Pdu
    context_engine_id: bytes
    context_name: bytes
    security_level: str


def decode_v3_notification_message(data: bytes, *, user: UsmUser) -> V3NotificationEnvelope | None:
    """Decode an inbound SNMPv3 trap or inform for a single configured user.

    Returns ``None`` for wrong-user or non-notification messages. Raises
    :class:`ProtocolError` or :class:`AuthenticationError` for malformed or
    auth-failed messages that otherwise target the configured user.
    """
    view = decode_v3_message(data)
    if view.usm_params.username != user.username.encode():
        return None

    flags = view.msg_flags[0]
    _validate_security_level(flags, user=user)

    codec = _usm_codec(user=user)
    if flags & MSG_FLAG_AUTH:
        if len(view.usm_params.auth_params) != _AUTH_TAG_LEN:
            raise ProtocolError(
                f"USM auth parameters must be exactly {_AUTH_TAG_LEN} octets, "
                f"got {len(view.usm_params.auth_params)}"
            )
        codec._verify_auth(
            data,
            view.auth_params_offset,
            view.usm_params.auth_params,
            view.usm_params.engine_id,
        )

    msg_data = view.msg_data_bytes
    if flags & MSG_FLAG_PRIV:
        msg_data = codec._decrypt_scoped_pdu(
            msg_data,
            view.usm_params.priv_params,
            view.usm_params.engine_id,
            view.usm_params.engine_boots,
            view.usm_params.engine_time,
        )

    context_engine_id, context_name, pdu = _decode_notification_scoped_pdu(msg_data)
    if pdu is None:
        return None
    _validate_notification_reportable_flag(flags, pdu.pdu_type)

    return V3NotificationEnvelope(
        view=view,
        pdu=pdu,
        context_engine_id=context_engine_id,
        context_name=context_name,
        security_level=_security_level_from_flags(flags),
    )


def is_discovery_probe(data: bytes) -> bool:
    """Whether *data* is the empty-engineID discovery probe used by V3Notifier."""
    try:
        view = decode_v3_message(data)
    except ProtocolError:
        return False

    if view.msg_flags[0] != MSG_FLAG_REPORTABLE:
        return False

    params = view.usm_params
    if (
        params.engine_id
        or params.engine_boots != 0
        or params.engine_time != 0
        or params.username
        or params.auth_params
        or params.priv_params
    ):
        return False

    try:
        context_engine_id, context_name, pdu_tag, pdu_content = _decode_scoped_fields(
            view.msg_data_bytes
        )
    except ProtocolError:
        return False

    if context_engine_id or context_name or pdu_tag != int(PduType.GET):
        return False

    try:
        probe = _decode_pdu_bytes(pdu_tag, pdu_content)
    except ProtocolError:
        return False
    if len(probe.varbinds) != 1:
        return False

    varbind = probe.varbinds[0]
    return varbind.oid == _DISCOVERY_PROBE_OID and isinstance(varbind.value, NullValue)


def encode_discovery_report(data: bytes, *, local_engine: UsmLocalEngine) -> bytes:
    """Encode a minimal discovery REPORT for an empty-engineID probe."""
    view, context_engine_id, context_name, probe = _decode_discovery_probe(data)
    report_pdu = _encode_report_pdu(
        request_id=probe.request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=_DISCOVERY_PROBE_OID, value=Counter32Value(1)),),
    )
    scoped = _encode_scoped_raw_pdu(context_engine_id, context_name, report_pdu)
    return encode_v3_message(
        msg_id=view.msg_id,
        msg_max_size=_MAX_MSG_SIZE,
        flags=0,
        usm_params=UsmParams(
            engine_id=local_engine.engine_id,
            engine_boots=local_engine.engine_boots,
            engine_time=local_engine.engine_time,
            username=b"",
            auth_params=b"",
            priv_params=b"",
        ),
        msg_data_bytes=scoped,
    )


def encode_inform_response(
    envelope: V3NotificationEnvelope,
    *,
    user: UsmUser,
    local_engine: UsmLocalEngine,
) -> bytes:
    """Encode a USM RESPONSE that acknowledges an INFORM request."""
    if envelope.pdu.pdu_type is not PduType.INFORM_REQUEST:
        raise ProtocolError(
            f"Inform response requires INFORM-REQUEST, found {envelope.pdu.pdu_type.name}"
        )

    flags = envelope.view.msg_flags[0]
    _validate_security_level(flags, user=user)

    response_pdu = Pdu(
        pdu_type=PduType.RESPONSE,
        request_id=envelope.pdu.request_id,
        error_status=0,
        error_index=0,
        varbinds=envelope.pdu.varbinds,
    )
    msg_data = encode_scoped_pdu(
        envelope.context_engine_id,
        envelope.context_name,
        response_pdu,
    )

    codec = _usm_codec(user=user, local_engine=local_engine)
    priv_params = b""
    if flags & MSG_FLAG_PRIV:
        priv_params, msg_data = codec._encrypt_scoped_pdu(msg_data, local_engine)

    auth_params = b"\x00" * _AUTH_TAG_LEN if flags & MSG_FLAG_AUTH else b""
    raw = encode_v3_message(
        msg_id=envelope.view.msg_id,
        msg_max_size=_MAX_MSG_SIZE,
        flags=flags & (MSG_FLAG_AUTH | MSG_FLAG_PRIV),
        usm_params=UsmParams(
            engine_id=local_engine.engine_id,
            engine_boots=local_engine.engine_boots,
            engine_time=local_engine.engine_time,
            username=user.username.encode(),
            auth_params=auth_params,
            priv_params=priv_params,
        ),
        msg_data_bytes=msg_data,
    )

    if flags & MSG_FLAG_AUTH:
        raw = codec._stamp_auth(raw, local_engine.engine_id)
    return raw


def _security_level_from_flags(flags: int) -> str:
    if flags & MSG_FLAG_PRIV:
        return "authPriv"
    if flags & MSG_FLAG_AUTH:
        return "authNoPriv"
    return "noAuthNoPriv"


def _validate_security_level(flags: int, *, user: UsmUser) -> None:
    if (flags & MSG_FLAG_PRIV) and not (flags & MSG_FLAG_AUTH):
        raise ProtocolError("SNMPv3 privacy requires authentication")
    actual = flags & (MSG_FLAG_AUTH | MSG_FLAG_PRIV)
    expected = _expected_security_flags(user)
    if actual != expected:
        raise ProtocolError(
            "Configured user requires "
            f"{_security_level_from_flags(expected)} messages, "
            f"received {_security_level_from_flags(actual)}"
        )


def _expected_security_flags(user: UsmUser) -> int:
    expected = 0
    if user.auth_protocol is not AuthProtocol.NONE:
        expected |= MSG_FLAG_AUTH
    if user.priv_protocol is not PrivProtocol.NONE:
        expected |= MSG_FLAG_PRIV
    return expected


def _validate_notification_reportable_flag(flags: int, pdu_type: PduType) -> None:
    reportable = bool(flags & MSG_FLAG_REPORTABLE)
    if pdu_type is PduType.SNMPV2_TRAP and reportable:
        raise ProtocolError("SNMPv3 trap notifications must clear reportableFlag")
    if pdu_type is PduType.INFORM_REQUEST and not reportable:
        raise ProtocolError("SNMPv3 inform notifications must set reportableFlag")


def _usm_codec(*, user: UsmUser, local_engine: UsmLocalEngine | None = None) -> UsmModel:
    # Reuse the shared USM auth/priv primitives without carrying over the
    # client-side discovery state machine into the listener-side path.
    return UsmModel(user=user, local_engine=local_engine)


def _decode_discovery_probe(data: bytes) -> tuple[V3MessageView, bytes, bytes, Pdu]:
    try:
        view = decode_v3_message(data)
        context_engine_id, context_name, pdu_tag, pdu_content = _decode_scoped_fields(
            view.msg_data_bytes
        )
    except ProtocolError as exc:
        raise ProtocolError(f"Invalid discovery probe: {exc}") from exc

    if not is_discovery_probe(data):
        raise ProtocolError("Invalid discovery probe")

    return (
        view,
        context_engine_id,
        context_name,
        _decode_pdu_bytes(pdu_tag, pdu_content),
    )


def _decode_notification_scoped_pdu(data: bytes) -> tuple[bytes, bytes, Pdu | None]:
    context_engine_id, context_name, pdu_tag, pdu_content = _decode_scoped_fields(data)
    if pdu_tag not in _NOTIFICATION_PDU_TAGS:
        return context_engine_id, context_name, None
    return context_engine_id, context_name, _decode_pdu_bytes(pdu_tag, pdu_content)


def _decode_scoped_fields(data: bytes) -> tuple[bytes, bytes, int, bytes]:
    tag, content, end = decode_tlv(data, 0)
    if tag != _SEQUENCE_TAG:
        raise ProtocolError(f"Expected ScopedPDU SEQUENCE, found 0x{tag:02x}")
    expect_end(data, end)

    offset = 0
    context_engine_id, offset = _decode_octets(content, offset, label="contextEngineID")
    context_name, offset = _decode_octets(content, offset, label="contextName")
    pdu_tag, pdu_content, offset = decode_tlv(content, offset)
    expect_end(content, offset)
    return context_engine_id, context_name, pdu_tag, pdu_content


def _decode_octets(data: bytes, offset: int, *, label: str) -> tuple[bytes, int]:
    tag, content, offset = decode_tlv(data, offset)
    if tag != _OCTET_STRING_TAG:
        raise ProtocolError(f"Expected {label} OCTET STRING, found 0x{tag:02x}")
    return content, offset


def _decode_pdu_bytes(tag: int, content: bytes) -> Pdu:
    return decode_pdu(bytes([tag]) + encode_length(len(content)) + content)


def _encode_report_pdu(
    *,
    request_id: int,
    error_status: int,
    error_index: int,
    varbinds: tuple[RawVarBind, ...],
) -> bytes:
    content = b"".join(
        [
            _encode_integer(request_id),
            _encode_integer(error_status),
            _encode_integer(error_index),
            _encode_varbind_list(varbinds),
        ]
    )
    return encode_tlv(_REPORT_PDU_TAG, content)


def _encode_scoped_raw_pdu(context_engine_id: bytes, context_name: bytes, pdu: bytes) -> bytes:
    return encode_tlv(
        _SEQUENCE_TAG,
        encode_tlv(_OCTET_STRING_TAG, context_engine_id)
        + encode_tlv(_OCTET_STRING_TAG, context_name)
        + pdu,
    )


def _encode_integer(value: int) -> bytes:
    from trishul_snmp.types import IntegerValue

    return encode_value(IntegerValue(value))


def _encode_varbind_list(varbinds: tuple[RawVarBind, ...]) -> bytes:
    return encode_tlv(_SEQUENCE_TAG, b"".join(_encode_varbind(varbind) for varbind in varbinds))


def _encode_varbind(varbind: RawVarBind) -> bytes:
    from trishul_snmp.types import ObjectIdentifierValue

    return encode_tlv(
        _SEQUENCE_TAG,
        encode_value(ObjectIdentifierValue(varbind.oid)) + encode_value(varbind.value),
    )
