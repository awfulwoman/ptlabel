"""Decode a raster job back into its commands, for asserting on what we send."""

from dataclasses import dataclass, field

import packbits


@dataclass
class Page:
    info: bytes = b""
    mode: int | None = None
    cut_every: int | None = None
    advanced: int | None = None
    margin: int | None = None
    compression: int | None = None
    rows: list[bytes] = field(default_factory=list)
    end: int | None = None

    @property
    def page_flag(self) -> int:
        return self.info[8]

    @property
    def raster_count(self) -> int:
        return int.from_bytes(self.info[4:8], "little")


@dataclass
class Job:
    inits: int = 0
    pages: list[Page] = field(default_factory=list)


def parse_job(data: bytes) -> Job:
    job, page, i = Job(), Page(), 0
    while i < len(data):
        b = data[i]
        if b == 0x00:
            i += 1
        elif data[i : i + 2] == b"\x1b@":
            job.inits += 1
            i += 2
        elif data[i : i + 4] == b"\x1bia\x01":
            i += 4
        elif data[i : i + 3] == b"\x1biz":
            page.info = data[i + 3 : i + 13]
            i += 13
        elif data[i : i + 3] == b"\x1biM":
            page.mode = data[i + 3]
            i += 4
        elif data[i : i + 3] == b"\x1biA":
            page.cut_every = data[i + 3]
            i += 4
        elif data[i : i + 3] == b"\x1biK":
            page.advanced = data[i + 3]
            i += 4
        elif data[i : i + 3] == b"\x1bid":
            page.margin = data[i + 3] + data[i + 4] * 256
            i += 5
        elif b == 0x4D:
            page.compression = data[i + 1]
            i += 2
        elif b == 0x5A:
            page.rows.append(bytes(16))
            i += 1
        elif b == 0x47:
            n = data[i + 1] + data[i + 2] * 256
            chunk = data[i + 3 : i + 3 + n]
            page.rows.append(packbits.decode(chunk) if page.compression == 2 else chunk)
            i += 3 + n
        elif b in (0x0C, 0x1A):
            page.end = b
            job.pages.append(page)
            page = Page()
            i += 1
        else:
            raise ValueError(f"unknown byte {b:#x} at {i}")
    return job
