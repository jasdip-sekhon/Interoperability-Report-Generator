# Interoperability Report Generator

Turns switch/optics test captures into a slide deck: read the raw data, render charts to a
folder, then build the deck from that folder.

Early days — only `plotting/` has working code.

## Layout

```
main.py                  runs the whole pipeline
run.yml                  which captures one report covers
data/
  data_to_yml.py         one capture xlsx -> one measurement yaml
  merge_runs.py          several of those yaml -> one, for a testcase captured twice
  output/                the generated measurement yaml
interconnects/           topology xlsx -> yaml (x-axis labels)
plotting/
  plotting.py            the chart library — data in, PNG out
  plotting_runner.py     builds every chart for one capture
  plotting_style.yaml    colours, sizing, DPI
deck/
  build_deck.py          manifest + PNGs -> pptx
output/                  the deck, plus one folder of charts per testcase
  <testcase>/            its PNGs and manifest.yml — wiped by the runner, not tracked
  test/                  charts from test_plotting.py, kept out of the deck's way
references/              redacted sample captures used as fixtures
```

`plotting.py` knows nothing about switches or interconnects — it takes `data`, `keys`,
`labels` and draws. Everything domain-specific lives in `plotting_runner.py`.

Rendering and deck building are joined by a folder of PNGs, not a function call, so charts
can be inspected without building a deck and the deck can be rebuilt without re-rendering.

A reset testcase is captured twice, DUT-run and Ref-run, and **neither file is
authoritative** — charting one alone silently drops whatever the other saw. Merge them
before plotting. Soak is a single capture and needs no merge.

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
python main.py            # the whole pipeline, per run.yml
```

`run.yml` lists what one report covers: the topology file and each testcase's captures.
A testcase with two captures (a reset is run twice, DUT and Ref) is merged before
plotting. Each testcase renders into `output/<testcase>/`, and the deck gets a section
per testcase.

The stages also run on their own, which is how you iterate on one of them:

```bash
python data/data_to_yml.py                   # captures -> measurement yaml
python interconnects/interconnects_to_yml.py # topology -> label yaml

python data/merge_runs.py data/output/reset_dut_sample.yml \
                          data/output/reset_ref_sample.yml \
                       -o data/output/reset_merged.yml

python plotting/plotting_runner.py data/output/soak_sample.yml
python deck/build_deck.py output/manifest.yml -o output/report.pptx
```

The runner writes `output/manifest.yml` alongside the charts, declaring each one's file,
caption and scope in presentation order. The deck builder reads only that, so it never
learns what a metric is — a chart type added upstream appears in the deck with no change
to `deck/`. It renders one capture at a time, because the runner clears `output/` first.

The converters read `references/` and are only rerun when a capture changes; the charts
read their yaml, never the spreadsheets. Both print what they skipped and why — a missing
sheet, a saturated reading, a lane with no topology entry — so a thin chart has a stated
reason rather than being silently thin.

## Tests

```bash
python data/test_data_to_yml.py        # parsers, against synthetic records
python data/test_merge_runs.py         # the per-field merge rules
python plotting/test_plotting_runner.py  # the topology/measurement join
python plotting/test_plotting.py       # renders one of each chart type to output/test/
python deck/test_build_deck.py         # slide layout and manifest handling
```

The fixtures hold one reading per lane, so the grouping, merging and seam logic are
covered synthetically rather than by running against `references/`.

## Data

Real captures contain customer data and are not tracked. The only spreadsheets in the repo
are the redacted `references/*_sample.xlsx` fixtures — see
[`references/README.md`](references/README.md).
