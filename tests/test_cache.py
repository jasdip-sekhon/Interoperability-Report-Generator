"""Tests for deciding a capture need not be converted again.

Reusing a yaml that a newer converter would have written differently is invisible: the
charts render, they are simply wrong. So the stamp covers the converting code as well
as the capture, and the list of modules it covers is checked against what is actually
in data/ - a new parser nobody adds there would be silently uncovered.
"""

import ast
import os
import tempfile

import yaml

import _bootstrap
from cache import CONVERTER_MODULES, _converter_hash, _file_hash, _source_stamp, is_current

DATA = os.path.join(_bootstrap.PROJECT_ROOT, "data")
CAPTURE = os.path.join(_bootstrap.PROJECT_ROOT, "references", "soak_sample.xlsx")

# cache.py decides reuse and merge_* joins finished yaml; neither converts a capture
NOT_CONVERTERS = {"cache.py", "merge_runs.py", "merge_rules.py", "merge_report.py"}


# --- the stamp must cover every module that converts ------------------------------

present = set()
for name in os.listdir(DATA):
    if name.endswith(".py"):
        present.add(name)
converting = present - NOT_CONVERTERS
assert converting == set(CONVERTER_MODULES), (
    f"data/ holds {sorted(converting)} but the stamp covers {sorted(CONVERTER_MODULES)}. "
    "A converting module missing here keeps serving yaml it would now write differently.")
print(f"ok  CONVERTER_MODULES covers all {len(converting)} converting modules")

# and every one of them is reachable from the converter, not dead weight
reachable = {"data_to_yml.py"}
pending = ["data_to_yml.py"]
while pending:
    tree = ast.parse(open(os.path.join(DATA, pending.pop()), encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            name = node.module + ".py"
            if name in present and name not in reachable:
                reachable.add(name)
                pending.append(name)
assert set(CONVERTER_MODULES) <= reachable, \
    f"{sorted(set(CONVERTER_MODULES) - reachable)} is stamped but nothing imports it"
print("ok  every stamped module is reachable from data_to_yml")


# --- the hash reacts to the bytes of those modules, not just its own file ---------

assert _converter_hash() == _converter_hash(), "the same code must hash the same"
parts = []
for name in CONVERTER_MODULES:
    parts.append(_file_hash(os.path.join(DATA, name)))
assert len(set(parts)) == len(parts), "each module contributes a distinct hash"
assert _file_hash(os.path.join(DATA, "collect.py")) != _converter_hash(), \
    "the converter hash is over the set, not over any single file"
print("ok  _converter_hash spans the set of modules")


# --- is_current is exact: anything different means convert again ------------------

work = tempfile.mkdtemp()
path = os.path.join(work, "capture.yml")


def write(stamp):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"meta": {"source": stamp}, "flaps": None}, f)


good = _source_stamp(CAPTURE, "soak")
write(good)
assert is_current(CAPTURE, path, "soak"), "an untouched yaml is current"

for field, wrong in (("converter", "0" * 32), ("hash", "0" * 32),
                     ("file", "elsewhere.xlsx"), ("test_type", "reset")):
    stamp = dict(good)
    stamp[field] = wrong
    write(stamp)
    assert not is_current(CAPTURE, path, "soak"), \
        f"a different {field} must not be served from cache"
print("ok  is_current: every stamped field invalidates when it differs")

write({"file": good["file"], "hash": good["hash"]})
assert not is_current(CAPTURE, path, "soak"), "a partial stamp is not a match"

with open(path, "w", encoding="utf-8") as f:
    f.write("flaps: []\n")
assert not is_current(CAPTURE, path, "soak"), "a yaml with no meta is not current"

with open(path, "w", encoding="utf-8") as f:
    f.write("}{ not yaml\n")
assert not is_current(CAPTURE, path, "soak"), "an unreadable yaml is not current"

os.remove(path)
assert not is_current(CAPTURE, path, "soak"), "a missing yaml is not current"
print("ok  is_current: a stamp it cannot read is never a match")

print()
print("all tests passed")
