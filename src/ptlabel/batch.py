"""Gapless multi-label jobs for the PT-E550W.

ptouch's own print_multi() turns auto-cut off, always sends page flag 0 and forces chain
printing off. This sends the sequence verified on a real PT-E550W instead: one job,
one page per label, TIFF compression, half-cuts between labels and a full cut every
`cut_every` labels (the last label by default).
"""

from ptouch.label import Label
from ptouch.printer import MediaType
from ptouch.printers import PTE550W
from ptouch.tape import HeatShrinkTube, Tape

MAX_CUT_EVERY = 99  # ESC i A accepts 1-99
PAGE_FLAG_OFFSET = 11  # byte n9 within the ESC i z command


class BatchPrinter(PTE550W):
    def _get_media_type(self, tape: Tape) -> MediaType:
        if isinstance(tape, HeatShrinkTube):
            return super()._get_media_type(tape)
        return MediaType.LAMINATED_TAPE

    def _page(
        self,
        label: Label,
        *,
        first: bool,
        last: bool,
        margin_dots: int,
        half_cut: bool,
        cut_every: int,
        chain: bool,
    ) -> bytes:
        config = self.get_tape_config(label.tape)
        label.prepare(config.print_pins, self.RESOLUTION_DPI)
        lines = label.image.width
        raster = self._generate_raster(self._prepare_image(label.image, config), config)

        info = bytearray(
            self._cmd_print_information(
                lines, self._get_media_type(label.tape), label.tape.width_mm
            )
        )
        info[PAGE_FLAG_OFFSET] = 0 if first else 1
        return (
            self._cmd_raster_mode()
            + bytes(info)
            + self._cmd_mode_settings(auto_cut=True)
            + self._cmd_page_number_cuts(pages=cut_every)
            + self._cmd_advanced_mode_settings(half_cut=half_cut, chain_printing=chain)
            + self._cmd_margin(margin_dots)
            + self._cmd_set_compression(tiff_compression=True)
            + self._build_raster_data(raster, lines, high_resolution=False)
            + (b"\x1a" if last else b"\x0c")
        )

    def print_batch(
        self,
        labels: list[Label],
        *,
        half_cut: bool = True,
        cut_every: int | None = None,
        margin_mm: float = 2.0,
        chain: bool = False,
    ) -> None:
        """Send all labels as one job. Chain leaves the last label in the printer."""
        if not labels:
            raise ValueError("no labels to print")
        if cut_every is None:
            cut_every = min(len(labels), MAX_CUT_EVERY)
        if not 1 <= cut_every <= MAX_CUT_EVERY:
            raise ValueError(f"cut_every must be 1-{MAX_CUT_EVERY}, got {cut_every}")
        if not self.MIN_MARGIN_MM <= margin_mm <= self.MAX_MARGIN_MM:
            raise ValueError(f"margin must be {self.MIN_MARGIN_MM}-{self.MAX_MARGIN_MM}mm")

        margin_dots = self._mm_to_dots(margin_mm)
        last = len(labels) - 1
        for i, label in enumerate(labels):
            self.connection.write(
                self._page(
                    label,
                    first=i == 0,
                    last=i == last,
                    margin_dots=margin_dots,
                    half_cut=half_cut,
                    cut_every=cut_every,
                    chain=chain,
                )
            )
