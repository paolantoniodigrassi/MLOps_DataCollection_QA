'''
Definisce le regole per il QA e distingue la severity dei
diversi problemi
'''
import math
from typing import Any, Dict, List, Optional
from src.processing.operators import six_as_floats, dot_product


def make_flag(
    file_path: str,
    study_uid: str,
    series_uid: str,
    rule: str,
    severity: str,
    message: str,
    tag: Optional[str] = None
) -> Dict[str, Any]:
    return {
        "file_path": file_path,
        "StudyInstanceUID": study_uid,
        "SeriesInstanceUID": series_uid,
        "rule": rule,   # nome della regola
        "severity": severity,   # "error" | "warning" | "info"
        "message": message,
        "tag": tag or "",   # tag DICOM coinvolto
    }


def base(r: Dict[str, Any]):
    # Per non ripetere r.get("file_path") in ogni regola
    return (
        str(r.get("file_path") or ""),
        str(r.get("StudyInstanceUID") or ""),
        str(r.get("SeriesInstanceUID") or "")
    )


def check_missing_tags(record: Dict[str, Any], required_tags: List[str]) -> List[Dict[str, Any]]:
    """
    Controlla che tutti i tag essenziali siano presenti e non vuoti
    """
    fp, study, series = base(record)
    flags = []

    for tag in required_tags:
        val = record.get(tag)
        missing = (val is None or (isinstance(val, str) and val.strip() == "") or (isinstance(val, (list, tuple)) and len(val) == 0))
        if missing:
            flags.append(make_flag(
                fp,
                study,
                series,
                rule="missing_tag",
                severity="error",
                message=f"Tag '{tag}' is missing or empty.",
                tag=tag
            ))
    return flags


