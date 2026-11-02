"""Spreadsheet cells and rows into values the collectors can use.

Switch names, timestamps and temperatures arrive however the switch wrote them.
"""

from datetime import datetime

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
