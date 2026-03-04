'''
Scrive tutti i report necessari a mostrare i risultati dei vari
processi della pipeline
'''
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

import sys
import json
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
import src.config as cfg


def write_metadata_csv(out_root: Path, records: List[Dict[str, Any]], filename: str = "metadata.csv", verbose: bool = True) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename

    df = pd.DataFrame(records)
    df.to_csv(out_path, index=False)

    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)} cols={len(df.columns)}")

    return out_path


def write_series_report_csv(out_root: Path, series_rows: List[Dict[str, Any]], filename: str = "series_report.csv", verbose: bool = True) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename

    df = pd.DataFrame(series_rows)
    df.to_csv(out_path, index=False)

    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)} cols={len(df.columns)}")

    return out_path


def write_volumes_report_csv(out_root: Path, volumes_rows: List[Dict[str, Any]], filename: str = "volumes_report.csv", verbose: bool = True) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename

    df = pd.DataFrame(volumes_rows)
    df.to_csv(out_path, index=False)

    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(df)} cols={len(df.columns)}")

    return out_path


def is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if isinstance(v, (list, tuple)) and len(v) == 0:
        return True
    return False


def write_missing_tags_tables(out_root: Path, records: List[Dict[str, Any]], required_tags: Sequence[str], by_file_name: str = "missing_tags_by_file.csv",
                              by_series_name: str = "missing_tags_by_series.csv", verbose: bool = True) -> Tuple[Path, Path]:
    
    out_root.mkdir(parents=True, exist_ok=True)

    missing_rows: List[Dict[str, Any]] = []
    for r in records:
        fp = r.get("file_path") or r.get("FilePath") or r.get("path") or ""
        study = r.get("StudyInstanceUID")
        series = r.get("SeriesInstanceUID")

        for tag in required_tags:
            if is_missing(r.get(tag)):
                missing_rows.append(
                    {
                        "file_path": str(fp),
                        "StudyInstanceUID": study,
                        "SeriesInstanceUID": series,
                        "tag": tag,
                        "reason": "missing_or_empty",
                    }
                )

    by_file_path = out_root / by_file_name
    by_series_path = out_root / by_series_name

    df_missing = pd.DataFrame(missing_rows)

    # --- Conteggio istanze per serie (serve anche per filtrare i falsi missing) ---
    if not records:
        df_counts = pd.DataFrame(columns=["StudyInstanceUID", "SeriesInstanceUID", "n_instances"])
    else:
        df_counts = (
            pd.DataFrame(records)[["StudyInstanceUID", "SeriesInstanceUID"]]
            .dropna()
            .value_counts()
            .reset_index(name="n_instances")
        )

    # Aggiungi n_instances a ogni riga "missing"
    if not df_missing.empty:
        df_missing = df_missing.merge(
            df_counts, on=["StudyInstanceUID", "SeriesInstanceUID"], how="left"
        )

        # Se la serie ha 1 sola istanza, non ha senso pretendere IPP/IOP per QA volumetrica
        skip_tags_singleton = {"ImagePositionPatient", "ImageOrientationPatient"}
        df_missing = df_missing[~(
            (df_missing["n_instances"] == 1) &
            (df_missing["tag"].isin(skip_tags_singleton))
        )].copy()
    else:
        # crea comunque la colonna per coerenza (opzionale)
        df_missing["n_instances"] = pd.Series(dtype="int64")

    df_missing.to_csv(by_file_path, index=False)

    # Summary per series/tag
    if not df_missing.empty:
        df_missing_series = (
            df_missing.dropna(subset=["StudyInstanceUID", "SeriesInstanceUID"])
            .groupby(["StudyInstanceUID", "SeriesInstanceUID", "tag"], as_index=False)
            .size()
            .rename(columns={"size": "missing_count"})
        )

        # df_missing già contiene n_instances (per merge sopra),
        # qui serve per serie/tag; si puo prendere dal df_counts
        df_missing_series = df_missing_series.merge(
            df_counts, on=["StudyInstanceUID", "SeriesInstanceUID"], how="left"
        )

        df_missing_series.to_csv(by_series_path, index=False)
    else:
        pd.DataFrame(
            columns=[
                "StudyInstanceUID",
                "SeriesInstanceUID",
                "tag",
                "missing_count",
                "n_instances"
            ]
        ).to_csv(by_series_path, index=False)


    if verbose:
        print(f"Wrote: {by_file_path}")
        print(f"    rows={len(df_missing)}")
        print(f"Wrote: {by_series_path}")

    return by_file_path, by_series_path


def write_read_errors_csv(out_root: Path, errors: List[Dict[str, Any]], filename: str = "read_errors.csv", verbose: bool = True) -> Optional[Path]:
    if not errors:
        return None
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / filename
    pd.DataFrame(errors).to_csv(out_path, index=False)

    if verbose:
        print(f"Wrote: {out_path}")
        print(f"    rows={len(errors)}")

    return out_path


def write_metadata_entrypoint():
    records = json.loads(Path(sys.argv[1]).read_text())
    write_metadata_csv(Path("."), records)


def write_read_errors_entrypoint():
    errors = json.loads(Path(sys.argv[1]).read_text())
    write_read_errors_csv(Path("."), errors)


def write_series_report_entrypoint():
    series_index_raw = json.loads(Path(sys.argv[1]).read_text())

    series_rows = []
    for key, info in series_index_raw.items():
        study_uid, series_uid = key.split("||")
        series_rows.append({
            "StudyInstanceUID": study_uid,
            "SeriesInstanceUID": series_uid,
            "n_instances": info.get("n_instances"),
            "sort_method": info.get("sort_method"),
            "modality": info.get("modality"),
            "series_description": info.get("series_description"),
            "issues": " | ".join(info.get("issues", [])),
        })

    write_series_report_csv(Path("."), series_rows)


def write_volumes_report_entrypoint():
    volumes_rows = json.loads(Path(sys.argv[1]).read_text())
    write_volumes_report_csv(Path("."), volumes_rows)


def write_missing_tags_entrypoint():
    records = json.loads(Path(sys.argv[1]).read_text())
    required_tags = cfg.essential_tags()
    write_missing_tags_tables(Path("."), records, required_tags)


if __name__ == "__main__":
    entrypoints = {
        "metadata": write_metadata_entrypoint,
        "errors": write_read_errors_entrypoint,
        "series": write_series_report_entrypoint,
        "volumes": write_volumes_report_entrypoint,
        "missing": write_missing_tags_entrypoint,
    }

    command = sys.argv[1]
    # Shift degli argomenti per gli entrypoint
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    entrypoints[command]()