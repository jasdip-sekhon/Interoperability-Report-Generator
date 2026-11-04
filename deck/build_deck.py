"""Turn a folder of rendered charts into a slide deck, reading the manifest the
plotting runner writes rather than the file names, so it knows nothing about switches,
metrics or test types. Charts appear in manifest order, grouped by scope - the ones
covering the whole capture first, then one group per switch."""

from pathlib import Path
import argparse
import sys

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import short_path                                 # noqa: E402
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5

# borrowed from the hand-built decks so the generated ones sit at the same measurements
HEADING = (0.35, 0.20, 12.6, 0.42)
RULE = (0.20, 0.82, 12.9, 0.03)

# a cell is (x, caption y, picture y, width, height); a picture is fitted inside it.
GRID_CELLS = ((0.35, 0.97, 1.24, 5.9, 2.25), (6.85, 0.97, 1.24, 5.9, 2.25),
              (0.35, 3.71, 3.98, 5.9, 2.25), (6.85, 3.71, 3.98, 5.9, 2.25))
# one chart gets the whole slide rather than a lonely quarter of it
SINGLE_CELL = ((0.35, 0.97, 1.30, 12.6, 4.90),)
# two share the slide's full width, one above the other, on the grid's own two rows
STACKED_CELLS = ((0.35, 0.97, 1.24, 12.6, 2.25), (0.35, 3.71, 3.98, 12.6, 2.25))
PER_SLIDE = len(GRID_CELLS)

RULE_COLOUR = RGBColor(0x7F, 0x7F, 0x7F)


def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _blank_slide(presentation):
    # layout 6 is Blank in the default template: no placeholders to work around
    return presentation.slides.add_slide(presentation.slide_layouts[6])


def _add_text(slide, box, text, size, bold=False):
    left, top, width, height = box
    shape = slide.shapes.add_textbox(Inches(left), Inches(top),
                                     Inches(width), Inches(height))
    frame = shape.text_frame
    frame.word_wrap = True
    run = frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    return shape


