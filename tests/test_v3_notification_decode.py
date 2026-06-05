from __future__ import annotations

import hashlib

import pytest

from trishul_snmp.errors import AuthenticationError, ProtocolError
from trishul_snmp.notify.events import decode_notification
from trishul_snmp.notify.v3 import (
    decode_v3_notification_message,
    encode_discovery_report,
    encode_inform_response,
    is_discovery_probe,
)
from trishul_snmp.security.usm import (
    AuthProtocol,
    PrivProtocol,
    UsmLocalEngine,
    UsmModel,
    UsmUser,
)
from trishul_snmp.types import Counter32Value, NullValue
from trishul_snmp.wire.ber import decode_tlv, encode_tlv, expect_end
from trishul_snmp.wire.message import SnmpMessage, encode_message
from trishul_snmp.wire.pdu import (
    Pdu,
    PduType,
    RawVarBind,
    _decode_integer_from,
    _decode_varbind_list,
)
from trishul_snmp.wire.v3message import (
    MSG_FLAG_AUTH,
    MSG_FLAG_PRIV,
    MSG_FLAG_REPORTABLE,
    UsmParams,
    decode_scoped_pdu,
    decode_v3_message,
    encode_v3_message,
)

_DISCOVERY_PROBE_OID = (1, 3, 6, 1, 6, 3, 15, 1, 1, 4, 0)


def _make_local_engine(fill: int, *, boots: int = 7, time: int = 111) -> UsmLocalEngine:
    return UsmLocalEngine(
        engine_id=b"\x80\x00\x01\x02\x03" + bytes([fill]) * 12,
        engine_boots=boots,
        engine_time=time,
    )


def _make_user(*, level: str, username: str = "notifyuser") -> UsmUser:
    md5_len = hashlib.md5(b"").digest_size
    if level == "noAuthNoPriv":
        return UsmUser(username=username, auth_protocol=AuthProtocol.NONE)
    if level == "authNoPriv":
        return UsmUser(
            username=username,
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"\xaa" * md5_len,
            auth_key_localized=True,
        )
    if level == "authPriv":
        return UsmUser(
            username=username,
            auth_protocol=AuthProtocol.MD5,
            auth_key=b"\xaa" * md5_len,
            auth_key_localized=True,
            priv_protocol=PrivProtocol.AES128,
            priv_key=b"privpassword12345",
        )
    raise AssertionError(f"unexpected test security level: {level}")


def _make_notification_pdu(pdu_type: PduType, *, request_id: int = 41) -> Pdu:
    return Pdu(
        pdu_type=pdu_type,
        request_id=request_id,
        error_status=0,
        error_index=0,
        varbinds=(RawVarBind(oid=(1, 3, 6, 1, 2, 1, 1, 1, 0), value=NullValue()),),
    )


def _make_message(
    *,
    user: UsmUser,
    pdu: Pdu,
    context_name: bytes = b"",
    local_engine: UsmLocalEngine | None = None,
    peer_engine: UsmLocalEngine | None = None,
) -> bytes:
    model = UsmModel(user=user, context_name=context_name, local_engine=local_engine)
    if peer_engine is not None:
        model._engine_id = peer_engine.engine_id
        model._engine_boots = peer_engine.engine_boots
        model._engine_time = peer_engine.engine_time
    return model.wrap_pdu(pdu)


def _restamp_auth(raw: bytes, *, user: UsmUser, engine_id: bytes) -> bytes:
    return UsmModel(user=user)._stamp_auth(raw, engine_id)


