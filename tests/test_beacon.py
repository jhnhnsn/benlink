import asyncio
import typing as t

import pytest

from benlink import protocol as p
from benlink.command import (
    BeaconSettings,
    CommandConnection,
    GetAprsPath,
    GetAprsPathReply,
    MessageReplyError,
    SetAprsPath,
    SetAprsPathReply,
    command_message_to_protocol,
    radio_message_from_protocol,
)

_COMMON = dict(
    max_fwd_times=3,
    time_to_live=5,
    ptt_release_send_location=True,
    ptt_release_send_id_info=False,
    ptt_release_send_bss_user_id=True,
    should_share_location=True,
    send_pwr_voltage=False,
    packet_format=p.PacketFormat.APRS,
    allow_position_check=True,
    aprs_ssid=9,
    smart_beacon_en=True,
    mic_e_en=True,
    send_id_by_aprs=True,
    location_share_interval=120,
    bss_user_id_lower=0x01020304,
    ptt_release_id_info="ID INFO",
    beacon_message="hello",
    aprs_symbol="/>",
    aprs_callsign="N0CALL",
    bss_user_id_upper=0x05060708,
)


def _v1() -> p.BSSSettings:
    return p.BSSSettings(**_COMMON, _unk_bss_0=True, _unk_bss_1=1)


def _v2() -> p.BSSSettingsV2:
    return p.BSSSettingsV2(
        **_COMMON, _unk_bss_0=True, _unk_bss_1=1,
        smart_beacon_min_interval=6, smart_beacon_max_interval=17, _unk_bss_2=0x55,
    )


@pytest.mark.parametrize("record", [_v1(), _v2()], ids=["v1", "v2"])
def test_read_then_write_keeps_every_bit(record):
    model = BeaconSettings.from_protocol(record)
    assert model.to_protocol().to_bytes() == record.to_bytes()


def test_public_model_has_the_smart_beacon_fields():
    model = BeaconSettings.from_protocol(_v2())
    assert model.smart_beacon_en is True
    assert model.mic_e_en is True
    assert model.send_id_by_aprs is True
    assert model.smart_beacon_min_interval == 6
    assert model.smart_beacon_max_interval == 17


def test_write_size_follows_the_record_the_radio_sent():
    v1 = BeaconSettings.from_protocol(_v1())
    v2 = BeaconSettings.from_protocol(_v2())
    assert v1.smart_beacon_min_interval is None and v1.smart_beacon_max_interval is None
    assert type(v1.to_protocol()) is p.BSSSettings
    assert len(v1.to_protocol().to_bytes()) == 50
    assert type(v2.to_protocol()) is p.BSSSettingsV2
    assert len(v2.to_protocol().to_bytes()) == 52


def test_write_message_uses_the_record_size():
    from benlink.command import SetBeaconSettings

    for record, size in ((_v1(), 50), (_v2(), 52)):
        msg = command_message_to_protocol(SetBeaconSettings(BeaconSettings.from_protocol(record)))
        assert len(msg.to_bytes()) == 4 + size


@pytest.mark.parametrize("record", [_v1(), _v2()], ids=["v1", "v2"])
def test_json_dump_and_validate_keep_every_bit(record):
    # Backups store model_dump(mode="json"); a restore validates it and writes it.
    model = BeaconSettings.from_protocol(record)
    again = BeaconSettings.model_validate(model.model_dump(mode="json"))
    assert again == model
    assert again.to_protocol().to_bytes() == record.to_bytes()


def test_a_dump_from_before_the_new_fields_still_validates():
    old = BeaconSettings.from_protocol(_v1()).model_dump(mode="json")
    for key in ("smart_beacon_en", "mic_e_en", "send_id_by_aprs", "smart_beacon_min_interval",
                "smart_beacon_max_interval", "reserved_0", "reserved_1", "reserved_2"):
        old.pop(key)
    model = BeaconSettings.model_validate(old)
    assert model.smart_beacon_en is False
    assert type(model.to_protocol()) is p.BSSSettings


def test_reply_decodes_into_the_full_model():
    raw = bytes.fromhex("00028021") + b"\x00" + _v2().to_bytes()
    reply = radio_message_from_protocol(p.Message.from_bytes(raw))
    assert reply.tnc_settings == BeaconSettings.from_protocol(_v2())


# APRS path (GET_APRS_PATH 72 / SET_APRS_PATH 71), format from HTCommander:
# GET has no body; its reply is a status byte, then the path as UTF-8 to the end
# of the frame (maybe NUL-padded). SET sends the path as UTF-8 with no padding.


def test_get_aprs_path_request_has_no_body():
    msg = command_message_to_protocol(GetAprsPath())
    assert msg.to_bytes() == bytes.fromhex("00020048")


