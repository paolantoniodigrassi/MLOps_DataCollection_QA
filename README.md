# Pipeline Unificata: Estrazione DICOM + Quality Assurance

Pipeline integrata che combina l'estrazione DICOM dal PACS (con anonimizzazione) e la Quality Assurance automatica, gestita tramite Nextflow e interfaccia a linea di comando.

## Prerequisiti

- Docker e Docker Compose
- Accesso al server PACS (DCM4CHEE) se si usa la modalità CSV
- Credenziali AWS KMS (solo per anonimizzazione `partial`)

## Installazione

1. Clona il progetto e accedi alla cartella:

```bash
cd unified_pipeline
```

2. Copia e configura il file `.env`:

```bash
cp .env.example .env
# Modifica .env con i tuoi valori (PACS_BASE_URL, credenziali AWS, ecc.)
```

3. Build del container Docker:

```bash
docker-compose build
```

## Uso

### Esecuzione interattiva

```bash
docker-compose run --rm pipeline
```

Lo script interattivo chiederà:
1. **Modalità**: estrazione da CSV + QA oppure QA su file locali
2. Se CSV: percorso del file, tipo di anonimizzazione
3. Directory di output


### Senza Docker

Se hai Python 3.11+ e Nextflow installati:

```bash
pip install -r requirements.txt
bash run_pipeline.sh
```

## Modalità di Anonimizzazione

| Modalità | Parametro | Descrizione | Richiede AWS |
|---|---|---|---|
| Standard | `clear` | Nessuna anonimizzazione | No |
| Anonimizzata | `irreversible` | Hash SHA-256 irreversibile | No |
| Pseudonimizzata | `partial` | Cifratura reversibile con AWS KMS | Sì |

## Formato del CSV

Il file CSV deve avere una colonna `PatientName` (case-insensitive):

```csv
PatientName
Mario Rossi
Laura Bianchi
```

## Struttura del Progetto

```
unified_pipeline/
├── pipeline.nf              # Pipeline Nextflow unificata
├── run_pipeline.sh          # CLI interattivo
├── Dockerfile
├── docker-compose.yaml
├── requirements.txt
├── .env.example
├── src/
│   ├── extraction/          # Logica estrazione DICOM
│   │   ├── extract_dicom.py     # Script principale estrazione
│   │   ├── extraction_config.py # Configurazione
│   │   ├── network_utils.py     # Comunicazione con PACS
│   │   ├── dicom_handler.py     # Download istanze DICOM
│   │   ├── helpers.py           # Utility per nomi pazienti
│   │   ├── crypto_utils.py      # Cifratura (AWS KMS + hash)
│   │   └── decryption.py        # Decifratura
│   ├── config.py            # Configurazione QA
│   ├── inout/
│   │   ├── parsing/
│   │   │   ├── file_scanner.py  # Scansione file DICOM
│   │   │   └── dicom_reader.py  # Lettura header DICOM
│   │   ├── report.py            # Report CSV
│   │   └── report_qc.py         # Report QC
│   ├── processing/
│   │   ├── operators.py         # Operatori matematici
│   │   ├── series_grouper.py    # Raggruppamento serie
│   │   └── volume_builder.py    # Costruzione volumi 3D
│   └── qc/
│       ├── qc_runner.py         # Esecuzione QC
│       └── rules.py             # Regole di controllo qualità
├── data/                    # Directory per file DICOM locali
├── input_csv/               # Directory per file CSV
├── output/                  # Output della pipeline
└── extractions/             # Directory per le estrazioni dal PACS
```

## Output della Pipeline

La pipeline produce nella directory di output una sottocartella per ogni esecuzione, contenente:

| File | Descrizione |
|---|---|
| `metadata.csv` | Metadati di tutti i file DICOM |
| `series_report.csv` | Report per serie |
| `volumes_report.csv` | Report sui volumi ricostruiti |
| `read_errors.csv` | Errori di lettura DICOM |
| `missing_tags_by_file.csv` | Tag mancanti per file |
| `missing_tags_by_series.csv` | Tag mancanti per serie |
| `qc_flags_by_image.csv` | Flag QC per immagine |
| `qc_flags_by_series.csv` | Flag QC per serie |
| `qc_summary.csv` | Riepilogo QC |
| `extraction_summary.txt` | Riepilogo estrazione (solo modalità CSV) |
| `pseudonym_map.csv` | Mappa pseudonimi (solo se anonimizzazione != clear) |

Inoltre verrà generata la cartella `volumes` contenente i volumi ricostruiti. 

## Configurazione PACS

L'URL del PACS si configura nel file `.env`:

```bash
# Docker sulla stessa rete di DCM4CHEE
PACS_BASE_URL=http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs

# Docker con host.docker.internal (default)
PACS_BASE_URL=http://host.docker.internal:8080/dcm4chee-arc/aets/DCM4CHEE/rs

# IP diretto del server
PACS_BASE_URL=http://192.168.1.100:8080/dcm4chee-arc/aets/DCM4CHEE/rs
```

## Note

- Se DCM4CHEE è già avviato con un docker-compose separato, modifica il campo `networks` in `docker-compose.yaml` per usare la rete esterna esistente.
- I file DICOM locali vanno messi nella cartella `data/`.
- I file CSV vanno messi nella cartella `input_csv/`.
