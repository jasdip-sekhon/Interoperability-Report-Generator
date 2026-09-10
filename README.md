# Interoperability Report Generator

Turns switch/optics test captures into a slide deck: read the raw data, render charts to a
folder, then build the deck from that folder.

Early days — only `plotting/` has working code.

## Layout

```
main.py         entry point
analysis/       captures -> findings
plotting/       findings -> PNG charts on disk
deck/           PNGs -> slide deck
references/     redacted sample captures used as fixtures
```

Rendering and deck building are joined by a folder of PNGs, not a function call, so charts
can be inspected without building a deck and the deck can be rebuilt without re-rendering.
Wipe the output folder each run — a stale PNG is indistinguishable from a fresh one.

Chart styling lives in [`plotting/plotting_style.yaml`](plotting/plotting_style.yaml).

## Setup

Requires Python 3.11+ (matplotlib 3.11 dropped older versions).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS/Linux the activation line is `source .venv/bin/activate`.

## Running the plotting test

```bash
python plotting/test_box_plot.py
```

Renders a chart to `plotting/test_box_plot.png` from inline sample data.

## Data

Real captures contain customer data and are not tracked. The only spreadsheets in the repo
are the redacted `references/*_sample.xlsx` fixtures — see
[`references/README.md`](references/README.md).
