"""Checks data_to_yml against real captures, not synthetic records.

Every other test either builds its own small input by hand or renders fake data; none
of them prove the collectors read the right columns out of an actual spreadsheet. This
reads two fixtures a second, independent way - straight through openpyxl, with none of
parse.py or collect.py involved - and checks several lanes across five metrics against
what data_to_yml produced from the same files. One lane of one metric was previously
checked once, by hand; this is every run, several lanes of each.
"""

from datetime import datetime
import os
import tempfile

from openpyxl import load_workbook
import yaml

import _bootstrap
from data_to_yml import data_to_yml

RESET = os.path.join(_bootstrap.PROJECT_ROOT, "references", "reset_dut_sample.xlsx")
SOAK = os.path.join(_bootstrap.PROJECT_ROOT, "references", "soak_sample.xlsx")


def _sheet(path, name):
    wb = load_workbook(path, read_only=True)
    rows = list(wb[name].iter_rows(values_only=True))
    wb.close()
    header = rows[0]
    col = {cell: i for i, cell in enumerate(header)}
    return col, rows[1:]


def _check(actual, expected, what, n):
    assert len(expected) >= n, f"the fixture should have at least {n} {what} lanes"
    checked = 0
    for key in sorted(expected)[:n]:
        assert key in actual, f"{key} has a {what} reading in the sheet but not in the yaml"
        assert expected[key] == actual[key], \
            f"{what} at {key}: sheet says {expected[key]}, yaml says {actual[key]}"
        checked = checked + 1
    print(f"ok  {what}: {checked} lanes match a direct re-read of the sheet")


work = tempfile.mkdtemp()


# --- reset_dut_sample.xlsx: flaps, and BER from the module's own VDM columns ------

reset_yml = os.path.join(work, "reset_dut_sample.yml")
data_to_yml(RESET, reset_yml, test_type="reset", recovery_commanded=True)
reset = yaml.safe_load(open(reset_yml, encoding="utf-8"))

col, rows = _sheet(RESET, "6_get_link_flap")
expected_flaps = {}
for row in rows:
    key = (str(row[col["TreeL1"]]), row[col["TreeL2"]], row[col["TreeL3"]])
    count = max(0, row[col["Down->Up"]] - 1)
    if key not in expected_flaps or count > expected_flaps[key]:
        expected_flaps[key] = count
actual_flaps = {}
for record in reset["flaps"]:
    actual_flaps[(record["switch"], record["port"], record["lane"])] = record["count"]
_check(actual_flaps, expected_flaps, "flaps", 5)

# BER is soak-only, even though this fixture's module info does carry VDM columns
assert reset["ber"] is None, "BER must not be collected for a non-soak test_type"
print("ok  BER: not collected for a functional test, even though this capture has it")

col, rows = _sheet(RESET, "2_module_reset")
expected_link_up = {}
for row in rows:
    key = (str(row[col["TreeL1"]]), row[col["TreeL2"]], row[col["TreeL3"]])
    if key not in expected_link_up:
        expected_link_up[key] = []
    expected_link_up[key].append(row[col["LinkUpTime"]])
actual_link_up = {}
for record in reset["link_up"]:
    key = (record["switch"], record["port"], record["lane"])
    actual_link_up[key] = record["values"]
_check(actual_link_up, expected_link_up, "link-up time", 5)


# --- temperatures: joined against the log's own timestamps, same as collect_temps -

col, rows = _sheet(RESET, "0_log")
log_timestamps = {}
for row in rows:
    if not row[col["test_start_time"]]:
        continue
    key = (str(row[col["Repeat"]]), str(row[col["test_step"]]), str(row[col["TreeL1"]]))
    log_timestamps[key] = datetime.strptime(row[col["test_start_time"]],
                                            "%Y-%m-%d %H:%M:%S")
start = min(log_timestamps.values())

col, rows = _sheet(RESET, "3_get_module_info")
expected_temps = {}
for row in rows:
    switch = str(row[col["TreeL1"]])
    port = row[col["TreeL2"]]
    key = (str(row[col["Repeat"]]), str(row[col["test_step"]]), switch)
    when = log_timestamps.get(key)
    if when is None:
        continue
    hours = round((when - start).total_seconds() / 3600.0, 4)
    text = str(row[col["ModuleMonitorsModuleMonitorInternalTemperature"]])
    if text.endswith("C"):
        text = text[:-1]
    temp = float(text)
    module_key = (switch, port)
    if module_key not in expected_temps:
        expected_temps[module_key] = []
    expected_temps[module_key].append([hours, temp])
for key in expected_temps:
    expected_temps[key] = sorted(expected_temps[key])

actual_temps = {}
for record in reset["temps"]:
    actual_temps[(record["switch"], record["port"])] = record["points"]
_check(actual_temps, expected_temps, "temperature", 5)


# --- soak_sample.xlsx: BER, T-Code and uncorrected codewords from get_fec_counter -

soak_yml = os.path.join(work, "soak_sample.yml")
data_to_yml(SOAK, soak_yml, test_type="soak", recovery_commanded=False)
soak = yaml.safe_load(open(soak_yml, encoding="utf-8"))

col, rows = _sheet(SOAK, "5_get_fec_counter")

expected_ber = {}
expected_tcode = {}
expected_ucw = {}
for row in rows:
    key = (str(row[col["TreeL1"]]), row[col["TreeL2"]], row[col["TreeL3"]])
    expected_ber[key] = [row[col["FEC_BER"]]]
    expected_tcode[key] = [row[col["tcode2"]]]
    expected_ucw[key] = [row[col["UNCORR_CW"]]]

actual_ber = {}
for record in soak["ber"]:
    key = (record["switch"], record["port"], record["lane"])
    actual_ber[key] = record["values"]
_check(actual_ber, expected_ber, "BER (fec_counter)", 5)

actual_tcode = {}
for record in soak["tcode"]:
    key = (record["switch"], record["port"], record["lane"])
    actual_tcode[key] = record["values"]
actual_ucw = {}
for record in soak["uncorrected_cw"]:
    key = (record["switch"], record["port"], record["lane"])
    actual_ucw[key] = record["values"]

_check(actual_tcode, expected_tcode, "T-Code", 5)
_check(actual_ucw, expected_ucw, "uncorrected codewords", 5)

# tcode2 is blank for most rows in this fixture - worth confirming the check is not
# accidentally passing by only ever landing on blank lanes
with_value = [k for k in expected_tcode if expected_tcode[k] != [None]]
assert len(with_value) > 0, "the fixture should have at least one real T-Code reading"
assert any(actual_tcode[k] == expected_tcode[k] for k in with_value), \
    "no non-blank T-Code lane was actually verified"
print("ok  T-Code: at least one checked lane carries a real (non-blank) reading")

print()
print("all tests passed")
