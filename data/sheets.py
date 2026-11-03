"""A capture workbook into header-keyed records.

The active sheet is whichever was open when the file was saved, so sheets go by name.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import warn                                       # noqa: E402

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
        warn(f"no '*{sheet_name}' sheet; {consequence}.")
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