def test_set_aprs_path_request_is_the_path_in_utf8():
    msg = command_message_to_protocol(SetAprsPath("WIDE1-1,WIDE2-1"))
    assert msg.to_bytes() == bytes.fromhex("00020047") + b"WIDE1-1,WIDE2-1"


def test_get_aprs_path_reply_strips_nul_padding():
    raw = bytes.fromhex("00028048") + b"\x00" + b"WIDE1-1,WIDE2-1\x00\x00\x00"
    reply = radio_message_from_protocol(p.Message.from_bytes(raw))
    assert reply == GetAprsPathReply("WIDE1-1,WIDE2-1")


def test_get_aprs_path_reply_with_an_error_status():
    raw = bytes.fromhex("00028048") + b"\x01"
    reply = radio_message_from_protocol(p.Message.from_bytes(raw))
    assert isinstance(reply, MessageReplyError) and reply.reason == "NOT_SUPPORTED"


def test_set_aprs_path_reply():
    ok = radio_message_from_protocol(p.Message.from_bytes(bytes.fromhex("00028047") + b"\x00"))
    assert ok == SetAprsPathReply()
    bad = radio_message_from_protocol(p.Message.from_bytes(bytes.fromhex("00028047") + b"\x05"))
    assert isinstance(bad, MessageReplyError) and bad.reason == "INVALID_PARAMETER"


class ReplyLink:
    """A link that answers each request with a fixed reply, by command."""

    def __init__(self, replies: dict[p.BasicCommand, bytes]) -> None:
        self.replies = replies
        self.sent: list[p.Message] = []
        self.callback: t.Callable[[p.Message], None] | None = None

    def is_connected(self) -> bool:
        return True

    async def send_bytes(self, data: bytes) -> None:
        pass

    async def send(self, msg: p.Message) -> None:
        self.sent.append(msg)
        assert self.callback is not None
        reply = p.Message.from_bytes(self.replies[msg.command])
        asyncio.get_running_loop().call_soon(self.callback, reply)

    async def connect(self, callback: t.Callable[[p.Message], None]) -> None:
        self.callback = callback

    async def disconnect(self) -> None:
        pass


def test_connection_gets_and_sets_the_aprs_path():
    link = ReplyLink({
        p.BasicCommand.GET_APRS_PATH: bytes.fromhex("00028048") + b"\x00WIDE2-1\x00",
        p.BasicCommand.SET_APRS_PATH: bytes.fromhex("00028047") + b"\x00",
    })

    async def go():
        conn = CommandConnection(link, reply_timeout=1)
        await conn.connect()
        assert await conn.get_aprs_path() == "WIDE2-1"
        await conn.set_aprs_path("WIDE1-1,WIDE2-1")
        assert link.sent[-1].to_bytes() == bytes.fromhex("00020047") + b"WIDE1-1,WIDE2-1"

    asyncio.run(go())


def test_set_aprs_path_error_raises():
    link = ReplyLink({p.BasicCommand.SET_APRS_PATH: bytes.fromhex("00028047") + b"\x05"})

    async def go():
        conn = CommandConnection(link, reply_timeout=1)
        await conn.connect()
        with pytest.raises(ValueError, match="INVALID_PARAMETER"):
            await conn.set_aprs_path("WIDE1-1")

    asyncio.run(go())


def test_controller_fetch_and_write_beacon_settings_and_path():
    from benlink.controller import RadioController

    record = _v2()
    link = ReplyLink({
        p.BasicCommand.READ_BSS_SETTINGS: bytes.fromhex("00028021") + b"\x00" + record.to_bytes(),
        p.BasicCommand.WRITE_BSS_SETTINGS: bytes.fromhex("00028022") + b"\x00",
        p.BasicCommand.GET_APRS_PATH: bytes.fromhex("00028048") + b"\x00WIDE1-1",
        p.BasicCommand.SET_APRS_PATH: bytes.fromhex("00028047") + b"\x00",
    })
    radio = RadioController(CommandConnection(link, reply_timeout=1))

    async def go():
        await radio._conn.connect()
        radio._state = t.cast(t.Any, type("S", (), {"beacon_settings": None})())
        bs = await radio.fetch_beacon_settings()
        assert bs == BeaconSettings.from_protocol(record)
        assert radio.beacon_settings == bs
        new = bs.model_copy(update={"location_share_interval": 300})
        await radio.write_beacon_settings(new)
        assert radio.beacon_settings == new
        sent = link.sent[-1].to_bytes()
        assert sent[:4] == bytes.fromhex("00020022") and len(sent) == 4 + 52
        assert await radio.fetch_aprs_path() == "WIDE1-1"
        await radio.write_aprs_path("WIDE2-1")
        assert link.sent[-1].to_bytes() == bytes.fromhex("00020047") + b"WIDE2-1"

    asyncio.run(go())
