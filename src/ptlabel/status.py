"""Printer status packets (32 bytes) per the Brother PT-E550W raster command reference.

Only query status while the printer is idle. During a job the printer sends packets
on its own; sending anything then (even ESC @ / ESC i S) aborts the job.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ptouch.tape import Tape, Tape3_5mm, Tape6mm, Tape9mm, Tape12mm, Tape18mm, Tape24mm

MODELS = {0x66: "PT-E550W", 0x68: "PT-P750W"}
ERRORS_1 = {
    0x01: "no media",
    0x04: "cutter jam",
    0x08: "weak batteries",
    0x40: "high-voltage adapter",
}
ERRORS_2 = {0x01: "wrong media", 0x10: "cover open", 0x20: "overheating"}
TAPES = {4: Tape3_5mm, 6: Tape6mm, 9: Tape9mm, 12: Tape12mm, 18: Tape18mm, 24: Tape24mm}

REPLY, PRINT_COMPLETE, ERROR, TURNED_OFF = 0x00, 0x01, 0x02, 0x04


class PrinterError(Exception):
    pass


@dataclass
class Status:
    model: str
    media_width_mm: int
    media_type: int
    status_type: int
    phase: int
    errors: list[str] = field(default_factory=list)


def parse_status(packet: bytes) -> Status:
    if len(packet) != 32 or packet[0:3] != b"\x80\x20B":
        raise ValueError(f"not a status packet: {packet.hex(' ')}")
    errors = [name for bit, name in ERRORS_1.items() if packet[8] & bit]
    errors += [name for bit, name in ERRORS_2.items() if packet[9] & bit]
    return Status(
        model=MODELS.get(packet[4], f"unknown ({packet[4]:#x})"),
        media_width_mm=packet[10],
        media_type=packet[11],
        status_type=packet[18],
        phase=packet[19],
        errors=errors,
    )


def tape_for_status(status: Status) -> Tape:
    if status.errors:
        raise PrinterError(", ".join(status.errors))
    if status.media_type in (0x00, 0xFF) or status.media_width_mm not in TAPES:
        raise PrinterError(
            f"unsupported or missing tape (width {status.media_width_mm}mm, "
            f"type {status.media_type:#x}); pass --tape for heat-shrink tube"
        )
    return TAPES[status.media_width_mm]()


def _read_packet(conn, deadline: float) -> bytes | None:
    buf = b""
    while len(buf) < 32:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        chunk = conn.read(32 - len(buf), timeout=min(remaining, 0.5))
        if not chunk:
            time.sleep(0.02)
        buf += chunk
    return buf


def query_status(conn, timeout: float = 3.0) -> Status:
    """Ask an idle printer for its status. Never call this during a job."""
    conn.write(b"\x00" * 100 + b"\x1b@\x1biS")
    packet = _read_packet(conn, time.monotonic() + timeout)
    if packet is None:
        raise PrinterError("no status reply from printer")
    return parse_status(packet)


def wait_for_completion(
    conn,
    expected: int,
    on_progress: Callable[[int], None] | None = None,
    timeout: float = 60.0,
) -> None:
    """Listen (without sending anything) until `expected` labels report printed.

    `timeout` is the longest silence allowed between packets.
    """
    done = 0
    deadline = time.monotonic() + timeout
    while done < expected:
        packet = _read_packet(conn, deadline)
        if packet is None:
            raise PrinterError(f"timed out after {done}/{expected} labels")
        deadline = time.monotonic() + timeout
        status = parse_status(packet)
        if status.status_type == PRINT_COMPLETE:
            done += 1
            if on_progress:
                on_progress(done)
        elif status.status_type in (ERROR, TURNED_OFF):
            reason = ", ".join(status.errors) or "printer turned off"
            raise PrinterError(f"{reason} after {done}/{expected} labels")
