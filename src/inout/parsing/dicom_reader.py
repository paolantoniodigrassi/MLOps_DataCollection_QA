from pathlib import Path
from typing import Any, Dict, List

import pydicom
from pydicom.errors import InvalidDicomError
from pydicom.multival import MultiValue
import numpy as np
import pydicom


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