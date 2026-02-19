from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# --- Make project root importable ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports from your project ---
from src.inout.parsing.file_scanner import scan_dicom_files
from src.inout.parsing.dicom_reader import read_dicom_header

# Step 2 processing
from src.processing.series_grouper import group_records_by_series, sort_series_records, build_series_index

# Step 3 processing
from src.processing.volume_builder import build_volume, save_volume_outputs

# Pixel reader
from src.inout.parsing.dicom_reader import read_pixel_array_from_record

# Report
from src.inout.report import write_metadata_csv, write_series_report_csv, write_volumes_report_csv, write_missing_tags_tables, write_read_errors_csv

# Config
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
            "StudyInstanceUID", "SeriesInstanceUID"
            # sorting
            "InstanceNumber", "ImagePositionPatient", "ImageOrientationPatient"
            # core tags
            "Modality", "PixelSpacing", "SliceThickness", "Rows", "Columns", "SeriesDescription"
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
        for i, (key, recs) in enumerate(groups.items()):
            print(f"  - Group {i+1}: Study={short(key[0], 24)} Series={short(key[1], 24)} n={len(recs)}")

    # 4) Sorting test (Step 2b) on a few groups
    print(f"\n[4] Sorting within series")
    for i, (key, recs) in enumerate(groups.items()):
        sorted_recs, method, issues = sort_series_records(recs)
        inst_first = sorted_recs[0].get("InstanceNumber") if sorted_recs else None
        inst_last = sorted_recs[-1].get("InstanceNumber") if sorted_recs else None
        print(f"  - Series {i+1}: n={len(recs)} sort_method={method} "
              f"InstanceNumber(first,last)=({inst_first},{inst_last})")
        if issues:
            print(f"    issues: {issues}")

    # 5) Full series index
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

    # [6] STEP 3 - Build volumes for reconstructable series
    print(f"\n[6] Build volumes")
    volumes_dir = out_root / "volumes"
    ensure_dir(volumes_dir)

    volumes_rows = []
    built_ok = 0
    built_fail = 0

    for (study_uid, series_uid), info in series_index.items():
        sorted_recs = info.get("records_sorted") or []
        first_file = ""
        if sorted_recs:
            fp = sorted_recs[0].get("file_path")
            first_file = str(fp) if fp is not None else ""

        n_files = len(sorted_recs)

        if not sorted_recs:
            volumes_rows.append({
                "first_file": first_file,
                "StudyInstanceUID": study_uid,
                "SeriesInstanceUID": series_uid,
                "status": "skip",
                "reason": "empty records_sorted",
                "n_input": 0,
                "n_slices_built": 0,
                "out_volume": "",
                "out_geometry": "",
                "out_issues": "",
                "issues": "empty series",
            })
            continue

        # Try building a volume
        vol, geom, issues = build_volume(sorted_recs, read_pixel_array_from_record)

        if vol is None or geom is None:
            built_fail += 1
            volumes_rows.append({
                "first_file": first_file,
                "StudyInstanceUID": study_uid,
                "SeriesInstanceUID": series_uid,
                "status": "fail",
                "reason": "not reconstructable or geometry/pixels invalid",
                "n_input": len(sorted_recs),
                "n_slices_built": 0,
                "out_volume": "",
                "out_geometry": "",
                "out_issues": "",
                "issues": " | ".join(issues[:10]) + (" | ..." if len(issues) > 10 else ""),
            })
            continue

        # Save outputs
        vol_path, geo_path, iss_path = save_volume_outputs(
            volumes_dir, (study_uid, series_uid), vol, geom, issues
        )

        built_ok += 1
        volumes_rows.append({
            "first_file": first_file,
            "StudyInstanceUID": study_uid,
            "SeriesInstanceUID": series_uid,
            "status": "ok",
            "reason": "",
            "n_input": len(sorted_recs),
            "n_slices_built": int(vol.shape[0]),
            "out_volume": str(vol_path),
            "out_geometry": str(geo_path),
            "out_issues": str(iss_path),
            "spacing_x": geom["spacing"][0],
            "spacing_y": geom["spacing"][1],
            "spacing_z": geom["spacing"][2],
            "rows": geom["rows"],
            "cols": geom["cols"],
            "modality": geom.get("modality"),
            "series_description": geom.get("series_description"),
            "issues": " | ".join(issues[:10]) + (" | ..." if len(issues) > 10 else ""),
        })

    print(f"Volumes built OK:   {built_ok}")
    print(f"Volumes built FAIL: {built_fail}")


    # Report
    # 1) metadata
    write_metadata_csv(out_root, records)

    # 2) series report
    write_series_report_csv(out_root, series_rows)

    # 3) volumes report
    write_volumes_report_csv(out_root, volumes_rows)

    # 4) read errors
    write_read_errors_csv(out_root, errors)

    # 5) missing tags tables (usa esattamente i tag estratti nello step 1)
    required_tags = cfg.essential_tags()  # o la tua lista esplicita
    write_missing_tags_tables(out_root, records, required_tags)


if __name__ == "__main__":
    main()
