# Architecture

How the stages fit together. For how to *use* the tool, see [`README.md`](README.md).

## Layout

```
main.py                  the command line, and nothing else
pipeline.py              sequences the four stages
run_config.py            what one report covers, from a config or from the data
run.yml                  which captures one report covers (one per rack)
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
output/<report>/         one folder per report: its deck, its x-axis labels, and one
                         folder of charts per testcase. Reports cannot overwrite
                         each other
  <testcase>/            its PNGs and manifest.yml — wiped by the runner, not tracked
tests/                   every test_*.py, run via tests/run_all.py
references/              redacted sample captures used as fixtures
```

`plotting.py` knows nothing about switches or interconnects — it takes `data`, `keys`,
`labels` and draws. Everything domain-specific lives in `plotting_runner.py`.

That boundary is enforced, not just intended: `test_library_is_generic.py` fails if
`plotting.py` imports anything from this project or so much as names a switch, a lane or
a BER. It is meant to be liftable into another project along with `plotting_style.yaml`,
which is why a chart method is called `value_series` rather than `temp_time_series`.

Rendering and deck building are joined by a folder of PNGs, not a function call, so charts
can be inspected without building a deck and the deck can be rebuilt without re-rendering.

A reset testcase is captured twice, DUT-run and Ref-run, and **neither file is
authoritative**. Each is charted on its own — the two runs reset different hardware, so
merging them would seam every time series — but the merged yaml is written anyway, for
the analysis that needs the union.

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

The runner writes a `manifest.yml` alongside the charts, declaring each one's file,
caption, scope and metric in presentation order. The deck builder reads only that: it
groups a slide by scope and metric and sizes the charts by how many share it, without
knowing what any metric means — so a chart type added upstream appears in the deck with
no change to `deck/`. Each testcase gets its own folder, which the runner clears first.

The converters read `references/` and are only rerun when a capture changes; the charts
read their yaml, never the spreadsheets. Both print what they skipped and why — a missing
sheet, a saturated reading, a lane with no topology entry — so a thin chart has a stated
reason rather than being silently thin.

## Tests

Every test is a standalone script (asserts, not a framework) and lives in `tests/`,
regardless of which stage it covers — a test importing its module by bare name is what
`tests/_bootstrap.py` sets up, the same sys.path trick `pipeline.py` uses to let the stages
import each other.

```bash
python tests/run_all.py                    # everything, one command

python tests/test_data_to_yml.py           # parsers, against synthetic records
python tests/test_merge_runs.py            # the per-field merge rules
python tests/test_plotting_runner.py       # the topology/measurement join
python tests/test_plotting.py              # renders one of each chart type
python tests/test_library_is_generic.py    # plotting.py stays domain-free
python tests/test_build_deck.py            # slide layout and manifest handling
```

The fixtures hold one reading per lane, so the grouping, merging and seam logic are
covered synthetically rather than by running against `references/`.

