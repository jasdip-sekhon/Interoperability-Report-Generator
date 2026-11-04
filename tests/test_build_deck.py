"""Tests for assembling the deck.

The point of the manifest is that this script never learns what a metric is, so the
tests lean on that: a made-up chart type and a made-up switch have to work without the
builder recognising either.
"""

import os
import tempfile

import yaml
from PIL import Image
from pptx import Presentation

import _bootstrap
from build_deck import (
    GRID_CELLS,
    GRID_ASPECT,
    PER_SLIDE,
    SINGLE_CELL,
    STACKED_CELLS,
    WIDE_PER_SLIDE,
    build_deck,
    cells_for,
    group_by_metric,
    group_by_scope,
    paginate,
    _caption_for,
    _device_of,
    _fit,
    _heading_for,
    _shows_parts,
)

PICTURE = 13  # MSO_SHAPE_TYPE.PICTURE


def chart(name, scope, title=None, metric=None, aspect=1.33):
    entry = {"file": name, "title": title or name, "scope": scope, "aspect": aspect}
    if metric is not None:
        entry["metric"] = metric
    return entry


WIDE = 3.7      # a full rack on one axis, as the runner renders it
COMPACT = 1.33  # a handful of entries, at the minimum figure size


def write_manifest(folder, charts, test_type="soak"):
    """Charts are written out at the shape their aspect claims, since the builder
    measures the PNG rather than trusting the manifest."""
    entries = []
    for entry in charts:
        size = (int(300 * entry["aspect"]), 300)
        Image.new("RGB", size, "white").save(os.path.join(folder, entry["file"]))
        written = dict(entry)
        del written["aspect"]
        entries.append(written)
    manifest = {"capture": "x.yml", "test_type": test_type,
                "ber_source": "fec_counter", "charts": entries}
    path = os.path.join(folder, "manifest.yml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, sort_keys=False, allow_unicode=True)
    return path


def slide_pictures(slide):
    return [shape for shape in slide.shapes if shape.shape_type == PICTURE]


# --- grouping follows the manifest, it does not sort ------------------------------

groups = group_by_scope([chart("a.png", "all"), chart("b.png", "all"),
                         chart("c.png", "0"), chart("d.png", "4-33")])
assert [scope for scope, _ in groups] == ["all", "0", "4-33"], groups
assert len(groups[0][1]) == 2
print("ok  group_by_scope: manifest order kept, consecutive scopes collected")

# the same scope appearing again later stays a separate group rather than being merged,
# because reordering would contradict the order the runner chose
groups = group_by_scope([chart("a.png", "0"), chart("b.png", "all"), chart("c.png", "0")])
assert [scope for scope, _ in groups] == ["0", "all", "0"]
print("ok  group_by_scope: order wins over tidiness")


# --- pagination ------------------------------------------------------------------

compact = [chart(f"c{i}.png", "all", aspect=COMPACT) for i in range(5)]
assert [len(page) for page in paginate(compact)] == [4, 1]
assert paginate([]) == []
assert [len(page) for page in paginate(compact[:1])] == [1]
print("ok  paginate: splits on the grid size, no empty trailing page")

# a wide chart is letterboxed by a grid cell, so it takes a full-width row and the
# slide holds two instead of four
wide = [chart(f"w{i}.png", "all", aspect=WIDE) for i in range(5)]
assert [len(page) for page in paginate(wide)] == [2, 2, 1]
assert WIDE > GRID_ASPECT > COMPACT, "the threshold must separate the two families"
print(f"ok  paginate: wide charts get {WIDE_PER_SLIDE} full-width rows, not the grid")

# the shapes decide together: one wide chart settles the page it lands on, and a page
# of compact charts closes early rather than cramming a wide one into a quarter
mixed = paginate([chart("a.png", "all", aspect=COMPACT),
                  chart("b.png", "all", aspect=WIDE),
                  chart("c.png", "all", aspect=COMPACT)])
assert [len(page) for page in mixed] == [2, 1], mixed
assert [c["file"] for c in mixed[0]] == ["a.png", "b.png"]
print("ok  paginate: one wide chart sets the capacity of the page it joins")

# the metric leads: it is the only element at a fixed position, since anything before
# it shifts it by its own length from slide to slide
assert _heading_for("Soak", "all", None, None, 1, 1) == "Across all switches · Soak"
assert _heading_for("Soak", "0", None, None, 1, 1) == "Switch 0 · Soak"
assert _heading_for("Soak", "0", None, "Pre-FEC BER", 1, 1) == "Pre-FEC BER · Switch 0 · Soak"
assert (_heading_for("Soak", "0", None, "Pre-FEC BER", 2, 3)
        == "Pre-FEC BER · Switch 0 · Soak · page 2 of 3")
# the model identifies the unit; the address is detail the heading does not carry
assert (_heading_for("Soak", "0", "AZ9074 — 10.0.0.1", "T-Code", 1, 1)
        == "T-Code · Switch 0 · Soak · AZ9074")
# a device belongs to a switch, so "all switches" never claims one
assert (_heading_for("Soak", "all", "AZ9074 — 10.0.0.1", "T-Code", 1, 1)
        == "T-Code · Across all switches · Soak")
print("ok  _heading_for: metric first, then switch, testcase and model, each once")

# two counters on one slide make the reader work out which is which, so the slide
# defers whenever its charts already label themselves
assert _shows_parts([{"file": "a.png", "of": 5}]) is True
assert _shows_parts([{"file": "a.png"}, {"file": "b.png", "of": 1}]) is False
assert _caption_for({"file": "a.png", "part": 2, "of": 5}, "T-Code") == "part 2 of 5"
assert _caption_for({"file": "a.png", "of": 1}, "T-Code") == ""
assert _caption_for({"file": "a.png", "metric": "T-Code"}, None) == "T-Code"
print("ok  _caption_for: the metric when the heading omits it, the part when it does not")

assert _device_of([{"file": "a.png"}, {"file": "b.png", "device": "AZ9074"}]) == "AZ9074"
assert _device_of([{"file": "a.png"}]) is None
print("ok  _device_of: the first chart that names the device speaks for the slide")


# --- a slide holds one metric, and its charts share the room ---------------------

groups = group_by_metric([chart("a.png", "0", metric="BER"),
                          chart("b.png", "0", metric="BER"),
                          chart("c.png", "0", metric="T-Code")])
assert [m for m, _ in groups] == ["BER", "T-Code"], groups
assert len(groups[0][1]) == 2
print("ok  group_by_metric: consecutive charts of one metric share a slide")

groups = group_by_metric([chart("a.png", "0"), chart("b.png", "0")])
assert len(groups) == 1 and groups[0][0] is None,     "a manifest with no metric field must stay one group, as it laid out before"
print("ok  group_by_metric: a manifest without the field is unchanged")

assert cells_for(1) is SINGLE_CELL
assert cells_for(2) is STACKED_CELLS
assert cells_for(3) is GRID_CELLS and cells_for(4) is GRID_CELLS
assert STACKED_CELLS[0][3] > GRID_CELLS[0][3], "two stacked charts keep the full width"
print("ok  cells_for: room per chart follows how many are sharing the slide")


# --- pictures are fitted, never stretched ----------------------------------------

width, height = _fit(4.0, 5.9, 2.25)
assert abs(width / height - 4.0) < 0.01, "a 4:1 chart must stay 4:1"
assert width <= 5.9 + 1e-6 and height <= 2.25 + 1e-6, "and must fit inside the cell"

width, height = _fit(0.25, 5.9, 2.25)
assert height <= 2.25 + 1e-6, "a tall chart is limited by height, not width"
assert abs(width / height - 0.25) < 0.01
print("ok  _fit: aspect preserved, bounded by whichever side runs out first")

# what the whole change is for: the full-width row gives a wide chart room the grid
# cell cannot, and gives a compact one nothing it did not already have
grid_w, grid_h = GRID_CELLS[0][3], GRID_CELLS[0][4]
row_w, row_h = STACKED_CELLS[0][3], STACKED_CELLS[0][4]
assert _fit(WIDE, row_w, row_h)[0] > _fit(WIDE, grid_w, grid_h)[0] * 1.3
assert _fit(COMPACT, row_w, row_h) == _fit(COMPACT, grid_w, grid_h)
print("ok  _fit: a full-width row only pays off for a chart the grid would letterbox")


# --- one chart takes the slide, several share the grid ---------------------------

work = tempfile.mkdtemp()
path = write_manifest(work, [chart("solo.png", "0")])
build_deck(path, os.path.join(work, "one.pptx"))
deck = Presentation(os.path.join(work, "one.pptx"))
only = slide_pictures(deck.slides[2])[0]
assert only.width > GRID_CELLS[0][3] * 914400, \
    "a lone chart should fill the slide, not sit in a quarter of it"
assert SINGLE_CELL[0][3] > GRID_CELLS[0][3]
print("ok  layout: a single chart gets the full slide")

work = tempfile.mkdtemp()
path = write_manifest(work, [chart(f"c{i}.png", "all", aspect=COMPACT)
                             for i in range(PER_SLIDE)])
build_deck(path, os.path.join(work, "grid.pptx"))
deck = Presentation(os.path.join(work, "grid.pptx"))
assert len(slide_pictures(deck.slides[2])) == PER_SLIDE
print(f"ok  layout: {PER_SLIDE} compact charts share one slide")

# end to end, the aspect comes off the PNG - nothing in the manifest declares it
work = tempfile.mkdtemp()
path = write_manifest(work, [chart(f"w{i}.png", "all", aspect=WIDE)
                             for i in range(PER_SLIDE)])
build_deck(path, os.path.join(work, "wide.pptx"))
deck = Presentation(os.path.join(work, "wide.pptx"))
assert [len(slide_pictures(s)) for s in deck.slides] == [0, 0, 2, 2]
placed = slide_pictures(deck.slides[2])[0]
assert placed.width > GRID_CELLS[0][3] * 914400,     "a wide chart must end up wider than the grid cell it would have sat in"
print(f"ok  layout: wide charts measured from the PNG, {WIDE_PER_SLIDE} to a slide")


# --- the builder must not need to recognise anything -----------------------------

work = tempfile.mkdtemp()
charts = [chart("ber.png", "all"),
          chart("brand_new_metric.png", "all"),      # a type added upstream later
          chart("temp_switch_99-7.png", "99-7")]     # a switch named anything
path = write_manifest(work, charts, test_type="shut_unshut")
build_deck(path, os.path.join(work, "unknown.pptx"))
deck = Presentation(os.path.join(work, "unknown.pptx"))
headings = []
for slide in deck.slides:
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip():
            headings.append(shape.text_frame.text.strip())
            break
assert "Shut_Unshut Plots" in headings, headings
assert "Switch 99-7 · Shut_Unshut" in headings, \
    "an unrecognised switch id still gets its own slide, named with its testcase"
total = sum(len(slide_pictures(s)) for s in deck.slides)
assert total == 3, "every chart in the manifest is placed, known or not"
print("ok  unknown metrics, switches and test types all survive untouched")


# --- an empty capture produces a short deck, not a crash -------------------------

work = tempfile.mkdtemp()
path = write_manifest(work, [])
build_deck(path, os.path.join(work, "empty.pptx"))
deck = Presentation(os.path.join(work, "empty.pptx"))
assert len(deck.slides) == 2, "title and section divider only"
print("ok  a capture with no charts still builds")

print()
print("all tests passed")
