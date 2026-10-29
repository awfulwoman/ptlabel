import pytest
from jobparse import parse_job
from PIL import Image
from ptouch.label import Label
from ptouch.tape import HeatShrinkTube11_7mm, Tape12mm, Tape24mm

from ptlabel.batch import BatchPrinter


def labels(n, width=40, tape=Tape24mm):
    img = Image.new("RGB", (width, 128), "white")
    img.paste((0, 0, 0), (0, 0, width // 2, 128))
    return [Label(img, tape) for _ in range(n)]


def printed(conn, items, **kw):
    BatchPrinter(conn).print_batch(items, **kw)
    return parse_job(bytes(conn.written))


def test_initialises_once(conn):
    job = printed(conn, labels(3))
    assert job.inits == 1
    assert len(job.pages) == 3


def test_page_flags_and_print_commands(conn):
    job = printed(conn, labels(3))
    assert [p.page_flag for p in job.pages] == [0, 1, 1]
    assert [p.end for p in job.pages] == [0x0C, 0x0C, 0x1A]


def test_verified_settings_default_half_cut(conn):
    """Sequence proven on a real PT-E550W: auto-cut, cut once at the end, half-cut, no chain."""
    for p in printed(conn, labels(3)).pages:
        assert p.info[:3] == bytes([0x86, 0x01, 24])
        assert p.raster_count == 40
        assert p.mode == 0x40
        assert p.cut_every == 3
        assert p.advanced == 0x0C
        assert p.margin == 14
        assert p.compression == 2


def test_raster_content_survives(conn):
    page = printed(conn, labels(1)).pages[0]
    assert len(page.rows) == 40
    assert page.rows[0] == b"\xff" * 16
    assert page.rows[-1] == bytes(16)


def test_full_cuts_only(conn):
    assert printed(conn, labels(2), half_cut=False).pages[0].advanced == 0x08


def test_chain_leaves_last_label_in_printer(conn):
    assert printed(conn, labels(2), chain=True).pages[0].advanced == 0x04


def test_cut_every(conn):
    assert printed(conn, labels(4), cut_every=2).pages[0].cut_every == 2


def test_cut_every_caps_at_99(conn):
    assert printed(conn, labels(120, width=2)).pages[0].cut_every == 99


@pytest.mark.parametrize("bad", [0, 100])
def test_cut_every_range(conn, bad):
    with pytest.raises(ValueError):
        printed(conn, labels(2), cut_every=bad)


def test_margin(conn):
    assert printed(conn, labels(1), margin_mm=5).pages[0].margin == 35


def test_narrow_laminated_tape(conn):
    img = Image.new("RGB", (10, 70), "white")
    p = printed(conn, [Label(img, Tape12mm)]).pages[0]
    assert p.info[:3] == bytes([0x86, 0x01, 12])


def test_heat_shrink_keeps_its_media_type(conn):
    img = Image.new("RGB", (10, 66), "white")
    p = printed(conn, [Label(img, HeatShrinkTube11_7mm)]).pages[0]
    assert p.info[1] == 0x11


def test_empty_batch(conn):
    with pytest.raises(ValueError):
        printed(conn, [])
