from benlink import protocol as p


def test_register_notification_reply_decodes_as_raw_bytes():
    # Seen on a UV-Pro (fw 0.9.3) after REGISTER_NOTIFICATION; used to raise
    # "RegisterNotification cannot be a reply".
    reply = bytes.fromhex("00028006") + b"\x00\x02"
    msg = p.Message.from_bytes(reply)
    assert msg.is_reply
    assert msg.command == p.BasicCommand.REGISTER_NOTIFICATION
    assert msg.body == b"\x00\x02"
