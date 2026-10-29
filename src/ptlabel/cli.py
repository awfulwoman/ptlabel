"""ptlabel: batch-print CSV rows or images as one gapless job."""

import argparse
import os
import sys
from pathlib import Path

from PIL import Image
from ptouch.label import Label

from .batch import BatchPrinter
from .connection import DeviceConnection, FileConnection
from .render import csv_texts, fit_image, render_text
from .status import TAPES, PrinterError, query_status, tape_for_status, wait_for_completion

DEFAULT_PRINTER = "/dev/usb/lp0"
TAPE_CHOICES = {"3.5": 4, "6": 6, "9": 9, "12": 12, "18": 18, "24": 24}


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--printer",
        default=os.environ.get("PTLABEL_PRINTER", DEFAULT_PRINTER),
        help="printer device (env PTLABEL_PRINTER, default %(default)s)",
    )

    job = argparse.ArgumentParser(add_help=False, parents=[common])
    job.add_argument(
        "--tape", choices=TAPE_CHOICES, help="tape width in mm (default: ask the printer)"
    )
    job.add_argument(
        "--cut",
        choices=["half", "full"],
        default="half",
        help="cut between labels: half keeps the backing in one strip (default)",
    )
    job.add_argument(
        "--cut-every",
        type=int,
        help="full cut after every N labels, 1-99 (default: only after the last)",
    )
    job.add_argument(
        "--margin",
        type=float,
        default=2.0,
        help="blank tape each side of a label in mm, minimum 2 (default %(default)s)",
    )
    job.add_argument(
        "--chain",
        action="store_true",
        help="leave the last label in the printer so the next job wastes no leader",
    )
    job.add_argument("--output", help="dry run: write the raster job to this file")
    job.add_argument("--preview", help="save each label as a PNG in this directory")
    job.add_argument("--no-wait", action="store_true", help="don't wait for the printer to finish")

    p = argparse.ArgumentParser(prog="ptlabel", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="show printer and tape status")

    c = sub.add_parser("csv", parents=[job], help="one text label per CSV row")
    c.add_argument("file", help="CSV file with a header row, or - for stdin")
    c.add_argument("--template", help="e.g. '{name}\\n{tag}' (default: first column)")
    c.add_argument(
        "--font",
        default=os.environ.get("PTLABEL_FONT"),
        help="TrueType font file (env PTLABEL_FONT)",
    )
    c.add_argument("--min-length", type=float, default=0, help="minimum label length in mm")

    i = sub.add_parser("images", parents=[job], help="one label per image")
    i.add_argument("files", nargs="+")
    i.add_argument(
        "--rotate",
        default="auto",
        help="auto (long side along the tape), none, or degrees (default %(default)s)",
    )
    i.add_argument("--copies", type=int, default=1, help="copies of each image")
    return p


def _images(args, height: int) -> list[Image.Image]:
    if args.command == "csv":
        if args.file == "-":
            texts = csv_texts(sys.stdin, args.template)
        else:
            with open(args.file, newline="", encoding="utf-8-sig") as f:
                texts = csv_texts(f, args.template)
        min_px = round(args.min_length * BatchPrinter.RESOLUTION_DPI / 25.4)
        return [render_text(t, height, font=args.font, min_length_px=min_px) for t in texts]
    images = []
    for path in args.files:
        with Image.open(path) as img:
            images += [fit_image(img, height, rotate=args.rotate)] * args.copies
    return images


def _print(args) -> int:
    dry_run = args.output is not None
    conn = FileConnection(args.output) if dry_run else DeviceConnection(args.printer)
    conn.connect()
    try:
        if args.tape:
            tape = TAPES[TAPE_CHOICES[args.tape]]()
        elif dry_run:
            tape = TAPES[24]()
        else:
            tape = tape_for_status(query_status(conn))

        height = BatchPrinter.PIN_CONFIGS[type(tape)].print_pins
        images = _images(args, height)
        if not images:
            print("nothing to print", file=sys.stderr)
            return 1
        if args.preview:
            Path(args.preview).mkdir(parents=True, exist_ok=True)
            for n, img in enumerate(images, 1):
                img.save(Path(args.preview) / f"{n:04d}.png")

        BatchPrinter(conn).print_batch(
            [Label(img, tape) for img in images],
            half_cut=args.cut == "half",
            cut_every=args.cut_every,
            margin_mm=args.margin,
            chain=args.chain,
        )
        if dry_run:
            print(f"wrote {len(images)} labels to {args.output}", file=sys.stderr)
        elif not args.no_wait:
            wait_for_completion(
                conn,
                len(images),
                on_progress=lambda n: print(
                    f"\rprinted {n}/{len(images)}", end="", file=sys.stderr
                ),
            )
            print(file=sys.stderr)
        return 0
    finally:
        conn.close()


def _status(args) -> int:
    conn = DeviceConnection(args.printer)
    conn.connect()
    try:
        s = query_status(conn)
    finally:
        conn.close()
    print(f"{s.model}: {s.media_width_mm}mm tape, media type {s.media_type:#04x}")
    print("errors: " + (", ".join(s.errors) or "none"))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _status(args) if args.command == "status" else _print(args)
    except PermissionError:
        print(
            f"permission denied on {args.printer}: add yourself to the lp group "
            "(then log in again) or run with sudo",
            file=sys.stderr,
        )
    except FileNotFoundError as e:
        print(f"not found: {e.filename} (is the printer plugged in and on?)", file=sys.stderr)
    except (PrinterError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
