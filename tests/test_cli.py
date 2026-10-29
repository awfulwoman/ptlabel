import pytest
from conftest import MemoryConnection, status_packet
from jobparse import parse_job
from PIL import Image

from ptlabel import cli
from ptlabel.connection import DeviceConnection


@pytest.fixture
def csvfile(tmp_path):
    p = tmp_path / "items.csv"
    p.write_text("name,tag\nAlice,A1\nBob,B2\nCarol,C3\n")
    return p


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "pic.png"
    Image.new("RGB", (60, 200), "black").save(p)
    return p


def run_dry(tmp_path, *args):
    out = tmp_path / "job.bin"
    assert cli.main([*args, "--tape", "24", "--output", str(out)]) == 0
    return parse_job(out.read_bytes())


def test_csv_one_page_per_row(tmp_path, csvfile):
    job = run_dry(tmp_path, "csv", str(csvfile), "--template", "{name}\\n{tag}")
    assert len(job.pages) == 3
    assert job.pages[0].advanced == 0x0C  # half-cut, no chain


def test_images_with_copies(tmp_path, image):
    job = run_dry(tmp_path, "images", str(image), str(image), "--copies", "2")
    assert len(job.pages) == 4
    assert job.pages[0].raster_count == round(200 * 128 / 60)


def test_full_cut_and_chain_flags(tmp_path, image):
    job = run_dry(tmp_path, "images", str(image), "--cut", "full", "--chain")
    assert job.pages[0].advanced == 0x00


def test_cut_every_and_margin(tmp_path, csvfile):
    job = run_dry(tmp_path, "csv", str(csvfile), "--cut-every", "2", "--margin", "3")
    assert job.pages[0].cut_every == 2
    assert job.pages[0].margin == 21


def test_narrow_tape_uses_its_print_area(tmp_path, csvfile):
    out = tmp_path / "job.bin"
    cli.main(["csv", str(csvfile), "--tape", "12", "--output", str(out)])
    page = parse_job(out.read_bytes()).pages[0]
    assert page.info[2] == 12
    # 12mm tape prints on pins 29..98 only
    assert all(row[:3] == b"\x00\x00\x00" for row in page.rows)


def test_preview_writes_pngs(tmp_path, csvfile):
    prev = tmp_path / "prev"
    run_dry(tmp_path, "csv", str(csvfile), "--preview", str(prev))
    assert sorted(p.name for p in prev.iterdir()) == ["0001.png", "0002.png", "0003.png"]


def test_print_detects_tape_and_waits(monkeypatch, csvfile, capsys):
    conn = MemoryConnection([status_packet(width=24)] + [status_packet(status_type=0x01)] * 3)
    monkeypatch.setattr(cli, "DeviceConnection", lambda path: conn)
    assert cli.main(["csv", str(csvfile)]) == 0
    job = parse_job(bytes(conn.written).split(b"\x1biS", 1)[1])
    assert len(job.pages) == 3
    assert "3/3" in capsys.readouterr().err


def test_print_reports_printer_error(monkeypatch, csvfile, capsys):
    conn = MemoryConnection([status_packet(err2=0x10)])
    monkeypatch.setattr(cli, "DeviceConnection", lambda path: conn)
    assert cli.main(["csv", str(csvfile)]) == 1
    assert "cover open" in capsys.readouterr().err


def test_status_command(monkeypatch, capsys):
    conn = MemoryConnection([status_packet(width=18)])
    monkeypatch.setattr(cli, "DeviceConnection", lambda path: conn)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "18mm Laminated tape" in out
    assert "tape colour: White" in out
    assert "text colour: Black" in out


def test_permission_error_is_explained(tmp_path, capsys):
    dev = tmp_path / "lp0"
    dev.write_bytes(b"")
    dev.chmod(0)
    assert cli.main(["status", "--printer", str(dev)]) == 1
    assert "lp group" in capsys.readouterr().err


def test_device_connection_roundtrip(tmp_path):
    dev = tmp_path / "fake"
    dev.write_bytes(b"")
    c = DeviceConnection(str(dev))
    c.connect(None)
    c.connect(None)  # idempotent
    c.write(b"abc")
    c.close()
    assert dev.read_bytes() == b"abc"
