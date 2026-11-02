# Working on this codebase

Captures (`.xlsx`) → measurements (`.yml`) → charts (`.png`) → deck (`.pptx`).
User docs are [`README.md`](README.md); design is [`ARCHITECTURE.md`](ARCHITECTURE.md).

```
main.py            the command line, and nothing else
pipeline.py        sequences the four stages
run_config.py      what one report covers, from a config or from the data
data/              capture xlsx -> measurement yaml (data_to_yml -> collect, meta,
                   parse, sheets, cache), and the DUT/Ref merge (merge_runs ->
                   merge_rules, merge_report)
interconnects/     topology xlsx -> interconnects.yml (x-axis labels)
plotting/          plotting.py is the generic library; plotting_runner -> charts ->
                   layout -> {output, x_axis}
deck/              manifest + PNGs -> pptx
output/<report>/   one self-contained folder per report: deck, charts, x-axis labels
```

Verify any change with both, in this order:

```bash
python tests/run_all.py     # ten test files, asserts not a framework
python main.py              # the fixtures, end to end, ~10 seconds
```

## The two things users ask for

### 1. A run config

One `run_<name>.yml` per report. Schema is in README; the parts that need judgement:

- **Pair DUT/Ref by asking, not by filename.** The halves of one testcase are spelled
  differently in real data — `ShutunShut-Ln1-1-DUT` with `ShutunShut_Lane1_1_Ref`,
  `lane1-1` with `ln1-1`. Guessing produces a plausible deck that is wrong.
- **`metrics` is per test type**, and differs by rack. What the hand-built reports chart:

  | testcase | metrics |
  |---|---|
  | Soak | `ber, tcode, temps` |
  | Reset | `flaps, ber, link_up, temps` |
  | Shut No-Shut | `flaps, link_up, temps` |
  | Lane x-y | `flaps, temps` (Rack6) or `+ link_up` (R12) |

  Omitting `metrics` charts everything: 407 charts instead of 329 on R12-TB1.
- **`recovery_commanded: true`** only where the test commands links back up (reset,
  shut). Wrong here gave 506 false "never recovered" lanes once.

### 2. A topology workbook

Only one sheet is read: **`Chart label lookup`**, with exactly these columns:

| Rx Switch | Rx Port-Lane | Rx Vendor | Tx Switch | Tx Port-Lane | Tx Vendor | FEC-BER / T-Code x-axis label |
|---|---|---|---|---|---|---|
| `SW0` | `1-1` | `NW1` | `Ixia` | `1-1` | `Ixia` | `1-1-Tx-Ixia ==> 1-1-Rx-NW1` |

One row per **Rx lane** — that row is one x-axis entry. Other sheets (`Cables`,
`Lane links`, `Switches`, `Link matrix`) are human reference and are ignored.

`Rx Switch` is matched to the measurements by stripping a leading `SW`, so `SW0`
becomes `0` while `4-33` and `Ixia` stay as they are.

## Domain facts that are easy to get wrong

- **T-Code is the FEC bin** - symbol errors per codeword. KP4 RS(544,514) corrects up
  to 15 and fails at 16, so the spec line at 6 is a margin, not the cliff. Likewise the
  BER line at 2e-6 sits ~120x below KP4's 2.4e-4 tolerance. All three spec constants in
  `charts.py` come from the test plan, not the MSA.
- **BER is `FEC_BER`, not `PRE_FEC_SER`.** `PRE_FEC_SER` is 10× larger; reading it makes
  every link look an order of magnitude worse.
- **BER ≥ 0.5 is counter saturation**, not a reading. Filtered in the runner
  (`SATURATED_BER`), never in the converter — raw data is not modified.
- **Lane 0 means an un-broken-out port**, and the topology calls it lane 1. Both
  `_lane_values` and `_lane_scalars` index it under both.
- **Blank ≠ zero.** `null` = not measured, `0` = measured zero, `[]` = measured and
  nothing survived filtering. The bar chart marks measured zeros so they are not
  mistaken for gaps.
- **`load_workbook(..., read_only=True)`** — 26× faster. Without it a report takes 37
  minutes instead of 1.5.
- **Test type comes from the config, not sheet detection.** Detection calls every
  non-reset capture a soak, which throws away the recovery signal.
- Every render prints the topology it used. `x axis from ...fixture.xlsx, 35
  interconnects` against real data means the topology was built from the wrong file.
  Each report writes its own copy under `output/<report>/`, so racks cannot collide;
  `interconnects/interconnects.yml` remains only as the default for standalone runs.

## Conventions

`plotting.py` is the user's own code and the style benchmark: explicit loops, no
comprehensions, no `enumerate`/`zip`/`lambda`/`sort(key=)`, `if`/`else` over ternaries
and `or`-defaults. `plotting_runner.py` follows it. Match that style; do not introduce
dispatch tables or spec dictionaries.

`plotting.py` must stay domain-free — no project imports, and no word like switch, lane
or BER anywhere in it. `test_library_is_generic.py` fails if that slips.

Every `draw_*` follows one recipe, stated in `charts.py`'s docstring: guard, reshape,
report unmatched, draw, record. Adding a chart means adding a function, not a table row.

**One purpose per file**, and imports run one way so a change is never chased backwards:
`plotting_runner -> charts -> layout -> {output, x_axis, plotting}`. Before splitting,
check the group calls nothing outside itself; both splits here were mechanical because
of that, and would have been a bad idea otherwise.

**Entry points hold no logic.** `main.py` is argparse and nothing else, because code
inside `if __name__ == "__main__":` can never be reached by a test. The work lives in
`pipeline.py`, which is importable. Same reason `collect_measurements` was split out of
`data_to_yml`.

**A function does one job.** When one grows several, split it by the rule it enforces -
`merge_meta` became `_refuse_mixed_ber_sources`, `_union_switches`, `_earliest_start`.
Nothing in `plotting/` nests deeper than 3 or recurses; keep it that way.

**No unused parameters.** An argument the body ignores is a lie about the interface -
`value_series` took `colors` and `labels` and read neither, so callers built label lists
that were thrown away. Check before adding one for symmetry's sake.

**Comments earn their place.** One line at the surprising spot, not a block restating
the code. `_source_stamp` hashes its own source file: that line gets a comment, the four
obvious fields around it do not.

**Write through a partial file and rename**, so an interrupted run leaves the previous
file rather than half of a new one. Close workbooks in `finally` - `read_only` holds the
zip open.

Line endings are **LF**, normalised by `.gitattributes`. Do not rewrite them when
editing programmatically - a changed ending is a diff that changes nothing.

## Known rough edges

- A capture is reconverted only when something that changes its yaml changes: the
  spreadsheet, any converting module in `data/`, `test_type`, or `recovery_commanded`.
  The stamp is `meta.source` in each yaml (see `cache.py`), and `--no-cache` ignores it.
  Hashing a 379 MB capture costs 0.8s against ~480s to convert it. If `data/` gains a
  module that parses, add it to `CONVERTER_MODULES` or the stamp stops covering it.
- `test_charts.py` covers the reshaping helpers but never calls a `draw_*`. Dropping an
  import from `charts.py` once left the suite green while `python main.py` died
  immediately - which is why both commands are listed above, in that order.
