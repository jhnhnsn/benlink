import asyncio
import typing as t

import pytest

from benlink import protocol as p
from benlink.command import (
    CommandConnection,
    GetVolume,
    GetVolumeReply,
    MessageReplyError,
    SetVolume,
    SetVolumeReply,
    command_message_to_protocol,
    radio_message_from_protocol,
)

# GET_VOLUME (22) / SET_VOLUME (23), format from HTCommander: GET has no body;
# its reply is a status byte and the level (0-15). SET sends the level in one
# byte; its reply is a status byte.


def test_get_volume_request_has_no_body():
    assert command_message_to_protocol(GetVolume()).to_bytes() == bytes.fromhex("00020016")


@pytest.mark.parametrize("level", [0, 7, 15])
def test_set_volume_request_is_the_level_in_one_byte(level):
    msg = command_message_to_protocol(SetVolume(level))
    assert msg.to_bytes() == bytes.fromhex("00020017") + bytes([level])


def test_get_volume_reply():
    raw = bytes.fromhex("00028016") + b"\x00\x09"
    assert radio_message_from_protocol(p.Message.from_bytes(raw)) == GetVolumeReply(9)


def test_get_volume_reply_with_an_error_status_and_no_level():
    raw = bytes.fromhex("00028016") + b"\x01"
    reply = radio_message_from_protocol(p.Message.from_bytes(raw))
    assert isinstance(reply, MessageReplyError) and reply.reason == "NOT_SUPPORTED"


def test_get_volume_reply_success_without_a_level_is_an_error():
    raw = bytes.fromhex("00028016") + b"\x00"
    reply = radio_message_from_protocol(p.Message.from_bytes(raw))
    assert isinstance(reply, MessageReplyError)


def test_set_volume_reply():
    ok = radio_message_from_protocol(p.Message.from_bytes(bytes.fromhex("00028017") + b"\x00"))
    assert ok == SetVolumeReply()
    bad = radio_message_from_protocol(p.Message.from_bytes(bytes.fromhex("00028017") + b"\x05"))
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


def test_connection_gets_and_sets_the_volume():
    link = ReplyLink({
        p.BasicCommand.GET_VOLUME: bytes.fromhex("00028016") + b"\x00\x04",
        p.BasicCommand.SET_VOLUME: bytes.fromhex("00028017") + b"\x00",
    })

    async def go():
        conn = CommandConnection(link, reply_timeout=1)
        await conn.connect()
        assert await conn.get_volume() == 4
        await conn.set_volume(12)
        assert link.sent[-1].to_bytes() == bytes.fromhex("00020017") + b"\x0c"

    asyncio.run(go())


@pytest.mark.parametrize("level", [-1, 16])
def test_set_volume_out_of_range_sends_nothing(level):
    link = ReplyLink({})

    async def go():
        conn = CommandConnection(link, reply_timeout=1)
        await conn.connect()
        with pytest.raises(ValueError, match="0-15"):
            await conn.set_volume(level)
        assert link.sent == []

    asyncio.run(go())


def test_set_volume_error_raises():
    link = ReplyLink({p.BasicCommand.SET_VOLUME: bytes.fromhex("00028017") + b"\x05"})

    async def go():
        conn = CommandConnection(link, reply_timeout=1)
        await conn.connect()
        with pytest.raises(ValueError, match="INVALID_PARAMETER"):
            await conn.set_volume(3)

    asyncio.run(go())


def test_controller_fetch_and_write_volume():
    from benlink.controller import RadioController

    link = ReplyLink({
        p.BasicCommand.GET_VOLUME: bytes.fromhex("00028016") + b"\x00\x0f",
        p.BasicCommand.SET_VOLUME: bytes.fromhex("00028017") + b"\x00",
    })
    radio = RadioController(CommandConnection(link, reply_timeout=1))

    async def go():
        await radio._conn.connect()
        radio._state = t.cast(t.Any, object())
        assert await radio.fetch_volume() == 15
        await radio.write_volume(0)
        assert link.sent[-1].to_bytes() == bytes.fromhex("00020017") + b"\x00"

    asyncio.run(go())
