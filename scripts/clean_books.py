#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rich import print

from trading_llm.clean import clean_extracted_dir
from trading_llm.paths import ensure_dirs, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean extracted book sections")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = ensure_dirs(args.root)
    report = clean_extracted_dir(root / "extracted", root / "cleaned")
    out = root / "reports" / "cleaning.json"
    save_json(out, report)
    print({k: report[k] for k in report if k != "per_book"})
    print(f"Saved report: {out}")


if __name__ == "__main__":
    main()
