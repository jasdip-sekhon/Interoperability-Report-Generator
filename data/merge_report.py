"""What the merge did - entries one run held and another did not are the reason it
exists."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import line, say                                  # noqa: E402

from merge_rules import _index

# the section key as everything else calls it in a sentence, not the internal name
SECTION_NAMES = {
    "flaps": "Link flaps",
    "ber": "BER",
    "tcode": "T-Code",
    "uncorrected_cw": "Uncorrected codewords",
    "link_up": "Link-up time",
    "temps": "Temperature",
    "sensors": "Sensor",
}


def _only_in(runs, labels, section, fields):
    """Which runs hold entries no other run has - the reason the merge exists."""
    notes = []
    for i in range(len(runs)):
        own = set(_index(runs[i].get(section), fields))
        others = set()
        for j in range(len(runs)):
            if j != i:
                others |= set(_index(runs[j].get(section), fields))
        only = len(own - others)
        if only:
            notes.append(f" | {only} only in {labels[i]}")
    return "".join(notes)


def _unit(fields, count):
    """What one entry of this section is: the key it is identified by says so, and a
    lane, an optic and a switch are three different things to count."""
    if len(fields) == 3:
        word = "lane"
    elif len(fields) == 2:
        word = "module"
    else:
        word = "switch"
    if count == 1:
        return word
    if word == "switch":
        return "switches"
    return word + "s"


def _section_line(runs, labels, merged, section, fields):
    name = SECTION_NAMES[section]
    if merged[section] is None:
        return f"  {name:22}   -- (absent from every run)"
    count = len(merged[section])
    line = f"  {name:22} {count:4} {_unit(fields, count)}"
    return line + _only_in(runs, labels, section, fields)


def _count_never_recovered(records):
    total = 0
    for record in records:
        if record["never_recovered"]:
            total = total + 1
    return total


def _report_never_recovered(runs, merged):
    before = []
    for run in runs:
        before.append(str(_count_never_recovered(run["flaps"])))
    after = _count_never_recovered(merged["flaps"])
    say(f"Never recovered: {' + '.join(before)} -> {after} (intersected: a lane that "
        f"recovered in any run is not never-recovered)")


def _report_informational(labels, out_path, conflicts):
    """One line, because nothing reads the merged yaml: the charts come from each run
    on its own, and a reconciliation of DUT against Ref is not a result."""
    line(f"Merged {' + '.join(labels)} -> {Path(out_path).name} (informational union; "
         f"each run is charted on its own)")
    if conflicts:
        if conflicts == 1:
            lane_word = "lane differs"
        else:
            lane_word = "lanes differ"
        say(f"{conflicts} {lane_word} in flap count between the runs")


def _report(runs, labels, merged, offsets, conflicts, out_path, quiet):
    if quiet:
        _report_informational(labels, out_path, conflicts)
        return
    say(f"Merged {len(runs)} runs: {', '.join(labels)}")
    lane = ["switch", "port", "lane"]
    for section, fields in (("flaps", lane), ("ber", lane), ("tcode", lane),
                            ("uncorrected_cw", lane), ("link_up", lane),
                            ("temps", ["switch", "port"]), ("sensors", ["switch"])):
        # a table row, not prose: printed directly so its columns stay aligned
        print(_section_line(runs, labels, merged, section, fields))

    _report_never_recovered(runs, merged)

    for i in range(1, len(labels)):
        say(f"{labels[i]} time-shifted +{offsets[i]:.2f}h onto the shared timeline")
    if conflicts:
        if conflicts == 1:
            lane_word = "lane"
        else:
            lane_word = "lanes"
        say(f"{conflicts} {lane_word} disagreed on flap count between runs")