def _decode_report_scoped_pdu(
    data: bytes,
) -> tuple[bytes, bytes, int, int, int, int, tuple[RawVarBind, ...]]:
    tag, content, end = decode_tlv(data, 0)
    assert tag == 0x30
    expect_end(data, end)

    offset = 0
    engine_tag, context_engine_id, offset = decode_tlv(content, offset)
    assert engine_tag == 0x04
    name_tag, context_name, offset = decode_tlv(content, offset)
    assert name_tag == 0x04
    pdu_tag, pdu_content, offset = decode_tlv(content, offset)
    expect_end(content, offset)

    inner = 0
    request_id, inner = _decode_integer_from(pdu_content, inner)
    error_status, inner = _decode_integer_from(pdu_content, inner)
    error_index, inner = _decode_integer_from(pdu_content, inner)
    varbinds, inner = _decode_varbind_list(pdu_content, inner)
    expect_end(pdu_content, inner)
    return (
        context_engine_id,
        context_name,
        pdu_tag,
        request_id,
        error_status,
        error_index,
        varbinds,
    )


def test_decode_v3_trap_noauthnopriv() -> None:
    user = _make_user(level="noAuthNoPriv")
    sender_engine = _make_local_engine(0x11, boots=3, time=22)
    pdu = _make_notification_pdu(PduType.SNMPV2_TRAP, request_id=101)
    raw = _make_message(
        user=user,
        pdu=pdu,
        context_name=b"trapctx",
        local_engine=sender_engine,
    )

    envelope = decode_v3_notification_message(raw, user=user)

    assert envelope is not None
    assert envelope.pdu == pdu
    assert envelope.context_engine_id == sender_engine.engine_id
    assert envelope.context_name == b"trapctx"
    assert envelope.security_level == "noAuthNoPriv"
    assert envelope.view.usm_params.engine_id == sender_engine.engine_id


def test_decode_v3_inform_authnopriv() -> None:
    user = _make_user(level="authNoPriv")
    receiver_engine = _make_local_engine(0x22, boots=4, time=33)
    pdu = _make_notification_pdu(PduType.INFORM_REQUEST, request_id=102)
    raw = _make_message(
        user=user,
        pdu=pdu,
        context_name=b"informctx",
        peer_engine=receiver_engine,
    )

    envelope = decode_v3_notification_message(raw, user=user)

    assert envelope is not None
    assert envelope.pdu == pdu
    assert envelope.context_engine_id == receiver_engine.engine_id
    assert envelope.context_name == b"informctx"
    assert envelope.security_level == "authNoPriv"
    assert envelope.view.msg_flags[0] & MSG_FLAG_AUTH
    assert not (envelope.view.msg_flags[0] & MSG_FLAG_PRIV)


def test_decode_v3_trap_authpriv() -> None:
    user = _make_user(level="authPriv")
    sender_engine = _make_local_engine(0x33, boots=5, time=44)
    pdu = _make_notification_pdu(PduType.SNMPV2_TRAP, request_id=103)
    raw = _make_message(
        user=user,
        pdu=pdu,
        context_name=b"privctx",
        local_engine=sender_engine,
    )

    envelope = decode_v3_notification_message(raw, user=user)

    assert envelope is not None
    assert envelope.pdu == pdu
    assert envelope.context_engine_id == sender_engine.engine_id
    assert envelope.context_name == b"privctx"
    assert envelope.security_level == "authPriv"
    assert envelope.view.msg_flags[0] & MSG_FLAG_AUTH
    assert envelope.view.msg_flags[0] & MSG_FLAG_PRIV


def test_decode_v3_notification_returns_none_for_wrong_user() -> None:
    sender = _make_user(level="noAuthNoPriv", username="alice")
    receiver = _make_user(level="noAuthNoPriv", username="bob")
    sender_engine = _make_local_engine(0x44)
    raw = _make_message(
        user=sender,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP),
        local_engine=sender_engine,
    )

    assert decode_v3_notification_message(raw, user=receiver) is None


def test_decode_v3_notification_returns_none_for_non_notification_pdu() -> None:
    user = _make_user(level="noAuthNoPriv")
    peer_engine = _make_local_engine(0x55)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.GET, request_id=104),
        peer_engine=peer_engine,
    )

    assert decode_v3_notification_message(raw, user=user) is None


