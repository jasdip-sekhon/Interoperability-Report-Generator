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

It prints progress as it goes; a full report can take up to an hour.

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
    metrics: [ber, tcode, temps]
    captures:
      - C:/data/R12-TB1-Traffic_Soak_20260816.xlsx

  - name: Reset
    metrics: [flaps, ber, link_up, temps]
    recovery_commanded: true
    captures:
      - label: DUT
        file: C:/data/R12-TB1-Reset_DUT_20260717.xlsx
      - label: Ref
        file: C:/data/R12-TB1-Reset_Ref_20260718.xlsx
```

| setting | what it does | needed? |
|---|---|---|
| `report` | names the deck, e.g. `output/r12-tb1.pptx` | yes |
| `topology` | the Tx/Rx interconnects spreadsheet, for real x-axis labels | no |
| `name` | the section heading in the deck | yes |
| `captures` | the test spreadsheets for that testcase | yes |
| `label` | `DUT` or `Ref`, when one testcase was run twice | no |
| `metrics` | which measurements to chart: any of `flaps`, `ber`, `tcode`, `link_up`, `temps`. Omit to chart all | no |
| `recovery_commanded` | `true` if this test tells links to come back up | no |

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
output/<report>.pptx       the deck
output/<testcase>/         that testcase's charts as PNGs, so one can be checked alone
data/output/               the measurements pulled out of each spreadsheet
```

If a chart looks wrong, open its PNG directly rather than hunting through the deck.

## For developers

How the stages fit together, how to run one on its own, and the tests:
[`ARCHITECTURE.md`](ARCHITECTURE.md).
