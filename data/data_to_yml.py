from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook
import yaml

VDM_PREFEC_PREFIX = "VDM_Pre-FEC_BER_Average_Media_Input_Lane_"
SENSOR_COLUMN = "mb_asc5_temp1_Q88_frontrighttop_C"

def _find_sheet(wb, sheet_name, required=True):
    # Search for a sheet by name, allowing for a numeric prefix before an underscore
    for name in wb.sheetnames:
        parts = name.split("_", 1)
        if len(parts) == 2 and parts[1] == sheet_name:
            return wb[name]
    if required:
        raise ValueError(f"Sheet '{sheet_name}' not found in workbook.")
    return None

def _find_sheet_with_column(wb, column):
    # the link-up sheet is named after whatever action produced it, so it is located by
    # the column it carries rather than by name
    for name in wb.sheetnames:
        sheet = wb[name]
        for row in sheet.iter_rows(values_only=True, max_row=1):
            if column in row:
                return sheet
    return None

def _sheet_records(wb, sheet_name, consequence):
    # a capture missing one sheet still has good data in the others, so drop just that
    # section rather than the whole file — but say which chart goes dark because of it
    sheet = _find_sheet(wb, sheet_name, required=False)
    if sheet is None:
        print(f"  Warning: no '*{sheet_name}' sheet; {consequence}.")
        return None
    return _read_sheet(sheet)

def _read_sheet(sheet):
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(row)
    if not rows:
        return []

    headers = rows[0]
    data = []
    for row in rows[1:]:
        record = {}
        i = 0
        for header in headers:
            if i < len(row):
                record[header] = row[i]
            i = i + 1
        data.append(record)
    return data

def _norm_switch(value):
    # Normalize switch values to strings
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()

def _group_by_lane(records, column):
    # TreeL1/L2/L3 is switch/port/lane; one capture samples each lane many times
    lanes = {}
    for record in records:
        key = (_norm_switch(record["TreeL1"]), record["TreeL2"], record["TreeL3"])
        if key not in lanes:
            lanes[key] = []
        lanes[key].append(record[column])
    return lanes

def collect_link_flaps(flap_records, test_type):
    lanes = _group_by_lane(flap_records, "Down->Up")

    flap_data = []
    for key in lanes:
        switch, port, lane = key
        raw_values = lanes[key]

        # Fixes the "Down->Up" count by subtracting 1 from each value
        count = 0
        for raw in raw_values:
            if raw is None:
                continue
            corrected = max(0, raw - 1)
            if corrected > count:
                count = corrected

        # Determine if the link never recovered (all raw values are 0)
        if test_type == "soak":
            never_recovered = None
        else:
            never_recovered = True
            for raw in raw_values:
                if raw != 0:
                    never_recovered = False

        flap_data.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "count": count,
            "never_recovered": never_recovered,
        })
    return flap_data

def _lanes_to_records(lanes):
    records = []
    for key in lanes:
        switch, port, lane = key
        records.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "values": lanes[key],
        })
    return records

def collect_pre_fec_ber(ber_records):
    return _lanes_to_records(_group_by_lane(ber_records, "FEC_BER"))


def collect_ber_from_vdm(module_records):
    # has the same structure as collect_pre_fec_ber but uses the VDM columns instead of a single FEC_BER column
    lanes = {}
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        for lane in range(1, 9):
            column = VDM_PREFEC_PREFIX + str(lane)
            if column not in record:
                continue
            key = (switch, port, lane)
            if key not in lanes:
                lanes[key] = []
            lanes[key].append(record[column])

    return _lanes_to_records(lanes)

def collect_tcode(fec_records):
    # only some switches have this measured; a None here means "not measured" and must
    # not become a 0 — that would report a switch as passing a spec it never ran
    return _lanes_to_records(_group_by_lane(fec_records, "tcode2"))

def collect_uncorrected_cw(fec_records):
    return _lanes_to_records(_group_by_lane(fec_records, "UNCORR_CW"))

def collect_link_up(reset_records):
    # seconds from admin-up to link-up, per lane
    return _lanes_to_records(_group_by_lane(reset_records, "LinkUpTime"))

def _parse_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")

