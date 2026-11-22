from benlink import protocol as p


def test_register_notification_reply_decodes_as_raw_bytes():
    # Seen on a UV-Pro (fw 0.9.3) after REGISTER_NOTIFICATION; used to raise
    # "RegisterNotification cannot be a reply".
    reply = bytes.fromhex("00028006") + b"\x00\x02"
    msg = p.Message.from_bytes(reply)
    assert msg.is_reply
    assert msg.command == p.BasicCommand.REGISTER_NOTIFICATION
    assert msg.body == b"\x00\x02"


def test_event_type_names_are_separate_and_all_map_to_the_protocol_enum():
    import typing as t

    from benlink.command import EventType, EnableEvent, command_message_to_protocol

    names = t.get_args(EventType)
    assert "RINGING_STOPPED" in names and "RADIO_STATUS_CHANGED" in names
    for name in names:
        msg = command_message_to_protocol(EnableEvent(name))
        assert msg.body.event_type.name in (name, "POSITION_CHANGE")
