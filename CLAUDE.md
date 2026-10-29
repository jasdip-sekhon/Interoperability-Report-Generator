# Working on this codebase

Captures (`.xlsx`) → measurements (`.yml`) → charts (`.png`) → deck (`.pptx`).
User docs are [`README.md`](README.md); design is [`ARCHITECTURE.md`](ARCHITECTURE.md).

```
main.py            sequences the four stages
data/              capture xlsx -> measurement yaml, and the DUT/Ref merge
interconnects/     topology xlsx -> interconnects.yml (x-axis labels)
output/<report>/   one self-contained folder per report: deck, charts, x-axis labels
plotting/          plotting.py (generic chart library) + plotting_runner.py (domain)
deck/              manifest + PNGs -> pptx
```

Verify any change with both, in this order:

```bash
python tests/run_all.py     # six test files, asserts not a framework
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

Every `draw_*` follows one recipe, stated in `plotting_runner.py`'s docstring: guard,
reshape, report unmatched, draw, record. Adding a chart means adding a function, not a
table row.

Line endings are **LF**, normalised by `.gitattributes`. Do not rewrite them when
editing programmatically - a changed ending is a diff that changes nothing.

## Known rough edges

- No caching — every run reconverts every spreadsheet. A real report takes up to an
  hour; re-rendering from `data/output/*.yml` takes seconds.
- `main.py` has no tests.
