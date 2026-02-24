'''
Ricostruisce i volumi delle serie che sono candidati validi per
la ricostruzione
'''
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path
import json
import math
import hashlib

import numpy as np
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.processing.operators import x_to_float, xyz_as_floats, six_as_floats, dot_product, slice_normal_from_iop
from src.inout.parsing.dicom_reader import read_pixel_array_from_record


PixelReaderFn = Callable [[Dict[str, Any]], np.ndarray]


def median(vals: List[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None and math.isfinite(v)]
    if not vals:
        return None
    vals.sort()
    m = len(vals) // 2
    if len(vals) % 2 == 1:
        return float(vals[m])
    return float(0.5 * (vals[m - 1] + vals[m]))


def is_series_reconstructable(sorted_records: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    issues: List[str] = []

    if len(sorted_records) < 2:
        return False, ["Series has < 2 instances (not a volume)."]

    first = sorted_records[0]

    rows0 = x_to_float(first.get("Rows"))
    cols0 = x_to_float(first.get("Columns"))
    if rows0 is None or cols0 is None:
        return False, ["Missing Rows/Columns."]
    rows_i = int(rows0)
    cols_i = int(cols0)
    if rows_i <= 0 or cols_i <= 0:
        return False, ["Invalid Rows/Columns."]

    ps0 = first.get("PixelSpacing")
    if ps0 is None or not isinstance(ps0, (list, tuple)) or len(ps0) < 2:
        return False, ["Missing PixelSpacing."]
    ps0_r = x_to_float(ps0[0])
    ps0_c = x_to_float(ps0[1])
    if ps0_r is None or ps0_c is None:
        return False, ["Invalid PixelSpacing."]

    iop0 = six_as_floats(first.get("ImageOrientationPatient"))
    if not iop0:
        return False, ["Missing ImageOrientationPatient (IOP)."]

    ipp0 = xyz_as_floats(first.get("ImagePositionPatient"))
    if ipp0 is None:
        return False, ["Missing ImagePositionPatient (IPP) in first slice."]

    tol_ps = 1e-4
    tol_iop = 1e-3

    n_ok_geo = 0
    for r in sorted_records:
        rr = x_to_float(r.get("Rows"))
        cc = x_to_float(r.get("Columns"))
        if rr is None or cc is None:
            continue
        if int(rr) != rows_i or int(cc) != cols_i:
            return False, ["Rows/Columns mismatch inside series."]

        ps = r.get("PixelSpacing")
        if ps is None or not isinstance(ps, (list, tuple)) or len(ps) < 2:
            return False, ["Some instances missing PixelSpacing."]
        pr = x_to_float(ps[0])
        pc = x_to_float(ps[1])
        if pr is None or pc is None:
            return False, ["Some instances have invalid PixelSpacing."]
        if abs(pr - ps0_r) > tol_ps or abs(pc - ps0_c) > tol_ps:
            return False, ["PixelSpacing mismatch inside series."]

        iop = six_as_floats(r.get("ImageOrientationPatient"))
        ipp = xyz_as_floats(r.get("ImagePositionPatient"))
        if iop and ipp:
            if any(abs(iop[i] - iop0[i]) > tol_iop for i in range(6)):
                return False, ["IOP mismatch inside series."]
            n_ok_geo += 1

    if n_ok_geo < max(2, int(0.8 * len(sorted_records))):
        return False, ["Too many instances missing IOP/IPP for reliable geometry."]

    return True, issues

def estimate_geometry(sorted_records: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    issues: List[str] = []
    if not sorted_records:
        return None, ["Empty series."]

    first = sorted_records[0]

    iop = six_as_floats(first.get("ImageOrientationPatient"))
    if not iop:
        return None, ["Missing IOP."]

    normal = slice_normal_from_iop(iop)
    if normal is None:
        return None, ["Cannot compute normal from IOP (cross/normalize failed)."]

    ipp0 = xyz_as_floats(first.get("ImagePositionPatient"))
    if ipp0 is None:
        return None, ["Missing IPP for origin."]

    ps = first.get("PixelSpacing")
    if ps is None or not isinstance(ps, (list, tuple)) or len(ps) < 2:
        return None, ["Missing PixelSpacing."]
    row_sp = x_to_float(ps[0])
    col_sp = x_to_float(ps[1])
    if row_sp is None or col_sp is None:
        return None, ["Invalid PixelSpacing."]

    sy = float(row_sp)
    sx = float(col_sp)

    z_coords: List[float] = []
    for r in sorted_records:
        ipp = xyz_as_floats(r.get("ImagePositionPatient"))
        if ipp is None:
            continue
        z_coords.append(float(dot_product(ipp, normal)))

    sz: Optional[float] = None
    if len(z_coords) >= 2:
        z_coords.sort()
        diffs = [abs(z_coords[i + 1] - z_coords[i]) for i in range(len(z_coords) - 1)]
        diffs = [d for d in diffs if d > 1e-6 and math.isfinite(d)]
        sz = median(diffs)

    if sz is None:
        issues.append("Cannot estimate sz from IPP; fallback to SpacingBetweenSlices or SliceThickness.")
        fallback = first.get("SpacingBetweenSlices") or first.get("SliceThickness")
        fb = x_to_float(fallback)
        if fb is not None:
            sz = float(fb)

    if sz is None:
        return None, issues + ["Missing slice spacing (sz)."]

    rows = int(x_to_float(first.get("Rows")) or 0)
    cols = int(x_to_float(first.get("Columns")) or 0)

    direction = [
        [iop[0], iop[3], normal[0]],
        [iop[1], iop[4], normal[1]],
        [iop[2], iop[5], normal[2]],
    ]

    geom = {
        "origin": [float(ipp0[0]), float(ipp0[1]), float(ipp0[2])],
        "spacing": [sx, sy, float(sz)],   
        "direction": direction,           
        "rows": rows,
        "cols": cols,
        "n_slices": len(sorted_records),
        "modality": first.get("Modality"),
        "series_description": first.get("SeriesDescription"),
        "study_uid": first.get("StudyInstanceUID"),
        "series_uid": first.get("SeriesInstanceUID"),
    }
    return geom, issues


def build_volume(sorted_records: List[Dict[str, Any]], read_pixel_array: PixelReaderFn) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]], List[str]]:
    ok, why_not = is_series_reconstructable(sorted_records)
    if not ok:
        return None, None, why_not

    issues: List[str] = []
    geom, geom_issues = estimate_geometry(sorted_records)
    issues.extend(geom_issues)
    if geom is None:
        return None, None, issues

    rows = int(geom["rows"])
    cols = int(geom["cols"])

    slices: List[np.ndarray] = []
    skipped = 0

    for r in sorted_records:
        try:
            img2d = read_pixel_array(r)
        except Exception as e:
            issues.append(f"Pixel read error for {r.get('file_path')}: {e}")
            skipped += 1
            continue

        if not isinstance(img2d, np.ndarray):
            issues.append(f"Pixel reader did not return np.ndarray for {r.get('file_path')}")
            skipped += 1
            continue

        if img2d.ndim != 2:
            issues.append(f"Pixel array not 2D for {r.get('file_path')}: ndim={img2d.ndim}")
            skipped += 1
            continue

        if img2d.shape != (rows, cols):
            issues.append(
                f"Shape mismatch for InstanceNumber={r.get('InstanceNumber')} "
                f"got={img2d.shape} expected={(rows, cols)}"
            )
            skipped += 1
            continue

        slices.append(img2d)

    if len(slices) < 2:
        return None, None, issues + [f"Not enough readable slices to build volume. skipped={skipped}"]

    volume = np.stack(slices, axis=0)  # (z, y, x)
    return volume, geom, issues

