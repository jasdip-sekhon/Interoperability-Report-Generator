"""What describes a capture rather than what it measured.

The temperature spec belongs to the switch: a rack can mix optics rated 70C and 75C.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import warn                                       # noqa: E402

from parse import _norm_switch, _parse_temp

def _switch_identity(log_records):
    """{switch: {device_model, device_ip}}, taken from the first row that names them."""
    switches = {}
    for record in log_records:
        switch = _norm_switch(record["TreeL1"])
        if switch is None:
            continue
        if switch not in switches:
            switches[switch] = {"device_model": None, "device_ip": None}
        if switches[switch]["device_model"] is None:
            switches[switch]["device_model"] = record["device_model"]
        if switches[switch]["device_ip"] is None:
            switches[switch]["device_ip"] = record["device_ip"]
    return switches


def _first_start_time(log_records):
    for record in log_records:
        if record["test_start_time"]:
            return str(record["test_start_time"])
    return None


def _one_rating(values, switch, field):
    """The rating a switch's temperature line is drawn at.

    Modules on one switch disagreeing is narrower than a mixed rack, but it still means
    one line cannot represent them all.
    """
    if len(values) > 1:
        rated = []
        for value in sorted(values):
            rated.append(str(value))
        warn(f"switch {switch} has modules rated {', '.join(rated)} for {field}; "
             f"keeping {values[0]}")
    if not values:
        return None
    return values[0]


def _remember(values, value):
    if value is not None and value not in values:
        values.append(value)


def _switch_temp_limits(module_records):
    """{switch: {temp_min, temp_max}}.

    The spec rides on every module row, and a rack can mix optics with different
    ratings (70C and 75C are both common). Each temperature chart covers one switch and
    draws one limit line, so the spec belongs to the switch, not the capture.
    """
    seen = {}
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        if switch is None:
            continue
        if switch not in seen:
            seen[switch] = {"temp_min": [], "temp_max": []}
        _remember(seen[switch]["temp_min"], _parse_temp(record["MinModuleTemperature"]))
        _remember(seen[switch]["temp_max"], _parse_temp(record["MaxModuleTemperature"]))

    limits = {}
    for switch in seen:
        limits[switch] = {
            "temp_min": _one_rating(seen[switch]["temp_min"], switch, "temp_min"),
            "temp_max": _one_rating(seen[switch]["temp_max"], switch, "temp_max"),
        }
    return limits


def collect_meta_data(log_records, module_records, test_type):
    switches = _switch_identity(log_records)
    limits = _switch_temp_limits(module_records)
    # a switch can appear in the module rows without appearing in the log
    for switch in limits:
        if switch not in switches:
            switches[switch] = {"device_model": None, "device_ip": None}
        for field in limits[switch]:
            switches[switch][field] = limits[switch][field]

    return {
        "test_type": test_type,
        "start_time": _first_start_time(log_records),
        "switches": switches,
    }
