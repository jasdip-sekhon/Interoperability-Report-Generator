"""One capture spreadsheet into one measurement yaml. Imports run one way: data_to_yml
-> {collect, meta, sheets, cache} -> parse."""

from pathlib import Path
import sys

from openpyxl import load_workbook
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import line                                       # noqa: E402
from metric_names import METRIC_NAMES                          # noqa: E402

from cache import _source_stamp, is_current
from collect import (collect_ber_from_vdm, collect_link_flaps, collect_link_up,
                     collect_pre_fec_ber, collect_sensors, collect_tcode,
                     collect_temps, collect_uncorrected_cw)
from meta import collect_meta_data
from parse import _log_timestamps
from sheets import _find_sheet, _find_sheet_with_column, _read_sheet, _sheet_records

def _detect_test_type(wb):
    """Guess the testcase from the sheets present: only a reset is distinguishable
    from everything else, so a caller that knows the testcase should say so instead."""
    if _find_sheet(wb, "module_reset", required=False) is None:
        return "soak"
    return "reset"

def _collect_fec_metrics(wb, module_records, test_type):
    """BER (soak only) plus the two counter metrics every test_type gets; the summary
    line already says when BER is absent, so only its source is printed here."""
    fec_sheet = _find_sheet(wb, "get_fec_counter", required=False)
    if fec_sheet is not None:
        fec_records = _read_sheet(fec_sheet)
        tcode = collect_tcode(fec_records)
        uncorrected_cw = collect_uncorrected_cw(fec_records)
        if test_type != "soak":
            return None, None, tcode, uncorrected_cw
        return collect_pre_fec_ber(fec_records), "fec_counter", tcode, uncorrected_cw
    if module_records is not None:
        if test_type != "soak":
            return None, None, None, None
        return collect_ber_from_vdm(module_records), "vdm", None, None
    return None, None, None, None

def _collect_link_up_metrics(wb):
    # named after whichever action produced it, so found by its column
    sheet = _find_sheet_with_column(wb, "LinkUpTime")
    if sheet is None:
        return None
    return collect_link_up(_read_sheet(sheet))

def _section_counts(measurements, sections):
    counts = []
    for section in sections:
        value = measurements[section]
        name = METRIC_NAMES[section]
        if value is None:
            counts.append(f"{name} --")
        else:
            counts.append(f"{name} {len(value)}")
    return ", ".join(counts)


def _report_sections(test_type, measurements):
    """Three units in one line otherwise read as the same kind of number: a lane, an
    optic (one per port, shared by its lanes), and a switch."""
    lanes = _section_counts(measurements, ("flaps", "ber", "tcode",
                                           "uncorrected_cw", "link_up"))
    modules = _section_counts(measurements, ("temps",))
    switches = _section_counts(measurements, ("sensors",))
    line(f"{test_type} capture | per lane: {lanes} | per module: {modules} "
         f"| per switch: {switches}")

def report_cached_capture(data, yml_file):
    """The same two lines a conversion prints, so a reused capture is still named and
    counted in the log rather than hidden behind a "reused" tally."""
    line(Path(data).name + " (reused)")
    with open(yml_file, encoding="utf-8") as f:
        measurements = yaml.safe_load(f)
    _report_sections(measurements["meta"]["test_type"], measurements)


def _read_capture(wb):
    """The four sheets the measurements come from. A missing one reads as None."""
    return (
        _sheet_records(wb, "log",
            "measurements have no timeline, so temperatures will be dropped"),
        _sheet_records(wb, "get_link_flap",
            "the link flap chart will have no data"),
        _sheet_records(wb, "get_module_info",
            "temperatures and the spec limits will be missing"),
        _sheet_records(wb, "get_switch_sensor",
            "the board sensor line will be omitted"),
    )


def collect_measurements(wb, test_type, recovery_commanded):
    """Every section of one capture; a section is null when its sheet was absent,
    which is a different fact from an empty list meaning "found nothing"."""
    log_records, flap_records, module_records, sensor_records = _read_capture(wb)

    if log_records is None:
        timestamps = _log_timestamps([])
    else:
        timestamps = _log_timestamps(log_records)

    ber, ber_source, tcode, uncorrected_cw = _collect_fec_metrics(wb, module_records,
                                                                  test_type)

    if log_records is None:
        meta_log = []
    else:
        meta_log = log_records
    if module_records is None:
        meta_modules = []
    else:
        meta_modules = module_records
    meta = collect_meta_data(meta_log, meta_modules, test_type)
    meta["ber_source"] = ber_source

    if flap_records is None:
        flaps = None
    else:
        flaps = collect_link_flaps(flap_records, recovery_commanded)

    if module_records is None or not timestamps:
        temps = None
    else:
        temps = collect_temps(module_records, timestamps)

    if sensor_records is None or not timestamps:
        sensors = None
    else:
        sensors = collect_sensors(sensor_records, timestamps)

    return {
        "meta": meta,
        "flaps": flaps,
        "ber": ber,
        "tcode": tcode,
        "uncorrected_cw": uncorrected_cw,
        "link_up": _collect_link_up_metrics(wb),
        "temps": temps,
        "sensors": sensors,
    }


def data_to_yml(data, yml_file, test_type=None, recovery_commanded=False):
    # read_only streams the sheets instead of building the whole workbook in memory;
    # on a real 361MB soak that is the difference between seconds and half an hour
    wb = load_workbook(data, read_only=True)
    line(Path(data).name)

    # the caller usually knows which testcase this is; detection is the fallback
    if test_type is None:
        test_type = _detect_test_type(wb)

    try:
        measurements = collect_measurements(wb, test_type, recovery_commanded)
    finally:
        # read_only holds the workbook's zip open until this is called
        wb.close()

    measurements["meta"]["source"] = _source_stamp(data, test_type, recovery_commanded)

    # renamed into place: an interrupt leaves the old yaml, not half of a new one
    partial = Path(yml_file).with_suffix(".partial")
    with open(partial, "w") as f:
        yaml.dump(measurements, f, default_flow_style=False, sort_keys=False)
    partial.replace(yml_file)

    _report_sections(test_type, measurements)
    return measurements
