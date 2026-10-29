# ptlabel

Batch-print CSV rows and images to a Brother PT-E550W label printer as **one job**, so the
printer doesn't waste a ~2.5cm leader (the gap between print head and cutter) on every label.

Labels are joined by half-cuts — the label layer is cut, the backing stays in one strip — with the
printer's minimum 2mm margin either side. Only the first label of a job pays the leader.

Built on [ptouch](https://pypi.org/project/ptouch/) for tape geometry and rasterising. ptlabel adds
the multi-label job sequence verified on real hardware, a `/dev/usb/lp0` connection, status/progress
reading, CSV text rendering and image dithering.

## Install

```sh
uv tool install git+https://github.com/awfulwoman/ptlabel
```

The printer appears as `/dev/usb/lp0`, owned by `root:lp`. To print without `sudo`, add yourself to
the `lp` group.

### Ubuntu and Fedora

The command is the same on both:

```sh
sudo usermod -aG lp "$USER"
```

Log out and in again (or open a new SSH session), then check:

```sh
id -nG          # should include lp
ptlabel status
```

A running process keeps the groups it started with. Terminals inside an existing tmux or other
multiplexer session won't see the change until that session is restarted. To use the group straight
away without logging out, run one command at a time with `sg lp -c 'ptlabel status'`.

If `/dev/usb/lp0` doesn't exist when the printer is plugged in and on, check that the `usblp` kernel
module is loaded with `lsmod | grep usblp`, and load it with `sudo modprobe usblp`.

## Use

```sh
ptlabel status                                   # model, tape width, errors

ptlabel csv items.csv                            # first column, one label per row
ptlabel csv items.csv --template '{name}\n{tag}' # two lines per label
ptlabel images logo.png photo.jpg --copies 5     # images, dithered to black and white
```

Tape width is read from the printer. Options for both `csv` and `images`:

| Option | Default | Meaning |
|---|---|---|
| `--cut half\|full` | `half` | cut between labels |
| `--cut-every N` | last label | full cut every N labels (1–99) |
| `--margin MM` | `2` | blank tape either side of each label (minimum 2) |
| `--chain` | off | leave the last label in the printer; the next job pushes it out instead of wasting a new leader. Use for every job of a run except the last |
| `--output FILE` | | dry run: write the raster job to a file |
| `--preview DIR` | | dry run: save each label as a PNG |
| `--tape MM` | `24` | dry runs only: tape width to lay out for (3.5, 6, 9, 12, 18 or 24). Real prints always use the tape the printer reports |
| `--printer PATH` | `/dev/usb/lp0` | or env `PTLABEL_PRINTER` |

`csv` also takes `--font` (env `PTLABEL_FONT`) and `--min-length MM`. `images` takes `--rotate`
(`auto` turns portrait images so the long side runs along the tape).

## Printer protocol notes

From the [Brother raster command reference](https://download.brother.com/welcome/docp100064/cv_pte550wp750wp710bt_eng_raster_102.pdf)
and test prints:

- One job: invalidate + `ESC @` once; per label `ESC i a 1`, `ESC i z` (page flag 0 first, 1 after),
  `ESC i M 0x40`, `ESC i A n`, `ESC i K`, `ESC i d`, `M 2`, rows, then `0x0C` — or `0x1A` after the last.
- Use TIFF compression. Uncompressed data over USB prints while it is still arriving, so cut
  positions go wrong, and `Z` (blank row) is only valid when compressed.
- **Never send anything while a job prints**, including a status request. It aborts the job and leaves
  printed tape inside the printer, which comes out at the start of the next job. ptlabel only listens
  for the printer's own status packets until every label reports printed.
- ptouch's `print_multi()` turns auto-cut off, always sends page flag 0 and forces chain printing
  off, so ptlabel builds the sequence itself.

## Develop

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
