# Interoperability Report Generator

Turns switch/optics test captures into a PowerPoint deck of charts.

## Setup

Requires Python 3.11+ (matplotlib 3.11 dropped older versions).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS/Linux the activation line is `source .venv/bin/activate`.

## Make a report

**1. Create a config file** for your report — see [The config](#the-config). Copying an
existing `run_*.yml` and changing the paths is the quickest start.

**2. Run it:**

```bash
python main.py run_myrack.yml
```

It prints progress as it goes. Reading the spreadsheets is the slow part — up to an
hour the first time — but a capture already read is reused, so later runs take seconds.
Pass `--no-cache` to read them all again.

**3. Open the deck** named on the last line, in `output/`.

`python main.py` with no arguments runs the samples in `references/` in ten seconds —
use it to check the install.

## The config

One text file per report, saved as `run_<name>.yml`. It is written by hand because
filenames do not say which captures pair, and no spreadsheet says what its test measured.

Paths use forward slashes, even on Windows.

```yaml
report: R12-TB1
topology: C:/data/R12_TB1_Tx_Rx_Interconnects.xlsx

testcases:
  - name: Soak
    metrics: [flaps, ber, tcode, uncorrected_cw, temps]
    capture: C:/data/R12-TB1-Traffic_Soak_20260816.xlsx

  - name: Reset
    metrics: [flaps, link_up, temps]
    dut: C:/data/R12-TB1-Reset_DUT_20260717.xlsx
    ref: C:/data/R12-TB1-Reset_Ref_20260718.xlsx
```

A testcase captured once uses `capture:`; one captured as a DUT run and a Ref run uses
`dut:` and `ref:`. For anything else — three or more runs, or labels other than DUT/Ref
— use `captures:` instead, a list of files (or `{label, file}` for a labelled one).

Testcases appear in the deck in the order written here, and a `dut:`/`ref:` pair appears
as two sections, DUT first. To group a family differently — every DUT section before any
Ref section, say — give each run its own testcase with a single `capture:` and order them
as you want them read.

`ber` only means something on a soak: a test that takes links down saturates the counter,
so BER is collected for a soak and nothing else. Listing it elsewhere draws no chart and
says so.

| setting | what it does | needed? |
|---|---|---|
| `report` | names the deck and its folder, e.g. `output/r12-tb1/r12-tb1.pptx` | yes |
| `topology` | the Tx/Rx interconnects spreadsheet, for real x-axis labels | in practice |
| `name` | the section heading in the deck | yes |
| `capture` | the one spreadsheet, for a testcase run once | one of these three |
| `dut`, `ref` | the two spreadsheets, for a testcase run as DUT and Ref | |
| `captures` | a list of spreadsheets, for anything `capture`/`dut`/`ref` can't say | |
| `metrics` | which measurements to chart: any of `flaps`, `ber`, `tcode`, `uncorrected_cw`, `link_up`, `temps`. Omit to chart all | no |

## Without a config

To look at captures without writing a config, point at a file or a folder:

```bash
python main.py capture.xlsx
python main.py path/to/Data_Files -t path/to/topology.xlsx
```

Every spreadsheet becomes its own section, named after the file. You lose the chosen
names and the `metrics` subset, but still get a full deck.

## Where things end up

```
output/<report>/<report>.pptx       the deck
output/<report>/<testcase>/         that testcase's charts as PNGs, to check one alone
output/<report>/interconnects.yml   the x-axis labels this report was built with
data/output/                        the measurements pulled out of each spreadsheet
```

If a chart looks wrong, open its PNG directly rather than hunting through the deck.

## For developers

How the stages fit together, how to run one on its own, and the tests:
[`ARCHITECTURE.md`](ARCHITECTURE.md).
