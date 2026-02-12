from pathlib import Path
from typing import List


def has_dicom_bytes(path: Path) -> bool:
    '''
    used for datasets that omit the .dcm extension
    DICOM files often contain b'DICM' at byte offset 128 (DICOM "magic bytes")
    '''
    try:
        with path.open("rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except Exception:
        return False
    

def is_probably_dicom(path:Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() == ".dcm":
        return True
    return has_dicom_bytes(path)


def scan_dicom_files(root: Path, ignore_ext: tuple[str, ...]) -> List[Path]:

    root = root.resolve()
    dicoms: List[Path] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in ignore_ext:
            continue
        if is_probably_dicom(p):
            dicoms.append(p)

    return sorted(dicoms)