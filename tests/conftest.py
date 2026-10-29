import sys
from pathlib import Path

import pytest
from ptouch.connection import Connection

sys.path.insert(0, str(Path(__file__).parent))


class MemoryConnection(Connection):
    """Captures everything written; replays canned status packets on read."""

    def __init__(self, replies: list[bytes] | None = None) -> None:
        self.written = bytearray()
        self.replies = list(replies or [])

    def connect(self, printer=None) -> None:
        pass

    def write(self, payload: bytes) -> None:
        self.written += payload

    def read(self, num_bytes: int = 32, timeout: float | None = None) -> bytes:
        return self.replies.pop(0) if self.replies else b""

    def close(self) -> None:
        pass


@pytest.fixture
def conn():
    return MemoryConnection()


def status_packet(*, status_type=0x00, width=24, media=0x01, err1=0, err2=0, phase=0x00) -> bytes:
    p = bytearray(32)
    p[0:6] = b"\x80\x20B0f0"
    p[8], p[9], p[10], p[11] = err1, err2, width, media
    p[18], p[19] = status_type, phase
    return bytes(p)