def test_decode_v3_notification_rejects_noauth_for_auth_user() -> None:
    receiver = _make_user(level="authNoPriv")
    sender = _make_user(level="noAuthNoPriv", username=receiver.username)
    raw = _make_message(
        user=sender,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=119),
        local_engine=_make_local_engine(0x59),
    )

    with pytest.raises(ProtocolError, match="requires authNoPriv"):
        decode_v3_notification_message(raw, user=receiver)


def test_decode_v3_notification_rejects_authnopriv_for_authpriv_user() -> None:
    receiver = _make_user(level="authPriv")
    sender = _make_user(level="authNoPriv", username=receiver.username)
    raw = _make_message(
        user=sender,
        pdu=_make_notification_pdu(PduType.INFORM_REQUEST, request_id=119),
        peer_engine=_make_local_engine(0x5A),
    )

    with pytest.raises(ProtocolError, match="requires authPriv"):
        decode_v3_notification_message(raw, user=receiver)


def test_decode_v3_notification_rejects_trap_with_reportable_flag_set() -> None:
    user = _make_user(level="noAuthNoPriv")
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=119),
        local_engine=_make_local_engine(0x5B),
    )
    view = decode_v3_message(raw)
    mutated = encode_v3_message(
        view.msg_id,
        view.msg_max_size,
        view.msg_flags[0] | MSG_FLAG_REPORTABLE,
        view.usm_params,
        view.msg_data_bytes,
    )

    with pytest.raises(ProtocolError, match="trap notifications must clear reportableFlag"):
        decode_v3_notification_message(mutated, user=user)


def test_decode_v3_notification_rejects_inform_with_reportable_flag_clear() -> None:
    user = _make_user(level="noAuthNoPriv")
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.INFORM_REQUEST, request_id=120),
        peer_engine=_make_local_engine(0x5C),
    )
    view = decode_v3_message(raw)
    mutated = encode_v3_message(
        view.msg_id,
        view.msg_max_size,
        view.msg_flags[0] & ~MSG_FLAG_REPORTABLE,
        view.usm_params,
        view.msg_data_bytes,
    )

    with pytest.raises(ProtocolError, match="inform notifications must set reportableFlag"):
        decode_v3_notification_message(mutated, user=user)


def test_decode_notification_v3_builds_public_event() -> None:
    user = _make_user(level="authNoPriv")
    receiver_engine = _make_local_engine(0x5A, boots=9, time=123)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.INFORM_REQUEST, request_id=120),
        context_name=b"alerts",
        peer_engine=receiver_engine,
    )

    event = decode_notification(raw, user=user, source_address=("127.0.0.1", 40162))

    assert event.community is None
    assert event.snmp_version == "3"
    assert event.username == "notifyuser"
    assert event.security_level == "authNoPriv"
    assert event.context_engine_id == receiver_engine.engine_id
    assert event.context_name == b"alerts"
    assert event.authoritative_engine_id == receiver_engine.engine_id
    assert event.authoritative_engine_boots == receiver_engine.engine_boots
    assert event.authoritative_engine_time == receiver_engine.engine_time
    assert event.source_address == ("127.0.0.1", 40162)


def test_decode_notification_v3_wrong_user_raises_protocol_error() -> None:
    sender = _make_user(level="noAuthNoPriv", username="alice")
    receiver = _make_user(level="noAuthNoPriv", username="bob")
    raw = _make_message(
        user=sender,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=121),
        local_engine=_make_local_engine(0x5B),
    )

    with pytest.raises(ProtocolError, match="configured user"):
        decode_notification(raw, user=receiver)


def test_decode_v3_notification_raises_on_bad_hmac() -> None:
    user = _make_user(level="authNoPriv")
    receiver_engine = _make_local_engine(0x66)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.INFORM_REQUEST, request_id=105),
        peer_engine=receiver_engine,
    )
    view = decode_v3_message(raw)
    tampered = (
        raw[: view.auth_params_offset]
        + bytes([raw[view.auth_params_offset] ^ 0xFF])
        + raw[view.auth_params_offset + 1 :]
    )

    with pytest.raises(AuthenticationError):
        decode_v3_notification_message(tampered, user=user)


