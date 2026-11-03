"""How one line reaches the terminal.

A report prints a few hundred lines and a warning has to survive being skimmed, so
the kind of line is a gutter character rather than a word buried in the sentence, and
nothing is left to the terminal's own wrapping - a 265-character warning soft-wrapped
to the margin loses the indent that tells you which capture it belongs to.
"""

from pathlib import Path
import os
import sys
import textwrap

WIDTH = 96
PROJECT_ROOT = Path(__file__).parent

YELLOW = "\x1b[33m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"


def _enable_windows_vt():
    # the modern terminal understands these already; the legacy console host has to be
    # asked, and if it refuses there is nothing to do but go without colour
    if os.name != "nt":
        return True
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _colour_wanted():
    """Colour is emphasis only. It is dropped whenever the log is going anywhere it
    cannot survive - a file, a pipe, CI - because every line still reads without it."""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return _enable_windows_vt()


COLOUR = _colour_wanted()


def _paint(text, code):
    if not COLOUR:
        return text
    return f"{code}{text}{RESET}"


def _emit(prefix, message, code=None):
    # wrapped first, painted after: an escape code is not a character the reader sees,
    # so counting it against the line width would wrap short
    filled = textwrap.fill(message, width=WIDTH,
                           initial_indent=prefix,
                           subsequent_indent=" " * len(prefix),
                           break_long_words=False, break_on_hyphens=False)
    if code is None:
        print(filled)
        return
    print(_paint(filled, code))


def warn(message):
    _emit("  ! ", message, YELLOW)


def info(message):
    _emit("  - ", message)


def say(message):
    _emit("    ", message)


def header(name):
    print()
    print(_paint(f"== {name} ==", BOLD))


def warn_detail(message, detail):
    """The sentence wraps, the detail does not: 'switch 4-33 port 32' broken across a
    wrap is neither readable nor greppable, and the list is capped short anyway."""
    _emit("  ! ", message, YELLOW)
    print(_paint(f"      {detail}", YELLOW))


def line(message):
    """Printed whole, never wrapped: a path or a row of fields is read and copied as
    one thing, and breaking it mid-field makes the log harder to grep."""
    print(f"    {message}")


def short_path(path):
    """A path inside the project is named relative to it; one outside keeps its full
    name, because which workbook a report charted against is the thing worth knowing."""
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