def _log_timestamps(log_records):
    # measurement sheets carry no clock of their own — each row joins back to the log
    # on (Repeat, test_step, TreeL1). Repeat can be 'init', so all three go in as strings.
    timestamps = {}
    for record in log_records:
        if not record["test_start_time"]:
            continue
        key = (str(record["Repeat"]), str(record["test_step"]),
               str(_norm_switch(record["TreeL1"])))
        timestamps[key] = _parse_time(record["test_start_time"])
    return timestamps

def _elapsed_hours(timestamps):
    start = None
    for key in timestamps:
        when = timestamps[key]
        if start is None or when < start:
            start = when
    return start

def collect_temps(module_records, timestamps):
    # one optic per PORT, so there is no lane here — all 8 lanes share this reading
    start = _elapsed_hours(timestamps)
    modules = {}
    unmatched = 0
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        temp = _parse_temp(record["ModuleMonitorsModuleMonitorInternalTemperature"])

        module_key = (switch, port)
        if module_key not in modules:
            modules[module_key] = []
        modules[module_key].append([round(hours, 4), temp])

    if unmatched:
        print(f"  Info: {unmatched} module temperature reading(s) had no "
              f"matching log timestamp and were dropped.")

    temp_data = []
    for module_key in modules:
        switch, port = module_key
        # a value-coloured line is drawn segment by segment, so order matters
        points = sorted(modules[module_key])
        temp_data.append({
            "switch": switch,
            "port": port,
            "points": points,
        })
    return temp_data

def collect_sensors(sensor_records, timestamps):
    # one reading per switch, not per port — this is a sensor on the switch board
    start = _elapsed_hours(timestamps)
    switches = {}
    unmatched = 0
    for record in sensor_records:
        switch = _norm_switch(record["TreeL1"])
        value = record[SENSOR_COLUMN]
        # only some switch models carry this sensor; on the rest the column is blank
        if value is None:
            continue
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        if switch not in switches:
            switches[switch] = []
        switches[switch].append([round(hours, 4), float(value)])

    if unmatched:
        print(f"  Info: {unmatched} sensor reading(s) had no matching log "
              f"timestamp and were dropped.")

    sensor_data = []
    for switch in switches:
        sensor_data.append({
            "switch": switch,
            "name": SENSOR_COLUMN,
            "points": sorted(switches[switch]),
        })
    return sensor_data

def _parse_temp(value):
    # readings carry a unit suffix with inconsistent spacing: '70 C', '72.9141C'
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("C"):
        text = text[:-1].strip()
    if not text:
        return None
    return float(text)

def collect_meta_data(log_records, module_records, test_type):
    # model and IP differ per switch
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

    start_time = None
    for record in log_records:
        if record["test_start_time"]:
            start_time = str(record["test_start_time"])
            break

    # the spec rides on every module row, and a rack can mix optics with different
    # ratings (70C and 75C are both common). Each temperature chart covers one switch
    # and draws one limit line, so the spec belongs to the switch, not the capture.
    seen = {}
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        if switch is None:
            continue
        if switch not in switches:
            switches[switch] = {"device_model": None, "device_ip": None}
        if switch not in seen:
            seen[switch] = {"temp_min": [], "temp_max": []}
        for field, column in (("temp_min", "MinModuleTemperature"),
                              ("temp_max", "MaxModuleTemperature")):
            value = _parse_temp(record[column])
            if value is not None and value not in seen[switch][field]:
                seen[switch][field].append(value)

    for switch in seen:
        for field in ("temp_min", "temp_max"):
            values = seen[switch][field]
            # modules on one switch disagreeing is a narrower problem than a mixed rack,
            # but it still means one line cannot represent them all
            if len(values) > 1:
                print(f"  Warning: switch {switch} has modules rated {sorted(values)} "
                      f"for {field}; keeping {values[0]}.")
            if values:
                switches[switch][field] = values[0]
            else:
                switches[switch][field] = None

    return {
        "test_type": test_type,
        "start_time": start_time,
        "switches": switches,
    }


def _detect_test_type(wb):
    # a reset capture records the reset step it performed; soak has no such sheet
    if _find_sheet(wb, "module_reset", required=False) is None:
        return "soak"
    return "reset"

