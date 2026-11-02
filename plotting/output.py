"""Where one capture's charts go, and the manifest that declares them.

The manifest is the whole contract with deck/, which never learns what a metric is.
"""

from pathlib import Path

import yaml

MANIFEST_NAME = "manifest.yml"


def ensure_output_dir(out_dir):
    Path(out_dir).mkdir(parents=True, exist_ok=True)


def clear_output_dir(out_dir):
    out_dir = Path(out_dir)
    ensure_output_dir(out_dir)
    removed = 0
    for path in out_dir.glob("*.png"):
        path.unlink()
        removed = removed + 1
    if removed:
        print(f"  Cleared {removed} chart(s) from {out_dir.name}/")


def output_path(filename, out_dir):
    ensure_output_dir(out_dir)
    return Path(out_dir) / filename


def _sort_by_scope(charts):
    """Reorder so each switch's charts arrive together, the 'all' ones first.

    Charts keep the order the draw_* functions produced them in, within each switch.
    """
    ordered = []
    for chart in charts:
        if chart["scope"] == "all":
            ordered.append(chart)

    switches = []
    for chart in charts:
        if chart["scope"] != "all" and chart["scope"] not in switches:
            switches.append(chart["scope"])
    switches.sort(key=str)

    for switch in switches:
        for chart in charts:
            if chart["scope"] == switch:
                ordered.append(chart)
    return ordered


def _write_manifest(measurements_yml, meta, charts, out_dir, testcase):
    """Declare what was drawn, in the order it should be presented."""
    if testcase is None:
        testcase = meta["test_type"]
    manifest = {
        "capture": Path(measurements_yml).name,
        "testcase": testcase,
        "test_type": meta["test_type"],
        "ber_source": meta["ber_source"],
        "charts": charts,
    }
    path = Path(out_dir) / MANIFEST_NAME
    partial = path.with_suffix(".partial")
    with open(partial, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)
    partial.replace(path)
    print(f"  Wrote {len(charts)} chart(s) and {path.name}")
    return path
