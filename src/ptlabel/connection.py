"""Talk to the printer through the kernel's usblp device (/dev/usb/lp0).

ptouch's own USB connection detaches the kernel driver and needs root or a udev rule;
the usblp device only needs membership of the lp group.
"""

import os
import select

from ptouch.connection import Connection


class DeviceConnection(Connection):
    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: int | None = None

    def connect(self, printer=None) -> None:
        if self._fd is None:
            self._fd = os.open(self.path, os.O_RDWR)

    def write(self, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            view = view[os.write(self._fd, view) :]

    def read(self, num_bytes: int = 32, timeout: float | None = None) -> bytes:
        ready, _, _ = select.select([self._fd], [], [], timeout)
        return os.read(self._fd, num_bytes) if ready else b""

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


class FileConnection(Connection):
    """Dry run: write the job to a file instead of a printer."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._f = None

    def connect(self, printer=None) -> None:
        if self._f is None:
            self._f = open(self.path, "wb")  # noqa: SIM115 - held open until close()

    def write(self, payload: bytes) -> None:
        self._f.write(payload)

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None
