"""Whether a capture has already been converted by this code - the stamp covers every
module that converts, so a parser fix invalidates every yaml."""

from pathlib import Path
import hashlib

import yaml

# every module whose contents can change what a capture converts to
CONVERTER_MODULES = ("data_to_yml.py", "collect.py", "parse.py", "meta.py", "sheets.py")

def _file_hash(path):
    digest = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        while True:
            block = f.read(1 << 20)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _converter_hash():
    """One hash over every module that decides what a capture converts to, so a change
    in collect.py or parse.py is not missed the way hashing only this file would."""
    here = Path(__file__).parent
    digest = hashlib.blake2b(digest_size=16)
    for name in CONVERTER_MODULES:
        digest.update(_file_hash(here / name).encode())
    return digest.hexdigest()


def _source_stamp(data, test_type):
    """Everything that can change this yaml's contents."""
    return {
        "file": str(Path(data).resolve()),
        "hash": _file_hash(data),
        # a parser fix leaves every existing yaml wrong, and nothing else would notice
        "converter": _converter_hash(),
        "test_type": test_type,
    }


def is_current(data, yml_file, test_type):
    """Whether yml_file was built from exactly these inputs, by this converter."""
    yml_file = Path(yml_file)
    if not yml_file.exists():
        return False
    try:
        with open(yml_file) as f:
            existing = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(existing, dict):
        return False
    meta = existing.get("meta")
    if meta is None:
        return False
    held = meta.get("source")
    if held is None:
        return False
    return held == _source_stamp(data, test_type)
