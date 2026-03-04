import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd


def write_qc_flags_by_image(out_root: Path, flags: List[Dict[str, Any]], filename: str = "qc_flags_by_image.csv", verbose: bool = True) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename
    df = pd.DataFrame(flags)
    df.to_csv(out_path, index=False)
    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)}")
    return out_path


def write_qc_flags_by_series(out_root: Path, flags: List[Dict[str, Any]], filename: str = "qc_flags_by_series.csv", verbose: bool = True) -> Path: 
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename
    df = pd.DataFrame(flags)
    df.to_csv(out_path, index=False)
    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)}")
    return out_path


def write_qc_summary(out_root: Path, summary: List[Dict[str, Any]], filename: str = "qc_summary.csv", verbose: bool = True) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename
    df = pd.DataFrame(summary)
    df.to_csv(out_path, index=False)
    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)}")
    return out_path

# Entrypoint
def write_qc_flags_by_image_entrypoint():
    import json
    flags = json.loads(Path(sys.argv[1]).read_text())
    write_qc_flags_by_image(Path("."), flags)


def write_qc_flags_by_series_entrypoint():
    import json
    flags = json.loads(Path(sys.argv[1]).read_text())
    write_qc_flags_by_series(Path("."), flags)


def write_qc_summary_entrypoint():
    import json
    summary = json.loads(Path(sys.argv[1]).read_text())
    write_qc_summary(Path("."), summary)


if __name__ == "__main__":
    entrypoints = {
        "by_image": write_qc_flags_by_image_entrypoint,
        "by_series": write_qc_flags_by_series_entrypoint,
        "summary": write_qc_summary_entrypoint,
    }

    command = sys.argv[1]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    entrypoints[command]()