def test_decode_notification_v3_raises_on_bad_hmac() -> None:
    user = _make_user(level="authNoPriv")
    receiver_engine = _make_local_engine(0x5C)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.INFORM_REQUEST, request_id=122),
        peer_engine=receiver_engine,
    )
    view = decode_v3_message(raw)
    tampered = (
        raw[: view.auth_params_offset]
        + bytes([raw[view.auth_params_offset] ^ 0xFF])
        + raw[view.auth_params_offset + 1 :]
    )

    with pytest.raises(AuthenticationError):
        decode_notification(tampered, user=user)


def test_decode_v3_notification_raises_on_bad_priv_params_length() -> None:
    user = _make_user(level="authPriv")
    sender_engine = _make_local_engine(0x77)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=106),
        local_engine=sender_engine,
    )
    view = decode_v3_message(raw)
    params = view.usm_params
    bad_usm = UsmParams(
        engine_id=params.engine_id,
        engine_boots=params.engine_boots,
        engine_time=params.engine_time,
        username=params.username,
        auth_params=b"\x00" * 12,
        priv_params=params.priv_params + b"\x99",
    )
    reencoded = encode_v3_message(
        msg_id=view.msg_id,
        msg_max_size=view.msg_max_size,
        flags=view.msg_flags[0],
        usm_params=bad_usm,
        msg_data_bytes=view.msg_data_bytes,
    )
    restamped = _restamp_auth(reencoded, user=user, engine_id=params.engine_id)

    with pytest.raises(ProtocolError, match="8 octets"):
        decode_v3_notification_message(restamped, user=user)


def test_decode_v3_notification_raises_on_malformed_ciphertext() -> None:
    user = _make_user(level="authPriv")
    sender_engine = _make_local_engine(0x88)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=107),
        local_engine=sender_engine,
    )
    view = decode_v3_message(raw)
    params = view.usm_params
    reencoded = encode_v3_message(
        msg_id=view.msg_id,
        msg_max_size=view.msg_max_size,
        flags=view.msg_flags[0],
        usm_params=UsmParams(
            engine_id=params.engine_id,
            engine_boots=params.engine_boots,
            engine_time=params.engine_time,
            username=params.username,
            auth_params=b"\x00" * 12,
            priv_params=params.priv_params,
        ),
        msg_data_bytes=encode_tlv(0x04, b""),
    )
    restamped = _restamp_auth(reencoded, user=user, engine_id=params.engine_id)

    with pytest.raises(ProtocolError):
        decode_v3_notification_message(restamped, user=user)


def test_is_discovery_probe_matches_usm_probe() -> None:
    probe = UsmModel(user=_make_user(level="noAuthNoPriv"))._build_discovery_probe()

    assert is_discovery_probe(probe) is True


def test_is_discovery_probe_rejects_regular_notification() -> None:
    user = _make_user(level="noAuthNoPriv")
    sender_engine = _make_local_engine(0x99)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=108),
        local_engine=sender_engine,
    )

    assert is_discovery_probe(raw) is False


def test_decode_notification_with_user_rejects_v2c_message() -> None:
    raw = encode_message(
        SnmpMessage(
            version=1,
            community="public",
            pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=123),
        )
    )

    with pytest.raises(ProtocolError, match="version 3"):
        decode_notification(raw, user=_make_user(level="noAuthNoPriv"))