def save_volume_outputs(out_dir: Path, key: Tuple[str, str], volume: np.ndarray, geometry: Dict[str, Any], issues: List[str]) -> Tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    study_uid, series_uid = key
    safe_study = str(study_uid).replace(".", "_")
    safe_series = str(series_uid).replace(".", "_")

    h = hashlib.sha1(f"{study_uid})__{series_uid}".encode("utf-8")).hexdigest()[:10]

    vol_path = out_dir / f"vol_{safe_study[:24]}__{safe_series[:24]}__{h}.npy"
    geo_path = out_dir / f"geo_{safe_study[:24]}__{safe_series[:24]}__{h}.json"
    iss_path = out_dir / f"issues_{safe_study[:24]}__{safe_series[:24]}__{h}.txt"

    np.save(vol_path, volume)

    with geo_path.open("w", encoding="utf-8") as f:
        json.dump(geometry, f, indent=2)

    valid_issues = [line for line in issues if line.strip()]
    if valid_issues:
        with iss_path.open("w", encoding="utf-8") as f:
            for line in issues:
                if line:
                    f.write(line + "\n")

    return vol_path, geo_path, iss_path


def build_volumes_entrypoint():
    series_index_path = Path(sys.argv[1])
    volumes_dir = Path(sys.argv[2])  # riceve params.out_dir/volumes da Nextflow

    series_index_raw = json.loads(series_index_path.read_text())
    series_index = {
        tuple(k.split("||")): v
        for k, v in series_index_raw.items()
    }

    volumes_dir.mkdir(parents=True, exist_ok=True)

    volumes_rows = []
    built_ok = 0
    built_fail = 0

    for (study_uid, series_uid), info in series_index.items():
        sorted_recs = info.get("records_sorted") or []
        first_file = ""
        if sorted_recs:
            fp = sorted_recs[0].get("file_path")
            first_file = str(fp) if fp is not None else ""

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

    with open("volumes_rows.json", "w") as fp:
        json.dump(volumes_rows, fp, indent=2, default=str)

    print(f"Volumes built OK:   {built_ok}")
    print(f"Volumes built FAIL: {built_fail}")


if __name__ == "__main__":
    build_volumes_entrypoint()
