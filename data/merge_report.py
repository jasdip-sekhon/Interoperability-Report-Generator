"""What the merge did.

Entries one run held and another did not are the reason the merge exists.
"""

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


def _section_line(runs, labels, merged, section, fields):
    name = SECTION_NAMES[section]
    if merged[section] is None:
        return f"  {name:22}   -- (absent from every run)"
    line = f"  {name:22} {len(merged[section]):4} entries"
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
    print(f"  Never recovered: {' + '.join(before)} -> {after} "
          f"(intersected: a lane that recovered in any run is not never-recovered)")


def _report(runs, labels, merged, offsets, conflicts):
    print(f"  Merged {len(runs)} runs: {', '.join(labels)}")
    lane = ["switch", "port", "lane"]
    for section, fields in (("flaps", lane), ("ber", lane), ("tcode", lane),
                            ("uncorrected_cw", lane), ("link_up", lane),
                            ("temps", ["switch", "port"]), ("sensors", ["switch"])):
        print(_section_line(runs, labels, merged, section, fields))

    _report_never_recovered(runs, merged)

    for i in range(1, len(labels)):
        print(f"  {labels[i]} time-shifted +{offsets[i]:.2f}h onto the shared timeline")
    if conflicts:
        if conflicts == 1:
            lane_word = "lane"
        else:
            lane_word = "lanes"
        print(f"  {conflicts} {lane_word} disagreed on flap count between runs")
