nextflow.enable.dsl=2

// Configurazione
params.root_dir  = "/app"
params.python    = "python3"
params.out_dir   = "/app/output"

// Modalità: 'csv' oppure 'local'
params.mode      = "local"

// Parametri per la modalità CSV (estrazione dal PACS)
params.csv_file           = ""
params.anonymization_type = "clear"    // clear | partial | irreversible

// Directory dei file DICOM (usata in modalità 'local', o riempita dall'estrazione)
params.data_dir  = "/app/data"


// Estrazione DICOM dal PACS (solo modalità CSV)

process extract_dicom_from_pacs {
    publishDir params.out_dir, mode: 'copy', pattern: 'extraction_summary.txt'

    input:
    val csv_path
    val anon_type

    output:
    path 'dicom_extracted', emit: dicom_dir
    path 'extraction_summary.txt'

    script:
    """
    mkdir -p dicom_extracted
    $params.python $params.root_dir/src/extraction/extract_dicom.py $csv_path $anon_type dicom_extracted
    """
}


// Scansione file DICOM

process scan_dicom_files {
    publishDir params.out_dir, mode: 'copy'

    input:
    path data_dir

    output:
    path 'dicom_list.txt'

    script:
    """
    $params.python $params.root_dir/src/inout/parsing/file_scanner.py $data_dir
    """
}


// Lettura header DICOM 

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


// Raggruppamento serie

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


// Costruzione e salvataggio volumi 

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


// Esecuzione batteria controlli QA

process run_qc {
    publishDir params.out_dir, mode: 'copy'

    input:
    path records
    path series_index

    output:
    path 'qc_flags_by_image.json'
    path 'qc_flags_by_series.json'
    path 'qc_summary.json'

    script:
    """
    $params.python $params.root_dir/src/qc/qc_runner.py $records $series_index
    """
}


// Generazione report
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

// Generazione report QA
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


// Workflow
workflow {

    // Determina la directory DICOM in base alla modalità
    if (params.mode == 'csv') {
        // Modalità CSV: estrae prima dal PACS, poi esegui QA
        extract_dicom_from_pacs(params.csv_file, params.anonymization_type)
        data_ch = extract_dicom_from_pacs.out.dicom_dir
    } else {
        // Modalità local: usa direttamente la directory specificata
        data_ch = channel.fromPath(params.data_dir, type: 'dir')
    }

    // Pipeline QA (identica in entrambi i casi)
    scan_dicom_files(data_ch)
    read_dicom_headers(scan_dicom_files.out)
    group_and_sort_series(read_dicom_headers.out[0])
    build_volumes(group_and_sort_series.out)

    // QC in parallelo con build_volumes
    run_qc(read_dicom_headers.out[0], group_and_sort_series.out)

    // Report in parallelo dopo read_dicom_headers
    write_metadata_csv(read_dicom_headers.out[0])
    write_read_errors_csv(read_dicom_headers.out[1])
    write_missing_tags_csv(read_dicom_headers.out[0])

    // Report dopo group_and_sort_series
    write_series_report_csv(group_and_sort_series.out)

    // Report dopo build_volumes
    write_volumes_report_csv(build_volumes.out[0])

    // Report QC
    write_qc_flags_by_image(run_qc.out[0])
    write_qc_flags_by_series(run_qc.out[1])
    write_qc_summary(run_qc.out[2])
}