def _add_rule(slide):
    left, top, width, height = RULE
    shape = slide.shapes.add_shape(1, Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RULE_COLOUR
    shape.line.fill.background()
    shape.shadow.inherit = False


def _fit(image_path, max_width, max_height):
    """Scale an image to fit a cell without distorting it - chart aspect ratios differ
    too much (a wide box plot, a near-square temperature chart) for a fixed size."""
    with Image.open(image_path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return width * scale, height * scale


def _caption_for(chart, slide_metric):
    """What this chart is that the slide heading has not said already - its metric on a
    slide mixing several, otherwise just which part of one axis it covers."""
    caption = chart["title"]
    if slide_metric and caption.startswith(slide_metric):
        caption = caption[len(slide_metric):].strip()
    return caption


def _place_chart(slide, chart, cell, charts_dir, slide_metric=None):
    x, caption_y, picture_y, cell_w, cell_h = cell
    caption = _caption_for(chart, slide_metric)
    if caption:
        _add_text(slide, (x, caption_y, cell_w, 0.24), caption, 10)
    path = charts_dir / chart["file"]
    width, height = _fit(path, cell_w, cell_h)
    # centre it horizontally in the cell, so narrow charts are not left-stranded
    left = x + (cell_w - width) / 2
    slide.shapes.add_picture(str(path), Inches(left), Inches(picture_y),
                             Inches(width), Inches(height))


def add_title_slide(presentation, report, manifests):
    slide = _blank_slide(presentation)
    _add_text(slide, (0.9, 2.6, 11.5, 0.9), f"Interoperability Test Report — {report}",
              34, bold=True)
    names = []
    for manifest in manifests:
        names.append(manifest.get("testcase") or manifest["test_type"])
    _add_text(slide, (0.9, 3.6, 11.5, 0.5), " · ".join(names) or "no testcases", 14)
    return slide


def add_section_slide(presentation, text):
    slide = _blank_slide(presentation)
    _add_text(slide, (0.55, 2.85, 12.2, 0.7), text, 26, bold=True)
    _add_rule(slide)
    return slide


def cells_for(count):
    """Charts get the room left over once they are sharing a slide, not a fixed size."""
    if count == 1:
        return SINGLE_CELL
    if count == 2:
        return STACKED_CELLS
    return GRID_CELLS


def add_chart_slide(presentation, heading, charts, charts_dir, slide_metric=None):
    slide = _blank_slide(presentation)
    _add_text(slide, HEADING, heading, 16, bold=True)
    _add_rule(slide)
    for chart, cell in zip(charts, cells_for(len(charts))):
        _place_chart(slide, chart, cell, charts_dir, slide_metric)
    return slide


def group_by_scope(charts):
    """[(scope, charts)] in manifest order - the runner decides what order means."""
    groups = []
    for chart in charts:
        if not groups or groups[-1][0] != chart["scope"]:
            groups.append((chart["scope"], []))
        groups[-1][1].append(chart)
    return groups


def group_by_metric(charts):
    """[(metric, charts)] - a slide holds one metric, so its charts are comparable; no
    metric field groups everything as one, matching decks built before the field existed."""
    groups = []
    for chart in charts:
        metric = chart.get("metric")
        if not groups or groups[-1][0] != metric:
            groups.append((metric, []))
        groups[-1][1].append(chart)
    return groups


def paginate(items, size):
    pages = []
    for start in range(0, len(items), size):
        pages.append(items[start:start + size])
    return pages


def slide_plan(charts):
    """[(metric, number, count, charts)] - one entry per slide. A metric with several
    charts gets slides of its own so its pages sit together; single-chart metrics are
    packed onto a shared slide, since one chart does not earn a slide of its own."""
    singles = []
    runs = []
    for metric, of_metric in group_by_metric(charts):
        if len(of_metric) == 1:
            singles.extend(of_metric)
        else:
            runs.append((metric, of_metric))

    plan = []
    pages = paginate(singles, PER_SLIDE)
    number = 1
    for page in pages:
        plan.append((None, number, len(pages), page))
        number = number + 1
    for metric, of_metric in runs:
        pages = paginate(of_metric, PER_SLIDE)
        number = 1
        for page in pages:
            plan.append((metric, number, len(pages), page))
            number = number + 1
    return plan


def _device_of(charts):
    """Whatever the charts say they came from - one scope is one device, so the first
    that names it speaks for the slide."""
    for chart in charts:
        if chart.get("device"):
            return chart["device"]
    return None


def _heading_for(name, scope, device, metric, page_number, page_count):
    # everything true of the whole slide is said here, once: the testcase (a slide
    # scrolled to on its own must still name it), the switch, and what that switch is
    heading = name
    if scope == "all":
        heading = f"{heading} — Across all switches"
    else:
        heading = f"{heading} — Switch {scope}"
        if device:
            heading = f"{heading} ({device})"
    if metric:
        heading = f"{heading} — {metric}"
    if page_count > 1:
        heading = f"{heading} (page {page_number} of {page_count})"
    return heading


def add_testcase(presentation, manifest, charts_dir):
    """A section divider and the chart slides under it. Returns the slide count."""
    # a configured testcase name is human-written, so it is used as typed; a detected
    # one is a lowercase slug and needs capitalising. Detection cannot tell a
    # shut/no-shut run from a soak, which is why the configured name wins.
    name = manifest.get("testcase")
    if not name:
        name = manifest["test_type"].title()
    add_section_slide(presentation, f"{name} Plots")
    slides = 1
    for scope, charts in group_by_scope(manifest["charts"]):
        device = _device_of(charts)
        for metric, number, count, page in slide_plan(charts):
            add_chart_slide(presentation,
                            _heading_for(name, scope, device, metric, number, count),
                            page, charts_dir, metric)
            slides = slides + 1
    return slides


def build_deck(manifest_paths, out_path, report="Report"):
    """One deck from one or more testcases, each its own section - charts live next to
    their own manifest, so separate testcase folders can combine without overwriting
    each other's files."""
    if isinstance(manifest_paths, (str, Path)):
        manifest_paths = [manifest_paths]

    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_WIDTH)
    presentation.slide_height = Inches(SLIDE_HEIGHT)

    manifests = []
    for path in manifest_paths:
        manifests.append(load_manifest(path))

    add_title_slide(presentation, report, manifests)
    slides = 1
    charts = 0
    for path, manifest in zip(manifest_paths, manifests):
        slides = slides + add_testcase(presentation, manifest, Path(path).parent)
        charts = charts + len(manifest["charts"])

    presentation.save(out_path)
    if charts == 1:
        chart_word = "chart"
    else:
        chart_word = "charts"
    if len(manifests) == 1:
        testcase_word = "testcase"
    else:
        testcase_word = "testcases"
    print(f"Wrote {short_path(out_path)}\n"
          f"  {slides} slides from {charts} {chart_word} across "
          f"{len(manifests)} {testcase_word}")
    return presentation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifests", nargs="+",
                        help="manifest.yml files, one per testcase, in deck order")
    parser.add_argument("-o", "--out", required=True, help="the .pptx to write")
    parser.add_argument("--report", default="Report", help="name for the title slide")
    args = parser.parse_args()
    build_deck(args.manifests, args.out, args.report)
