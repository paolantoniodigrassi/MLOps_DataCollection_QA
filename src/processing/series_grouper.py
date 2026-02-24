from typing import Any, Dict, Iterable, List, Tuple
import sys
import json
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.processing.operators import x_to_float, xyz_as_floats, six_as_floats,  dot_product, slice_normal_from_iop




def group_records_by_series(records: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    '''
    Group records by StudyInstanceUID, SeriesInstanceUID
    '''
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for r in records:
        study = r.get("StudyInstanceUID")
        series = r.get("SeriesInstanceUID")
        if not study or not series:
            continue

        key = (str(study), str(series))
        groups.setdefault(key, []).append(r)
    
    return groups


def sort_series_records(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    '''
    Sort records inside one series
    '''
    issues: List[str] = []
    if not records:
        return [], "empty", ["Empty series"]
    
    iop = six_as_floats(records[0].get("ImageOrientationPatient"))
    normal = slice_normal_from_iop(iop) if iop else None

    if normal is not None:
        coords: List[Tuple[float, Dict[str, Any]]] = []
        no_ipp: List[Dict[str, Any]] = []

        for r in records:
            ipp = xyz_as_floats(r.get("ImagePositionPatient"))
            if ipp is None:
                no_ipp.append(r)
                continue
            coords.append((dot_product(ipp, normal), r))

        # Use geometric sort if there are enough IPP values
        if len(coords) >= max(2, int(0.8 * len(records))):
            coords.sort(key=lambda x: x[0])
            sorted_records = [r for _, r in coords]

            if no_ipp:
                issues.append(f"{len(no_ipp)} instances missing ImagePositionPatient, appended unsorted at end.")
                sorted_records.extend(no_ipp)

            return sorted_records, "ipp", issues
        else:
            issues.append("Too many missing ImagePositionPatient, falling back to InstanceNumber.")
        
    # Fallback: InstanceNumber
    def inst_key(r: Dict[str, Any]) -> float:
        v = x_to_float(r.get("InstanceNumber"))
        return v if v is not None else float("inf")
        
    sorted_records = sorted(records, key=inst_key)
    return sorted_records, "instance_number", issues
    

def build_series_index(records: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    groups = group_records_by_series(records)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for key, recs in groups.items():
        sorted_recs, method, issues = sort_series_records(recs)

        first = sorted_recs[0] if sorted_recs else{}
        out[key] = {
            "records_sorted": sorted_recs,
            "sort_method": method,
            "issues": issues,
            "series_description": first.get("SeriesDescription"),
            "modality": first.get("Modality"),
            "n_instances": len(recs)
        }

    return out


def group_and_sort_entrypoint():
    records_path = Path(sys.argv[1])
    records = json.loads(records_path.read_text())

    series_index = build_series_index(records)

    series_index_serializable = {
        f"{study_uid}||{series_uid}": info
        for (study_uid, series_uid), info in series_index.items()
    }

    with open("series_index.json", "w") as fp:
        json.dump(series_index_serializable, fp, indent=2, default=str)

    print(f"Indexed series: {len(series_index_serializable)}")


if __name__ == "__main__":
    group_and_sort_entrypoint()