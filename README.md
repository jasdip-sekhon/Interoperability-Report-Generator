# Interoperability Report Generator

Turns switch/optics test captures into a slide deck: read the raw data, render charts to a
folder, then build the deck from that folder.

Early days — only `plotting/` has working code.

## Layout

```
main.py                  entry point
plotting/
  plotting.py            the chart library — data in, PNG out
  plotting_runner.py     builds every chart for a run
  plotting_style.yaml    colours, sizing, DPI
  interconnects/         topology xlsx -> yaml (x-axis labels)
  data/                  captures xlsx -> yaml (measurements)
    output/              the generated measurement yaml
deck/                    PNGs -> slide deck
output/                  generated PNGs — wiped each run, not tracked
references/              redacted sample captures used as fixtures
```

`plotting.py` knows nothing about switches or interconnects — it takes `data`, `keys`,
`labels` and draws. Everything domain-specific lives in `plotting_runner.py`.

Rendering and deck building are joined by a folder of PNGs, not a function call, so charts
can be inspected without building a deck and the deck can be rebuilt without re-rendering.
Wipe the output folder each run — a stale PNG is indistinguishable from a fresh one.

## Setup

Requires Python 3.11+ (matplotlib 3.11 dropped older versions).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS/Linux the activation line is `source .venv/bin/activate`.

## Running

```bash
python plotting/data/data_to_yml.py                   # captures  -> measurement yaml
python plotting/interconnects/interconnects_to_yml.py # topology   -> label yaml
python plotting/test_plotting.py                      # renders one of each chart type
```

The two converters read `references/` and are only rerun when a capture changes; the
charts read their yaml, never the spreadsheets.

## Data

Real captures contain customer data and are not tracked. The only spreadsheets in the repo
are the redacted `references/*_sample.xlsx` fixtures — see
[`references/README.md`](references/README.md).
