from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# --- Make project root importable ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports from your project ---
from src.io.parsing.file_scanner import scan_dicom_files
from src.io.parsing.dicom_reader import read_dicom_header

# Step 2 processing
from src.processing.series_grouper import group_records_by_series, sort_series_records, build_series_index

# Config (assumes you have these)
import src.config as cfg


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def short(v: Any, maxlen: int = 80) -> str:
    s = str(v)
    return s if len(s) <= maxlen else s[: maxlen - 3] + "..."


def main() -> None:
    data_root = PROJECT_ROOT / "data"
    out_root = data_root / "out"
    ensure_dir(out_root)

    print("TEST PIPELINE")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Data root:    {data_root}")

    # 1) Scan files
    ignore_ext = getattr(cfg, "PARSER_CONFIG", {}).get("ignore_extensions", [])
    files = scan_dicom_files(data_root, ignore_ext)

    print(f"\n[1] Scan")
    print(f"Found {len(files)} candidate files under {data_root}")
    if not files:
        print("No files found. Put DICOMs under ./data and re-run.")
        return

    # 2) Read headers -> records
    print(f"\n[2] Read headers")
    stop_before_pixels = getattr(cfg, "PARSER_CONFIG", {}).get("stop_before_pixels", True)
    force_read = getattr(cfg, "PARSER_CONFIG", {}).get("force_read", True)

    # Tags to extract: prefer cfg.all_tags(), else minimal fallback
    if hasattr(cfg, "all_tags"):
        tag_names = cfg.all_tags()
    else:
        tag_names = [
            # grouping
            "StudyInstanceUID", "SeriesInstanceUID",
            # sorting
            "InstanceNumber", "ImagePositionPatient", "ImageOrientationPatient",
            # core tags
            "Modality", "PixelSpacing", "SliceThickness", "Rows", "Columns", "SeriesDescription",
        ]

    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for f in files:
        out = read_dicom_header(
            f,
            tag_names,
            stop_before_pixels=stop_before_pixels,
            force_read=force_read,
        )
        if out.get("record") is None:
            errors.append({"file": str(f), "error": out.get("error")})
            continue
        records.append(out["record"])

    print(f"Parsed records: {len(records)}")
    print(f"Read errors:    {len(errors)}")
    if errors:
        print("  First 5 errors:")
        for e in errors[:5]:
            print(f"   - {e['file']}: {e['error']}")

    if not records:
        print("No valid DICOM headers parsed. Check read_dicom_header / force_read.")
        return

    # 3) Grouping test (Step 2a)
    print(f"\n[3] Grouping by (StudyInstanceUID, SeriesInstanceUID)")
    groups = group_records_by_series(records)
    print(f"Groups found: {len(groups)}")

    if groups:
        # Print a few groups
        for i, (key, recs) in enumerate(groups.items()):
            #if i >= 5:
            #    break
            print(f"  - Group {i+1}: Study={short(key[0], 24)} Series={short(key[1], 24)} n={len(recs)}")

    # 4) Sorting test (Step 2b) on a few groups
    print(f"\n[4] Sorting within series (preview)")
    #preview_n = 5
    for i, (key, recs) in enumerate(groups.items()):
    #    if i >= preview_n:
    #        break
        sorted_recs, method, issues = sort_series_records(recs)
        inst_first = sorted_recs[0].get("InstanceNumber") if sorted_recs else None
        inst_last = sorted_recs[-1].get("InstanceNumber") if sorted_recs else None
        print(f"  - Series {i+1}: n={len(recs)} sort_method={method} "
              f"InstanceNumber(first,last)=({inst_first},{inst_last})")
        if issues:
            print(f"    issues: {issues}")

    # 5) Full series index (Task 2 output structure)
    print(f"\n[5] build_series_index (full)")
    series_index = build_series_index(records)
    print(f"Indexed series: {len(series_index)}")

    # Summary counts by sort method
    by_method: Dict[str, int] = {}
    issues_count = 0
    for _, info in series_index.items():
        m = info.get("sort_method", "unknown")
        by_method[m] = by_method.get(m, 0) + 1
        if info.get("issues"):
            issues_count += 1

    print("Sort method distribution:")
    for m, c in sorted(by_method.items(), key=lambda x: x[0]):
        print(f"  {m:16s}: {c}")

    print(f"Series with issues: {issues_count}")

    # Output report in data/out
    import pandas as pd  # optional dependency
    df_meta = pd.DataFrame(records)
    df_meta.to_csv(out_root / "metadata.csv", index=False)

    # Build series report
    series_rows = []
    for (study_uid, series_uid), info in series_index.items():
        series_rows.append({
            "StudyInstanceUID": study_uid,
            "SeriesInstanceUID": series_uid,
            "n_instances": info.get("n_instances"),
            "sort_method": info.get("sort_method"),
            "modality": info.get("modality"),
            "series_description": info.get("series_description"),
            "issues": " | ".join(info.get("issues", [])),
        })
    df_series = pd.DataFrame(series_rows)
    df_series.to_csv(out_root / "series_report.csv", index=False)
    print("\nDONE")


if __name__ == "__main__":
    main()