def check_range_anomalies(record: Dict[str, Any], qc_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Controlla che i valori numerici siano dentro range ragionevoli
    """
    fp, study, series = base(record)
    flags = []

    def check(tag: str, min_val: float, max_val: float):
        """
        Check dei range
        """
        val = record.get(tag)
        if val is None:
            return
        # Gestisce liste
        values = val if isinstance(val, (list, tuple)) else [val]
        for v in values:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return
            # Gestione di inf
            if not math.isfinite(fv):
                flags.append(make_flag(
                    fp,
                    study,
                    series,
                    rule="range_anomaly",
                    severity="error",
                    message=f"Tag'{tag}' has non-finite value: {v}.",
                    tag=tag
                ))
            elif fv < min_val or fv > max_val:
                flags.append(make_flag(
                    fp,
                    study,
                    series,
                    rule="range_anomaly",
                    severity="warning",
                    message=f"Tag '{tag}' value {fv} is outside expected range [{min_val}, {max_val}].",
                    tag=tag
                ))

    ranges = qc_config.get("ranges", {})
    for tag, (min_val, max_val) in ranges.items():
        check(tag, min_val, max_val)

    return flags    


def check_bits_consistency(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    BitsStored non può essere maggiore di BitsAllocated.
    """
    fp, study, series = base(record)
    flags = []

    allocated = record.get("BitsAllocated")
    stored = record.get("BitsStored")

    if allocated is None or stored is None:
        return flags

    try:
        a, s = int(allocated), int(stored)
    except (TypeError, ValueError):
        return flags

    if s > a:
        flags.append(make_flag(
            fp,
            study,
            series,
            rule="bits_inconsistency",
            severity="error",
            message=f"BitsStored ({s}) > BitsAllocated ({a}).",
            tag="BitsStored"
        ))

    return flags


def check_modality(record: Dict[str, Any], expected_modalities: List[str]) -> List[Dict[str, Any]]:
    """
    Controlla che la modalità sia presente e tra quelle valide.
    """
    fp, study, series = base(record)
    flags = []

    modality = record.get("Modality")
    if not modality:
        flags.append(make_flag(
            fp,
            study,
            series,
            rule="missing_modality",
            severity="error",
            message="Tag 'Modality' is missing.",
            tag="Modality"
        ))
        return flags

    if expected_modalities and modality not in expected_modalities:
        flags.append(make_flag(
            fp,
            study,
            series,
            rule="unexpected_modality",
            severity="warning",
            message=f"Modality '{modality}' not in expected {expected_modalities}.",
            tag="Modality"
        ))

    return flags


def check_duplicate_sop(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Controlla che non ci siano due file con lo stesso SOPInstanceUID nella stessa serie.
    """
    flags = []
    seen: Dict[str, str] = {}  # sop_uid -> file_path

    for r in records:
        fp, study, series = base(r)
        sop = r.get("SOPInstanceUID")
        if not sop:
            continue
        sop = str(sop)
        if sop in seen:
            flags.append(make_flag(
                fp,
                study,
                series,
                rule="duplicate_sop",
                severity="error",
                message=f"SOPInstanceUID '{sop}' duplicated. First seen in: {seen[sop]}.",
                tag="SOPInstanceUID"
            ))
        else:
            seen[sop] = fp

    return flags


def check_instance_numbers(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Controlla duplicati e buchi nella sequenza di InstanceNumber.
    """
    flags = []
    if not records:
        return flags

    fp0, study, series = base(records[0])

    numbers = []
    for r in records:
        v = r.get("InstanceNumber")
        if v is None:
            continue
        try:
            numbers.append(int(float(v)))
        except (TypeError, ValueError):
            continue

    if not numbers:
        return flags

    # Duplicati
    seen = set()
    for n in numbers:
        if n in seen:
            flags.append(make_flag(
                fp0,
                study,
                series,
                rule="duplicate_instance_number",
                severity="error",
                message=f"InstanceNumber {n} appears more than once in series.",
                tag="InstanceNumber"
            ))
        seen.add(n)

    # Buchi nella sequenza
    sorted_nums = sorted(set(numbers))

    range_size = sorted_nums[-1] - sorted_nums[0] + 1
    if range_size > 10000:
        flags.append(make_flag(
            fp0, study, series,
            rule="gap_instance_numbers",
            severity="warning",
            message=f"InstanceNumber range too large to check gaps ({sorted_nums[0]}-{sorted_nums[-1]}).",
            tag="InstanceNumber"
        ))
    else:
        expected = set(range(sorted_nums[0], sorted_nums[-1] + 1))
        missing = expected - set(sorted_nums)
        if missing:
            flags.append(make_flag(
                fp0, study, series,
                rule="gap_instance_numbers",
                severity="warning",
                message=f"Gaps in InstanceNumber sequence: missing {sorted(missing)}.",
                tag="InstanceNumber"
            ))

    return flags


def check_single_slice_series(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Se è presente uno solo slice potrebbe trattarsi di un localizer o scout
    """
    flags = []
    if len(records) != 1:
        return flags

    fp, study, series = base(records[0])
    flags.append(make_flag(
        fp,
        study,
        series,
        rule="single_slice_series",
        severity="info",
        message="Series contains only 1 instance — likely a localizer or scout.",
    ))

    return flags


def check_geometry_consistency(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Controlla che Rows, Columns e PixelSpacing siano uniformi dentro la serie.
    """
    flags = []
    if not records:
        return flags

    first = records[0]
    fp0, study, series = base(first)

    ref_rows = first.get("Rows")
    ref_cols = first.get("Columns")
    ref_ps = first.get("PixelSpacing")

    for r in records[1:]:
        fp, _, _ = base(r)

        if r.get("Rows") != ref_rows or r.get("Columns") != ref_cols:
            flags.append(make_flag(
                fp,
                study,
                series,
                rule="geometry_inconsistency",
                severity="error",
                message=(
                    f"Rows/Columns mismatch: expected ({ref_rows},{ref_cols}), "
                    f"got ({r.get('Rows')},{r.get('Columns')})."
                ),
                tag="Rows"
            ))

        ps = r.get("PixelSpacing")
        if ps is not None and ref_ps is not None:
            try:
                if any(abs(float(ps[i]) - float(ref_ps[i])) > 1e-4 for i in range(2)):
                    flags.append(make_flag(
                        fp,
                        study,series,
                        rule="geometry_inconsistency",
                        severity="error",
                        message=f"PixelSpacing mismatch: expected {ref_ps}, got {ps}.",
                        tag="PixelSpacing",
                    ))
            except (TypeError, ValueError, IndexError):
                pass

    return flags


def check_orientation_consistency(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Controlla che ImageOrientationPatient sia coerente dentro la serie e che il vettore sia ortogonale.
    """
    flags = []
    if not records:
        return flags

    fp0, study, series = base(records[0])
    tol = 1e-3

    ref_iop = six_as_floats(records[0].get("ImageOrientationPatient"))

    # Controlla ortogonalità del primo record
    if ref_iop:
        row = ref_iop[:3] # vettore direzione righe
        col = ref_iop[3:] # vettore direzione colonne
        dot = dot_product(row, col)
        if abs(dot) > tol:
            flags.append(make_flag(
                fp0,
                study,
                series,
                rule="orientation_not_orthogonal",
                severity="error",
                message=f"IOP row/col vectors are not orthogonal (dot={dot:.4f}).",
                tag="ImageOrientationPatient"
            ))

    # Controlla consistenza dentro la serie
    for r in records[1:]:
        iop = six_as_floats(r.get("ImageOrientationPatient"))
        if iop is None or ref_iop is None:
            continue
        if any(abs(iop[i] - ref_iop[i]) > tol for i in range(6)):
            fp, _, _ = base(r)
            flags.append(make_flag(
                fp,
                study,
                series,
                rule="orientation_inconsistency",
                severity="error",
                message=f"IOP mismatch inside series.",
                tag="ImageOrientationPatient"
            ))

    return flags