import asyncio
import typing as t

import pytest

from benlink import protocol as p
from benlink.command import CommandConnection, GetSettings


class SilentLink:
    """A link that accepts writes and never replies (like a reply that failed to decode)."""

    def __init__(self) -> None:
        self.sent: list[p.Message] = []
        self.callback: t.Callable[[p.Message], None] | None = None

    def is_connected(self) -> bool:
        return True

    async def send_bytes(self, data: bytes) -> None:
        pass

    async def send(self, msg: p.Message) -> None:
        self.sent.append(msg)

    async def connect(self, callback: t.Callable[[p.Message], None]) -> None:
        self.callback = callback

    async def disconnect(self) -> None:
        pass


def test_request_without_reply_times_out_and_removes_its_handler():
    async def go():
        conn = CommandConnection(SilentLink(), reply_timeout=0.05)
        await conn.connect()
        with pytest.raises(TimeoutError):
            await conn.get_settings()
        assert conn._handlers == []

    asyncio.run(go())


def test_getsettings_message_is_sent():
    async def go():
        link = SilentLink()
        conn = CommandConnection(link, reply_timeout=0.01)
        await conn.connect()
        with pytest.raises(TimeoutError):
            await conn.send_message_expect_reply(GetSettings(), object)  # type: ignore[arg-type]
        assert link.sent and link.sent[0].command == p.BasicCommand.READ_SETTINGS

    asyncio.run(go())


def test_ble_link_accepts_a_bledevice_and_disconnect_callback():
    from bleak.backends.device import BLEDevice

    from benlink.controller import RadioController

    seen = []
    dev = BLEDevice("00:11:22:33:44:55", "UV-PRO", {"path": "/org/bluez/hci0/dev_00_11_22_33_44_55", "props": {}})
    radio = RadioController.new_ble(dev, disconnected_callback=seen.append, reply_timeout=5)
    link = radio._conn._link
    assert link._client.address == "00:11:22:33:44:55"
    assert radio._conn._reply_timeout == 5


def test_fetch_and_write_need_a_connected_radio():
    from benlink.controller import RadioController, StateNotInitializedError

    radio = RadioController(CommandConnection(SilentLink()))

    async def go():
        with pytest.raises(StateNotInitializedError):
            await radio.fetch_settings()

    asyncio.run(go())
