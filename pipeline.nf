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


// Processo per eseguire la batteria di controlli per QA
process run_qc {
    publishDir params.out_dir, mode: 'copy'

    input:
    path records
    path series_index
    //path volumes_rows  // aggiunto solo per creare la dipendenza

    output:
    path 'qc_flags_by_image.json'
    path 'qc_flags_by_series.json'
    path 'qc_summary.json'

    script:
    """
    $params.python $params.root_dir/src/qc/qc_runner.py $records $series_index
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


// Processi per il report QA
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


process write_qc_flags_by_image {
    publishDir params.out_dir, mode: 'copy'

    input:
    path qc_flags_by_image

    output:
    path 'qc_flags_by_image.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report_qc.py by_image $qc_flags_by_image
    """
}

process write_qc_flags_by_series {
    publishDir params.out_dir, mode: 'copy'

    input:
    path qc_flags_by_series

    output:
    path 'qc_flags_by_series.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report_qc.py by_series $qc_flags_by_series
    """
}

process write_qc_summary {
    publishDir params.out_dir, mode: 'copy'

    input:
    path qc_summary

    output:
    path 'qc_summary.csv'

    script:
    """
    $params.python $params.root_dir/src/inout/report_qc.py summary $qc_summary
    """
}


workflow {
    scan_dicom_files()
    read_dicom_headers(scan_dicom_files.out)
    group_and_sort_series(read_dicom_headers.out[0])
    build_volumes(group_and_sort_series.out)

    // QC in parallelo con build_volumes
    run_qc(read_dicom_headers.out[0], group_and_sort_series.out)

    // Parallelo dopo read_dicom_headers
    write_metadata_csv(read_dicom_headers.out[0])
    write_read_errors_csv(read_dicom_headers.out[1])
    write_missing_tags_csv(read_dicom_headers.out[0])

    // Parallelo dopo group_and_sort_series
    write_series_report_csv(group_and_sort_series.out)

    // Dopo build_volumes
    write_volumes_report_csv(build_volumes.out[0]) 

    // Parallelo dopo run_qc
    write_qc_flags_by_image(run_qc.out[0])
    write_qc_flags_by_series(run_qc.out[1])
    write_qc_summary(run_qc.out[2])
}


