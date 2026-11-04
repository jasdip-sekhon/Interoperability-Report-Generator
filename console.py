"""How one line reaches the terminal: a gutter character marks its kind, and nothing
is left to the terminal's own wrapping, which would otherwise lose the indent."""

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
    """Emphasis only, dropped wherever it cannot survive (a file, a pipe, CI) since
    every line still reads without it."""
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


def say(message):
    _emit("    ", message)


def margin(message):
    """At the left margin, unwrapped: a fact about the whole report, not about any
    one testcase under it."""
    print(message)


def header(name):
    print()
    print(_paint(f"== {name} ==", BOLD))


def warn_detail(message, detail):
    """The sentence wraps, the identifier list does not - breaking it mid-entry would
    make it neither readable nor greppable."""
    _emit("  ! ", message, YELLOW)
    print(_paint(f"      {detail}", YELLOW))


def line(message):
    """Printed whole, never wrapped: a path or field row is read and copied as one
    thing."""
    print(f"    {message}")


def short_path(path):
    """Relative, inside the project; full, outside it - knowing which workbook a
    report used matters more than a short path."""
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
