"""
Fa controllare tutte le regole del QC, riceve i dati, chiama le regole nel
giusto ordine e raccoglie tutti i flag
"""
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import src.config as cfg
from src.qc.rules import (check_missing_tags, check_range_anomalies, check_bits_consistency, check_modality, check_duplicate_sop,
                          check_instance_numbers, check_single_slice_series, check_geometry_consistency, check_orientation_consistency)

def run_per_image_rules(record: Dict[str, Any], qc_config: Dict[str, Any], required_tags: List[str], expected_modalities: List[str]) -> List[Dict[str, Any]]:
    """
    Applica tutte le regole che lavorano su un singolo record
    """
    flags = []
    flags.extend(check_missing_tags(record, required_tags))
    flags.extend(check_range_anomalies(record, qc_config))
    flags.extend(check_bits_consistency(record))
    flags.extend(check_modality(record, expected_modalities))
    return flags


def run_per_series_rules(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Applica tutte le regole che lavorano sull'intera serie
    """
    flags = []
    flags.extend(check_duplicate_sop(records))
    flags.extend(check_instance_numbers(records))
    flags.extend(check_single_slice_series(records))
    flags.extend(check_geometry_consistency(records))
    flags.extend(check_orientation_consistency(records))
    return flags


def aggregate_by_series(flags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Raggruppa i flag per StudyInstanceUID e SeriesInstanceUID e conta le violazioni
    """
    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for f in flags:
        key = (f["StudyInstanceUID"], f["SeriesInstanceUID"])
        agg.setdefault(key, {
            "n_errors": 0,
            "n_warnings": 0,
            "n_info": 0,
            "rules_violated": set(),
        })
        if f["severity"] == "error":
            agg[key]["n_errors"] += 1
        elif f["severity"] == "warning":
            agg[key]["n_warnings"] += 1
        elif f["severity"] == "info":
            agg[key]["n_info"] += 1
        agg[key]["rules_violated"].add(f["rule"])

    result = []
    for (study, series), info in agg.items():
        result.append({
            "StudyInstanceUID": study,
            "SeriesInstanceUID": series,
            "n_errors": info["n_errors"],
            "n_warnings": info["n_warnings"],
            "n_info": info["n_info"],
            "rules_violated": " | ".join(sorted(info["rules_violated"]))
        })
    
    return result


def compute_summary(flags: List[Dict[str, Any]], n_records: int) -> List [Dict[str, Any]]:
    """
    Calcola la percentuale di violazioni per tipo di regola
    """
    files_per_rule: Dict[str, set] = {}
    counts: Dict[str, int] = {}

    for f in flags:
        rule = f["rule"]
        fp = f["file_path"]
        counts[rule] = counts.get(rule, 0) + 1
        files_per_rule.setdefault(rule, set()).add(fp)

    summary = []
    for rule, count in sorted(counts.items()):
        n_files = len(files_per_rule[rule])
        summary.append({
            "rule": rule,
            "n_violations": count,
            "n_files_affected": n_files,
            "pct_of_records": round(100.0 * n_files / n_records, 2) if n_records > 0 else 0.0,
        })

    return summary


def run_qc ( records: List[Dict[str, Any]], series_index: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Esegue il QC completo su tutti i record
    """
    qc_config = getattr(cfg, "QC_CONFIG", {})
    required_tags = cfg.essential_tags()
    expected_modalities = qc_config.get("expected_modalities", [])

    flags_by_image: List[Dict[str, Any]] = []
    # Regole per immagine
    for record in records:
        flags_by_image.extend(run_per_image_rules(record, qc_config, required_tags, expected_modalities))
    
    #Regole per serie
    flags_by_series_raw: List[Dict[str, Any]] = []
    for key, info in series_index.items():
        sorted_recs = info.get("records_sorted") or []
        if not sorted_recs:
            continue
        flags_by_series_raw.extend(run_per_series_rules(sorted_recs))

    # Aggregazione per serie
    flags_by_series = aggregate_by_series(flags_by_image)

    # Summary per tipo di regola
    qc_summary = compute_summary(flags_by_image, len(records))

    return flags_by_image, flags_by_series, qc_summary

    
def run_qc_entrypoint():
    print("[qc_runner] Reading input files...", flush=True)
    records_path = Path(sys.argv[1])
    series_index_path = Path(sys.argv[2])
    
    
    records = json.loads(records_path.read_text())
    print(f"[qc_runner] Loaded records: {len(records)}", flush=True)

    series_index_raw = json.loads(series_index_path.read_text())
    series_index = {
        tuple(k.split("||")): v
        for k, v in series_index_raw.items()
    }
    print(f"[qc_runner] Loaded series_index keys: {len(series_index_raw)}", flush=True)

    print("[qc_runner] Running QC...", flush=True)
    flags_by_image, flags_by_series, qc_summary = run_qc(records, series_index)
    print(f"[qc_runner] QC done. Flags: {len(flags_by_image)}")

    print("[qc_runner] Writing outputs...")
    with open("qc_flags_by_image.json", "w") as fp:
        json.dump(flags_by_image, fp, indent=2, default=str)

    with open("qc_flags_by_series.json", "w") as fp:
        json.dump(flags_by_series, fp, indent=2, default=str)

    with open("qc_summary.json", "w") as fp:
        json.dump(qc_summary, fp, indent=2, default=str)

    print(f"Flags by image:  {len(flags_by_image)}")
    print(f"Flags by series: {len(flags_by_series)}")
    print(f"Rules violated:  {len(qc_summary)}")


if __name__ == "__main__":
    run_qc_entrypoint()

