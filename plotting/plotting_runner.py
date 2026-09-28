from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)

def output_path(filename):
    ensure_output_dir()
    return OUTPUT_DIR / filename
