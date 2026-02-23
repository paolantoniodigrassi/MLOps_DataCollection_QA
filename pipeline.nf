nextflow.enable.dsl=2

// Configurazione
params.root_dir = "/mnt/d/QA_DICOM_Files"
params.data_dir = "/mnt/d/QA_DICOM_Files/data/Dicom_Tesi"
params.python = "/mnt/d/QA_DICOM_Files/.venv_linux/bin/python3"


// Processo per la scansione dei file DICOM
process scan_dicom_files {
    output:
    path 'dicom_list.txt'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")
from pathlib import Path
from src.inout.parsing.file_scanner import scan_dicom_files
from src.config import PARSER_CONFIG

data_dir = Path("$params.data_dir")
dicoms = scan_dicom_files(data_dir, PARSER_CONFIG)

with open("dicom_list.txt", "w") as f:
    for p in dicoms:
        f.write(str(p) + "\\n")
'
"""
}


// Processo per la lettura dei file DICOM
process read_dicom_headers {
    input:
    path dicom_list

    output:
    path 'records.json'
    path 'read_errors.json'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from typing import Any, Dict, List
import src.config as cfg
from src.inout.parsing.dicom_reader import read_dicom_header

stop_before_pixels = cfg.PARSER_CONFIG.get("stop_before_pixels", True)
force_read = cfg.PARSER_CONFIG.get("force_read", True)

tag_names = cfg.all_tags()
files = Path("$dicom_list").read_text().splitlines()
files = [f.strip() for f in files if f.strip()]

records: List[Dict[str, Any]] = []
errors: List[Dict[str, Any]] = []

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
    '
    """
}


// Processo per raggruppare e ordinare gli slice delle serie
process group_and_sort_series {
    input:
    path records

    output:
    path 'series_index.json'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.processing.series_grouper import build_series_index

records = json.loads(Path("$records").read_text())

series_index = build_series_index(records)

# Conversione delle tuple-chiave in stringhe per la serializzazione JSON
series_index_serializable = {
    f"{study_uid}||{series_uid}": info
    for (study_uid, series_uid), info in series_index.items()
}

with open("series_index.json", "w") as fp:
    json.dump(series_index_serializable, fp, indent=2, default=str)

print(f"Indexed series: {len(series_index_serializable)}")
'
    """
}


// Processo per costruire e salvare i volumi
process build_volumes {
    input:
    path series_index

    output:
    path 'volumes_rows.json'
    path 'volumes/'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.processing.volume_builder import build_volume, save_volume_outputs
from src.inout.parsing.dicom_reader import read_pixel_array_from_record

series_index_raw = json.loads(Path("$series_index").read_text())

# Ricostruzione delle tuple-chiave dal separatore ||
series_index = {
    tuple(k.split("||")): v
    for k, v in series_index_raw.items()
}

volumes_dir = Path("volumes")
volumes_dir.mkdir(exist_ok=True)

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
'
    """
}


// Processi per il report
process write_metadata_csv {
    input:
    path records

    output:
    path 'metadata.csv'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.inout.report import write_metadata_csv

records = json.loads(Path("$records").read_text())
write_metadata_csv(Path("."), records)
'
    """
}

process write_read_errors_csv {
    input:
    path read_errors

    output:
    path 'read_errors.csv', optional: true

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.inout.report import write_read_errors_csv

errors = json.loads(Path("$read_errors").read_text())
write_read_errors_csv(Path("."), errors)
'
    """
}

process write_series_report_csv {
    input:
    path series_index

    output:
    path 'series_report.csv'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.inout.report import write_series_report_csv

series_index_raw = json.loads(Path("$series_index").read_text())

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
'
    """
}

process write_volumes_report_csv {
    input:
    path volumes_rows

    output:
    path 'volumes_report.csv'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
from src.inout.report import write_volumes_report_csv

volumes_rows = json.loads(Path("$volumes_rows").read_text())
write_volumes_report_csv(Path("."), volumes_rows)
'
    """
}

process write_missing_tags_csv {
    input:
    path records

    output:
    path 'missing_tags_by_file.csv'
    path 'missing_tags_by_series.csv'

    script:
    """
    $params.python -c '
import sys
sys.path.insert(0, "$params.root_dir")

import json
from pathlib import Path
import src.config as cfg
from src.inout.report import write_missing_tags_tables

records = json.loads(Path("$records").read_text())
required_tags = cfg.essential_tags()
write_missing_tags_tables(Path("."), records, required_tags)
'
    """
}


workflow {
    scan_dicom_files()

    read_dicom_headers(scan_dicom_files.out)
    read_dicom_headers.out[0].view { f -> "Records:     $f" }
    read_dicom_headers.out[1].view { f -> "Read errors: $f" }

    group_and_sort_series(read_dicom_headers.out[0])
    group_and_sort_series.out.view { f -> "Series index: $f" }

    build_volumes(group_and_sort_series.out)
    build_volumes.out[0].view { f -> "Volumes rows: $f" }
    build_volumes.out[1].view { f -> "Volumes dir:  $f" }

    // Parallelo dopo read_dicom_headers
    write_metadata_csv(read_dicom_headers.out[0])
    write_read_errors_csv(read_dicom_headers.out[1])
    write_missing_tags_csv(read_dicom_headers.out[0])

    // Parallelo dopo group_and_sort_series
    write_series_report_csv(group_and_sort_series.out)

    // Dopo build_volumes
    write_volumes_report_csv(build_volumes.out[0]) 
}


