from __future__ import annotations
from .bitfield import Bitfield, bf_int_enum, bf_dyn, bf_bytes
from .common import ReplyStatus

# GET_APRS_PATH (72) / SET_APRS_PATH (71). Format from HTCommander
# (src/lib/radio/radio.dart, getAprsPath / setAprsPath / _handleGetAprsPath):
# GET has no body; its reply is a status byte, then the path (a comma-separated
# digipeater path such as "WIDE1-1,WIDE2-1") as UTF-8 to the end of the frame,
# maybe NUL-padded. SET sends the path as UTF-8 with no length and no padding.
# The radio's maximum path length is not known.


class GetAprsPathBody(Bitfield):
    pass


class GetAprsPathReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
    path: bytes = bf_dyn(lambda _, n: bf_bytes(n // 8))


class SetAprsPathBody(Bitfield):
    path: bytes = bf_dyn(lambda _, n: bf_bytes(n // 8))


class SetAprsPathReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
    rest: bytes = bf_dyn(lambda _, n: bf_bytes(n // 8), default=b"")
