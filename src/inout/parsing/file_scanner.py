from pathlib import Path
from typing import List, Dict, Any
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from src.config import PARSER_CONFIG


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
    if path.name.lower().endswith("xx.dcm"):
        return False
    if path.suffix.lower() == ".dcm":
        return True
    return has_dicom_bytes(path)


def scan_dicom_files(root: Path, PARSER_CONFIG: Dict[str, Any]) -> List[Path]:

    root = root.resolve()
    dicoms: List[Path] = []
    ignore_ext = PARSER_CONFIG.get("ignore_extensions", ())

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in ignore_ext:
            continue
        if p.name == "DICOMDIR":
            continue
        if is_probably_dicom(p):
            dicoms.append(p)

    return sorted(dicoms)


def scan_entrypoint():
    data_dir = Path(sys.argv[1])
    dicoms = scan_dicom_files(data_dir, PARSER_CONFIG)

    with open("dicom_list.txt", "w") as f:
        for p in dicoms:
            f.write(str(p) + "\n")

    print(f"Found {len(dicoms)} DICOM files under {data_dir}")


if __name__ == "__main__":
    scan_entrypoint()
