"""Tests for sequencing the stages.

Most of this is naming and path handling, where the failure is a file written somewhere
nobody looks. The one with teeth is the cache: reusing a yaml that a newer converter
would have written differently is invisible - the charts render, they are just wrong -
so each thing that should invalidate it gets its own assertion.
"""

import os
import shutil
import tempfile

import _bootstrap
import pipeline
from pipeline import _capture_entries, _resolve, _slug, build_x_axis, prepare_measurements

CAPTURE = os.path.join(_bootstrap.PROJECT_ROOT, "references", "soak_sample.xlsx")


# --- names that become folders -----------------------------------------------

assert _slug("R12-TB1") == "r12-tb1"
assert _slug(" Soak ") == "soak"
assert _slug("Lane 1-1 DUT") == "lane_1-1_dut"
assert _slug("Shut / No-Shut") == "shut___no-shut", \
    "a slash would otherwise split one testcase into nested directories"
print("ok  _slug: lowercased, and no separator survives into a folder name")


# --- config paths are relative to the project, not the shell ------------------

assert _resolve(CAPTURE) == _resolve(_resolve(CAPTURE)), "an absolute path is left alone"
assert str(_resolve("references/soak_sample.xlsx")).startswith(
    str(_bootstrap.PROJECT_ROOT)), \
    "a relative path in a config means relative to the project, not the cwd"
print("ok  _resolve: config paths do not depend on where you ran from")


# --- the general list form: a bare path has no label, a dict carries one -------

entries = _capture_entries({"name": "x", "captures": [
    "plain.xlsx",
    {"label": "DUT", "file": "dut.xlsx"},
]})
assert entries == [(None, "plain.xlsx"), ("DUT", "dut.xlsx")]
print("ok  _capture_entries: captures: list, bare path or labelled dict")

# --- the flat shorthand for the two common cases --------------------------------

assert _capture_entries({"name": "x", "capture": "soak.xlsx"}) == [(None, "soak.xlsx")]
print("ok  _capture_entries: capture: for one file, no label needed")

assert _capture_entries({"name": "x", "dut": "a.xlsx", "ref": "b.xlsx"}) == \
    [("DUT", "a.xlsx"), ("Ref", "b.xlsx")]
assert _capture_entries({"name": "x", "dut": "a.xlsx"}) == [("DUT", "a.xlsx")], \
    "one side alone is still valid, e.g. before the paired run exists"
print("ok  _capture_entries: dut:/ref: for the paired case")

try:
    _capture_entries({"name": "x", "capture": "a.xlsx", "captures": ["b.xlsx"]})
    raise AssertionError("mixing the flat and list forms must be rejected")
except ValueError as stop:
    assert "x" in str(stop), "the error should name the testcase"
print("ok  _capture_entries: refuses to guess which form was meant")


# --- no topology is a working report, not an error ----------------------------

work = tempfile.mkdtemp()
assert build_x_axis(None, work) is None, \
    "without a topology the x axis comes from the measurements"
print("ok  build_x_axis: no topology configured is allowed")


# --- the cache: reuse only when nothing that matters changed ------------------

measurements_dir = tempfile.mkdtemp()
pipeline.MEASUREMENTS_DIR = _resolve(measurements_dir)
testcase = {"name": "Soak", "captures": [CAPTURE]}

converted = prepare_measurements(testcase)
assert len(converted) == 1
yml = converted[0][1]
assert os.path.exists(yml)
first = os.path.getmtime(yml)

prepare_measurements(testcase)
assert os.path.getmtime(yml) == first, "an unchanged capture must not be reconverted"
print("ok  cache: an unchanged capture is reused")

prepare_measurements(testcase, use_cache=False)
assert os.path.getmtime(yml) != first, "--no-cache must reconvert regardless"
print("ok  cache: --no-cache reconverts anyway")

# recovery_commanded changes never_recovered, so it must not be served from cache
stamp = os.path.getmtime(yml)
prepare_measurements({"name": "Soak", "captures": [CAPTURE],
                      "recovery_commanded": True})
assert os.path.getmtime(yml) != stamp, \
    "recovery_commanded changes what the yaml says and must invalidate it"
print("ok  cache: a changed parameter invalidates")

# the testcase name becomes test_type, which the converter records
stamp = os.path.getmtime(yml)
prepare_measurements({"name": "Reset", "captures": [CAPTURE]})
assert os.path.getmtime(yml) != stamp, \
    "the testcase name becomes test_type and must invalidate too"
print("ok  cache: a renamed testcase invalidates")

shutil.rmtree(measurements_dir, ignore_errors=True)

print()
print("all tests passed")
