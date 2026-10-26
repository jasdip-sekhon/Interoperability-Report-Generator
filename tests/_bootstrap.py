"""Puts every stage's directory on sys.path, so a test can import its module by bare
name the same way the stages import each other (see main.py). Import this before
importing anything under test:

    import _bootstrap
    from data_to_yml import data_to_yml
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
for folder in ("data", "interconnects", "plotting", "deck"):
    sys.path.insert(0, str(PROJECT_ROOT / folder))
