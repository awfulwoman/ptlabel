import pytest
from conftest import MemoryConnection, status_packet
from ptouch.tape import Tape3_5mm, Tape12mm, Tape24mm

from ptlabel.status import (
    PrinterError,
    parse_status,
    query_status,
    tape_for_status,
    wait_for_completion,
)


def test_parse_reply_reports_media():
    s = parse_status(status_packet(width=24, media=0x01))
    assert s.media_width_mm == 24
    assert s.media_type == 0x01
    assert s.errors == []
    assert s.status_type == 0x00


def test_parse_real_packet_from_printer():
    real = bytes.fromhex(
        "80 20 42 30 66 30 00 00 00 00 18 01 00 00 00 00"
        " 00 00 00 00 00 00 00 00 91 08 00 00 00 00 00 00"
    )
    s = parse_status(real)
    assert s.model == "PT-E550W"
    assert s.media_width_mm == 24
    assert s.media_name == "Laminated tape"
    assert s.tape_colour == "Yellow (Flex. ID)"
    assert s.text_colour == "Black"


def test_unknown_codes_still_named():
    p = bytearray(status_packet(media=0x42))
    p[24], p[25] = 0x77, 0x33
    s = parse_status(bytes(p))
    assert s.media_name == "unknown (0x42)"
    assert s.tape_colour == "unknown (0x77)"
    assert s.text_colour == "unknown (0x33)"


def test_parse_errors_named():
    s = parse_status(status_packet(err1=0x01, err2=0x10))
    assert "no media" in s.errors
    assert "cover open" in s.errors


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_status(b"\x00" * 32)
    with pytest.raises(ValueError):
        parse_status(b"\x80\x20")


@pytest.mark.parametrize("width,tape", [(4, Tape3_5mm), (12, Tape12mm), (24, Tape24mm)])
def test_tape_for_status(width, tape):
    assert isinstance(tape_for_status(parse_status(status_packet(width=width))), tape)


def test_tape_for_status_no_tape():
    with pytest.raises(PrinterError):
        tape_for_status(parse_status(status_packet(width=0, media=0x00)))


def test_query_status_sends_request_and_parses():
    c = MemoryConnection([status_packet(width=12)])
    s = query_status(c)
    assert c.written.endswith(b"\x1b@\x1biS")
    assert s.media_width_mm == 12


def test_wait_counts_completions_and_reports_progress():
    c = MemoryConnection(
        [
            status_packet(status_type=0x06, phase=0x01),
            status_packet(status_type=0x01),
            status_packet(status_type=0x06),
            status_packet(status_type=0x01),
        ]
    )
    seen = []
    wait_for_completion(c, 2, on_progress=seen.append, timeout=1)
    assert seen == [1, 2]
    assert c.written == b""  # never talk to the printer mid-job


def test_wait_raises_on_error_packet():
    c = MemoryConnection([status_packet(status_type=0x02, err1=0x04)])
    with pytest.raises(PrinterError, match="cutter jam"):
        wait_for_completion(c, 1, timeout=1)


def test_wait_times_out_when_silent():
    with pytest.raises(PrinterError, match="timed out"):
        wait_for_completion(MemoryConnection(), 1, timeout=0.2)
