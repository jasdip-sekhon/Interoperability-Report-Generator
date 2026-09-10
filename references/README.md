# Development fixtures

Small, structure-faithful samples cut from the real AWS/Innolight captures by
`make_fixtures.py`. **Origin: R12-TB1, 2026.**

The real captures are 13–643 MB of customer data. These are 90–130 KB, keep the exact
sheet names, header rows and value shapes, and are deliberately chosen so that each of the
traps in [`../docs/INGEST_CHECKLIST.md`](../docs/INGEST_CHECKLIST.md) actually appears in
the data. Management IPs and serials are redacted; every measurement is left as recorded.

Use them as golden fixtures: a new reader is *verified* against these, not trusted.

---

## Files

| File | Size | What it is |
|---|---|---|
| `soak_sample.xlsx` | ~130 KB | 48 h traffic soak. The only testcase with a `get_fec_counter` sheet, so the only source of T-Code and uncorrected codewords. |
| `reset_dut_sample.xlsx` | ~90 KB | Reset, DUT-run capture |
| `reset_ref_sample.xlsx` | ~105 KB | Reset, Ref-run capture — pair with the DUT file to exercise the merge |
| `interconnects_sample.xlsx` | ~6 KB | Topology: `Chart label lookup` sheet, 35 rows across all 5 switches, both Ixia-fed and switch-to-switch links |
| `topology_sample.yaml` | ~4 KB | Same 35 records as YAML — the proposed target format for an LLDP converter |

---

## Which quirk each fixture proves

Verified present, not assumed:

**1. Blank ≠ zero** — `soak_sample.xlsx`, sheet `5_get_fec_counter`

```
switch 0      tcode2 = [0, 1]      measured
switch 4-33   tcode2 = [None]      NOT measured
switch 4-34   tcode2 = [None]      NOT measured
switch 4-35   tcode2 = [None]      NOT measured
switch 4-36   tcode2 = [None]      NOT measured
```

A reader that records `None` as `0` reports four switches as passing a T-Code spec they
never measured.

**2. Logging offset** — `reset_ref_sample.xlsx`, sheet `6_get_link_flap`

```
switch 4-35   raw Down->Up = [0, 1, 2]   ->  corrected = [0, 1]
```

All three cases in one switch: raw `1` is the expected single commanded recovery
(corrected `0`), raw `2` is a genuine extra flap (corrected `1`), raw `0` is a lane that
*never recovered at all* — which the `-1` correction collapses into the same corrected `0`
as the normal case. That collapse is why `flap_never_recovered` has to be derived from the
raw value separately.

Contrast `soak_sample.xlsx`, where every switch reads raw `0`: soak commands no recovery,
so a "never recovered" signal is meaningless there. That is checklist §9.

**3. Split DUT/Ref coverage** — `reset_dut_sample.xlsx` + `reset_ref_sample.xlsx`

Both files contain all five switches (`0`, `4-33`, `4-34`, `4-35`, `4-36`). Neither is
authoritative for a subset. Picking one per switch silently drops the other's findings —
on the real data that hid 68 failing lanes. Merge by union.

**4. Saturated values** — `reset_ref_sample.xlsx`, sheet `3_get_module_info`

Contains VDM Pre-FEC readings at/above `0.5`, which are a coin-flip link rather than a real
BER. `plot_test_report.py` reports `ignored 58 VDM Pre-FEC reading(s) at or above 0.5 as
invalid` when parsing this fixture.

**5. Same name, different measurement** — reset vs. soak

The reset fixtures have no `get_fec_counter` sheet at all, so Pre-FEC falls back to the
module's own VDM reading — *the optic's view*, not the switch ASIC's counter. Parsing them
prints `no '*get_fec_counter' sheet; using the module's VDM Pre-FEC BER ... instead`. The
two must never be pooled or compared against the same threshold.

**6. Sheet position is not stable** — across the fixtures

```
get_fec_counter    5_  (soak)          — absent in reset
get_link_flap      7_  (soak)   6_  (reset)
get_module_info    2_  (soak)   3_  (reset)
get_switch_sensor  6_  (soak)   5_  (reset)
```

Match by suffix or content, never by index. The link-up sheet has to be found by the
presence of a `LinkUpTime` column, since its action name varies.

**7. Mixed-type switch IDs** — all fixtures

`0` is an int, `"4-33"` is a string, in the same column. See `norm_switch()`.

---

## Sanity check

```bash
python3 -c "
from pathlib import Path
import plot_test_report as ptr
run = ptr.load_run(Path('fixtures/reset_ref_sample.xlsx'))
print(sorted(run['flaps'].keys()))
"
```

Expected on `reset_ref_sample.xlsx`: 5 switches, 120 flap lanes, 6 never-recovered lanes,
122 Pre-FEC lanes, and the two `Info:` lines about the missing FEC sheet and the 58 dropped
VDM readings.

---

## Regenerating

```bash
python3 make_fixtures.py
```

Requires the real captures under `Data_Files/`. Row budgets are per-switch and per-sheet —
see the constants at the top of that script. The VDM-saturated rows in
`reset_ref_sample.xlsx` were appended separately, since they do not appear in the first N
rows of any switch; if you regenerate from scratch, re-add them or quirk 4 disappears.

---

## Caveat

These are cut from one customer's format. They prove that *these* traps exist and that a
reader handles them — they cannot tell you what a different customer's tooling will do
differently. Treat them as regression fixtures for the AWS reader, and as a worked example
of what a fixture set should demonstrate, not as a general conformance suite.