def test_encode_discovery_report_shape() -> None:
    probe = UsmModel(user=_make_user(level="noAuthNoPriv"))._build_discovery_probe()
    probe_view = decode_v3_message(probe)
    _probe_engine_id, _probe_context, probe_pdu = decode_scoped_pdu(probe_view.msg_data_bytes)
    local_engine = _make_local_engine(0xAA, boots=12, time=345)

    report = encode_discovery_report(probe, local_engine=local_engine)
    view = decode_v3_message(report)
    context_engine_id, context_name, pdu_tag, request_id, error_status, error_index, varbinds = (
        _decode_report_scoped_pdu(view.msg_data_bytes)
    )

    assert view.msg_id == probe_view.msg_id
    assert view.msg_flags[0] == 0
    assert view.usm_params.engine_id == local_engine.engine_id
    assert view.usm_params.engine_boots == local_engine.engine_boots
    assert view.usm_params.engine_time == local_engine.engine_time
    assert view.usm_params.username == b""
    assert context_engine_id == b""
    assert context_name == b""
    assert pdu_tag == 0xA8
    assert request_id == probe_pdu.request_id
    assert error_status == 0
    assert error_index == 0
    assert len(varbinds) == 1
    assert varbinds[0].oid == _DISCOVERY_PROBE_OID
    assert isinstance(varbinds[0].value, Counter32Value)
    assert varbinds[0].value.value == 1


def test_encode_discovery_report_rejects_non_probe() -> None:
    user = _make_user(level="noAuthNoPriv")
    sender_engine = _make_local_engine(0xAB)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=109),
        local_engine=sender_engine,
    )

    with pytest.raises(ProtocolError, match="discovery probe"):
        encode_discovery_report(raw, local_engine=_make_local_engine(0xAC))


def test_encode_inform_response_authpriv_shape() -> None:
    user = _make_user(level="authPriv")
    receiver_engine = _make_local_engine(0xBA, boots=13, time=456)
    inform_pdu = _make_notification_pdu(PduType.INFORM_REQUEST, request_id=110)
    raw = _make_message(
        user=user,
        pdu=inform_pdu,
        context_name=b"ctx-name",
        peer_engine=receiver_engine,
    )
    envelope = decode_v3_notification_message(raw, user=user)
    assert envelope is not None

    response = encode_inform_response(envelope, user=user, local_engine=receiver_engine)
    view = decode_v3_message(response)
    response_model = UsmModel(user=user)
    response_model._engine_id = receiver_engine.engine_id
    response_model._engine_boots = receiver_engine.engine_boots
    response_model._engine_time = receiver_engine.engine_time
    unwrapped = response_model.unwrap_message(response)
    assert unwrapped is not None

    decrypted_scoped = UsmModel(user=user)._decrypt_scoped_pdu(
        view.msg_data_bytes,
        view.usm_params.priv_params,
        view.usm_params.engine_id,
        view.usm_params.engine_boots,
        view.usm_params.engine_time,
    )
    context_engine_id, context_name, decoded_response = decode_scoped_pdu(decrypted_scoped)

    assert view.msg_id == envelope.view.msg_id
    assert view.msg_flags[0] & MSG_FLAG_AUTH
    assert view.msg_flags[0] & MSG_FLAG_PRIV
    assert not (view.msg_flags[0] & MSG_FLAG_REPORTABLE)
    assert view.usm_params.engine_id == receiver_engine.engine_id
    assert view.usm_params.engine_boots == receiver_engine.engine_boots
    assert view.usm_params.engine_time == receiver_engine.engine_time
    assert unwrapped.pdu_type is PduType.RESPONSE
    assert unwrapped.request_id == inform_pdu.request_id
    assert context_engine_id == envelope.context_engine_id
    assert context_name == envelope.context_name
    assert decoded_response.request_id == inform_pdu.request_id
    assert decoded_response.varbinds == inform_pdu.varbinds


def test_encode_inform_response_rejects_non_inform() -> None:
    user = _make_user(level="noAuthNoPriv")
    sender_engine = _make_local_engine(0xBB)
    raw = _make_message(
        user=user,
        pdu=_make_notification_pdu(PduType.SNMPV2_TRAP, request_id=111),
        local_engine=sender_engine,
    )
    envelope = decode_v3_notification_message(raw, user=user)
    assert envelope is not None

    with pytest.raises(ProtocolError, match="INFORM-REQUEST"):
        encode_inform_response(envelope, user=user, local_engine=_make_local_engine(0xBC))