def _collect_fec_metrics(wb, module_records):
    """BER, plus the two metrics only the switch ASIC's counter carries.

    The ASIC counter and the optic's own VDM reading are different instruments and must
    never be pooled, so which one was used travels with the data. T-Code and uncorrected
    codewords exist only on the counter, so a capture that falls back to VDM has neither.
    """
    fec_sheet = _find_sheet(wb, "get_fec_counter", required=False)
    if fec_sheet is not None:
        print("  Info: BER read from the switch ASIC's '*get_fec_counter'.")
        fec_records = _read_sheet(fec_sheet)
        return (collect_pre_fec_ber(fec_records), "fec_counter",
                collect_tcode(fec_records), collect_uncorrected_cw(fec_records))
    if module_records is not None:
        print("  Info: no '*get_fec_counter' sheet; using the module's own VDM "
              "Pre-FEC BER instead. T-Code and uncorrected codewords are unavailable.")
        return collect_ber_from_vdm(module_records), "vdm", None, None
    return None, None, None, None

def _collect_link_up_metrics(wb):
    # named after whichever action produced it, so found by its column
    sheet = _find_sheet_with_column(wb, "LinkUpTime")
    if sheet is None:
        print("  Info: no sheet carries a 'LinkUpTime' column; link-up times are "
              "unavailable.")
        return None
    return collect_link_up(_read_sheet(sheet))

def _report_sections(test_type, measurements):
    counts = []
    for section in ("flaps", "ber", "tcode", "uncorrected_cw", "link_up",
                    "temps", "sensors"):
        value = measurements[section]
        if value is None:
            counts.append(f"{section} --")
        else:
            counts.append(f"{section} {len(value)}")
    print(f"  {test_type} capture | " + " | ".join(counts))

def data_to_yml(data, yml_file):
    # read_only streams the sheets instead of building the whole workbook in memory;
    # on a real 361MB soak that is the difference between seconds and half an hour
    wb = load_workbook(data, read_only=True)
    print(f"{Path(data).name}")

    test_type = _detect_test_type(wb)

    log_records = _sheet_records(wb, "log",
        "measurements have no timeline, so temperatures will be dropped")
    flap_records = _sheet_records(wb, "get_link_flap",
        "the link flap chart will have no data")
    module_records = _sheet_records(wb, "get_module_info",
        "temperatures and the spec limits will be missing")
    sensor_records = _sheet_records(wb, "get_switch_sensor",
        "the board sensor line will be omitted")

    timestamps = _log_timestamps(log_records or [])
    ber, ber_source, tcode, uncorrected_cw = _collect_fec_metrics(wb, module_records)
    link_up = _collect_link_up_metrics(wb)

    meta = collect_meta_data(log_records or [], module_records or [], test_type)
    meta["ber_source"] = ber_source

    # a section is null when its sheet was absent — "could not look", which is a
    # different fact from an empty list meaning "looked, found nothing"
    if flap_records is None:
        flaps = None
    else:
        flaps = collect_link_flaps(flap_records, test_type)

    if module_records is None or not timestamps:
        temps = None
    else:
        temps = collect_temps(module_records, timestamps)

    if sensor_records is None or not timestamps:
        sensors = None
    else:
        sensors = collect_sensors(sensor_records, timestamps)

    measurements = {
        "meta": meta,
        "flaps": flaps,
        "ber": ber,
        "tcode": tcode,
        "uncorrected_cw": uncorrected_cw,
        "link_up": link_up,
        "temps": temps,
        "sensors": sensors,
    }

    with open(yml_file, "w") as f:
        yaml.dump(measurements, f, default_flow_style=False, sort_keys=False)

    _report_sections(test_type, measurements)
    return measurements


if __name__ == "__main__":
    references = Path(__file__).parent.parent / "references"
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    captures = ["soak_sample.xlsx", "reset_dut_sample.xlsx", "reset_ref_sample.xlsx"]
    for capture in captures:
        output_yml = output_dir / (Path(capture).stem + ".yml")
        data_to_yml(references / capture, output_yml)
        print(f"Wrote {output_yml}")
        print(f"  {output_yml.stat().st_size} bytes")