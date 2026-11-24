from __future__ import annotations
from .bitfield import Bitfield, bf_int, bf_int_enum, bf_dyn, bf_bytes
from .common import ReplyStatus

# GET_VOLUME (22) / SET_VOLUME (23). Format from HTCommander: GET has no body;
# its reply is a status byte, then the volume level (0-15) in one byte. SET
# sends the level (0-15) in one byte; its reply is a status byte. An error reply
# may carry only the status byte, so the level is read as the rest of the frame.
# The volume knob sends no event, so the level is read on demand.


class GetVolumeBody(Bitfield):
    pass


class GetVolumeReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
    level: bytes = bf_dyn(lambda _, n: bf_bytes(n // 8), default=b"")


class SetVolumeBody(Bitfield):
    level: int = bf_int(8)


class SetVolumeReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
    rest: bytes = bf_dyn(lambda _, n: bf_bytes(n // 8), default=b"")
