nextflow.enable.dsl=2

// Configurazione
params.root_dir = "/mnt/d/QA_DICOM_Files"
params.data_dir = "/mnt/d/QA_DICOM_Files/data/Dicom_Tesi"
params.python = "/mnt/d/QA_DICOM_Files/.venv_linux/bin/python3"
params.out_dir = "/mnt/d/QA_DICOM_Files/data/out"


// Processo per la scansione dei file DICOM
process scan_dicom_files {
    publishDir params.out_dir, mode: 'copy'

    output:
    path 'dicom_list.txt'

    script:
    """
    $params.python $params.root_dir/src/inout/parsing/file_scanner.py $params.data_dir
    """
}


// Processo per la lettura dei file DICOM
process read_dicom_headers {
    publishDir params.out_dir, mode: 'copy'

    input:
    path dicom_list

    output:
    path 'records.json'
    path 'read_errors.json'

    script:
    """
    $params.python $params.root_dir/src/inout/parsing/dicom_reader.py $dicom_list
    """
}


// Processo per raggruppare e ordinare gli slice delle serie
process group_and_sort_series {
    publishDir params.out_dir, mode: 'copy'

    input:
    path records

    output:
    path 'series_index.json'

    script:
    """
    $params.python $params.root_dir/src/processing/series_grouper.py $records
    """
}


// Processo per costruire e salvare i volumi
process build_volumes {
    publishDir params.out_dir, mode: 'copy', pattern: 'volumes_rows.json'

    input:
    path series_index

    output:
    path 'volumes_rows.json'

    script:
    """
    $params.python $params.root_dir/src/processing/volume_builder.py $series_index ${params.out_dir}/volumes
    """
}


// Processi per il report
process write_metadata_csv {
    publishDir params.out_dir, mode: 'copy'

    input:
    path records

    output:
    path 'metadata.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report.py metadata $records
    """
}

process write_read_errors_csv {
    publishDir params.out_dir, mode: 'copy'

    input:
    path read_errors

    output:
    path 'read_errors.csv', optional: true

    script:
    """
    $params.python $params.root_dir/src/inout/report.py errors $read_errors
    """
}

process write_series_report_csv {
    publishDir params.out_dir, mode: 'copy'

    input:
    path series_index

    output:
    path 'series_report.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report.py series $series_index
    """
}

process write_volumes_report_csv {
    publishDir params.out_dir, mode: 'copy'

    input:
    path volumes_rows

    output:
    path 'volumes_report.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report.py volumes $volumes_rows
    """
}

process write_missing_tags_csv {
    publishDir params.out_dir, mode: 'copy'

    input:
    path records

    output:
    path 'missing_tags_by_file.csv'
    path 'missing_tags_by_series.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report.py missing $records
    """
}


workflow {
    scan_dicom_files()
    read_dicom_headers(scan_dicom_files.out)
    group_and_sort_series(read_dicom_headers.out[0])
    build_volumes(group_and_sort_series.out)

    // Parallelo dopo read_dicom_headers
    write_metadata_csv(read_dicom_headers.out[0])
    write_read_errors_csv(read_dicom_headers.out[1])
    write_missing_tags_csv(read_dicom_headers.out[0])

    // Parallelo dopo group_and_sort_series
    write_series_report_csv(group_and_sort_series.out)

    // Dopo build_volumes
    write_volumes_report_csv(build_volumes.out[0]) 
}


