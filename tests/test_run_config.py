"""Tests for working out what one report covers.

The interesting cases are the ones that are not a config file: a folder of captures
usually has the topology workbook sitting in it, and charting that as data produced an
empty section once. A workbook is a capture because of the sheets it carries, nothing
else, so that is what gets pinned here.
"""

import os
import tempfile

import yaml

import _bootstrap
from run_config import config_for, is_capture, load_config

REFERENCES = os.path.join(_bootstrap.PROJECT_ROOT, "references")
CAPTURE = os.path.join(REFERENCES, "soak_sample.xlsx")
TOPOLOGY = os.path.join(REFERENCES, "interconnects_sample.xlsx")


# --- a capture is known by its sheets, not its name ------------------------------

assert is_capture(CAPTURE), "a capture carries the sheets the converter reads"
assert not is_capture(TOPOLOGY), \
    "a topology workbook carries none of them, however it is named"
print("ok  is_capture: decided by sheets, not by filename")


# --- a .yml is read as written ---------------------------------------------------

work = tempfile.mkdtemp()
path = os.path.join(work, "run.yml")
written = {"report": "X", "testcases": [{"name": "Soak", "captures": ["a.xlsx"]}]}
with open(path, "w", encoding="utf-8") as f:
    yaml.dump(written, f)

assert config_for(path) == written, "a config file is passed through untouched"
assert load_config(path) == written
print("ok  config_for: a .yml is the config")


# --- one capture becomes one testcase --------------------------------------------

config = config_for(CAPTURE)
assert config["report"] == "soak_sample"
assert len(config["testcases"]) == 1
assert config["testcases"][0]["name"] == "soak_sample"
assert os.path.isabs(config["testcases"][0]["captures"][0]), \
    "paths are resolved, so the config does not depend on the working directory"
print("ok  config_for: one capture, named after the file")


# --- a folder becomes one testcase per capture, topology skipped -----------------

config = config_for(REFERENCES)
names = []
for testcase in config["testcases"]:
    names.append(testcase["name"])
assert "interconnects_sample" not in names, \
    "the topology workbook sits beside the captures and must not be charted as data"
assert "soak_sample" in names and len(names) == len(set(names))
for testcase in config["testcases"]:
    assert len(testcase["captures"]) == 1, "a folder pairs nothing: one file, one case"
print(f"ok  config_for: {len(names)} captures from a folder, topology skipped")


# --- what is not a capture is refused, not charted empty -------------------------

for bad, why in ((TOPOLOGY, "a topology passed as a capture"),
                 (os.path.join(work, "nope.xlsx"), "a path that does not exist"),
                 (work, "a folder with no captures in it")):
    try:
        config_for(bad)
        raise AssertionError(f"{why} should not have been accepted")
    except SystemExit as stop:
        assert str(stop), f"{why} must say what was wrong"
print("ok  config_for: refuses with a reason rather than building an empty deck")

print()
print("all tests passed")
