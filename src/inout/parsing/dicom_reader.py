'''
Legge solo l'header DICOM per una lista di tag desiderati e produce
un "record" (dict) pronto da mettere in tabella (pandas)
'''
from pathlib import Path
from typing import Any, Dict, List

import pydicom
from pydicom.errors import InvalidDicomError
from pydicom.multival import MultiValue
import numpy as np
import pydicom

import sys
import json
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
import src.config as cfg

def pydicom_to_plain_python(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple, MultiValue)):
        return list(value)
    return value


def safe_get(ds: pydicom.Dataset, name: str) -> Any:
    if not hasattr(ds, name):
        return None
    return pydicom_to_plain_python(getattr(ds, name))


def read_dicom_header(path: Path, tag_names: List[str], *, stop_before_pixels: bool = True, force_read: bool = True) -> Dict[str, Any]:
    try:
        ds = pydicom.dcmread(str(path), stop_before_pixels=stop_before_pixels, force=force_read)
    except InvalidDicomError:
        return {"record": None, "missing_tags": [], "error": "InvalidDicomError"}
    except Exception as e:
        return {"record": None, "missing_tags": [], "error": f"{type(e).__name__}: {e}"}
    
    record: Dict[str, Any] = {"file_path": str(path)}
    for t in tag_names:
        record[t] = safe_get(ds, t)


    missing = [t for t in tag_names if record.get(t) is None]
    return {"record": record, "missing_tags": missing, "error": None}

def read_pixel_array_from_record(record: Dict[str, Any]) -> np.ndarray:
    fp = record.get("file_path")
    if not fp:
        raise ValueError("Record missing 'file_path'")
    
    path = Path(str(fp))

    ds = pydicom.dcmread(str(path), stop_before_pixels=False, force=True)

    arr = ds.pixel_array

    if arr.ndim == 3:
        arr = arr[0]

    if arr.ndim != 2:
        raise ValueError(f"Expected 2D pixel array, got ndim={arr.ndim}")
    
    return np.asarray(arr)


def read_headers_entrypoint():
    dicom_list = Path(sys.argv[1])
    
    stop_before_pixels = cfg.PARSER_CONFIG.get("stop_before_pixels", True)
    force_read = cfg.PARSER_CONFIG.get("force_read", True)

    if hasattr(cfg, "all_tags"):
        tag_names = cfg.all_tags()
    else:
        tag_names = ["StudyInstanceUID", "SeriesInstanceUID",
                     "InstanceNumber", "ImagePositionPatient",
                     "ImageOrientationPatient", "Modality",
                     "PixelSpacing", "SliceThickness",
                     "Rows", "Columns", "SeriesDescription"]

    files = dicom_list.read_text().splitlines()
    files = [f.strip() for f in files if f.strip()]

    records = []
    errors = []

    for f in files:
        out = read_dicom_header(
            Path(f),
            tag_names,
            stop_before_pixels=stop_before_pixels,
            force_read=force_read,
        )
        if out.get("record") is None:
            errors.append({"file": f, "error": out.get("error")})
        else:
            records.append(out["record"])

    with open("records.json", "w") as fp:
        json.dump(records, fp, indent=2, default=str)

    with open("read_errors.json", "w") as fp:
        json.dump(errors, fp, indent=2, default=str)

    print(f"Parsed records: {len(records)}")
    print(f"Read errors:    {len(errors)}")


if __name__ == "__main__":
    read_headers_entrypoint()