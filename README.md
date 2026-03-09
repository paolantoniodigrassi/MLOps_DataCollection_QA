# MLOps_DataCollection_QA

Pipeline integrata che combina l'estrazione DICOM dal PACS (con anonimizzazione) e la Quality Assurance automatica, gestita tramite Nextflow e interfaccia a linea di comando.

## Prerequisiti

- Docker e Docker Compose
- Accesso al server PACS (DCM4CHEE) se si usa la modalità CSV
- Credenziali AWS KMS (solo per anonimizzazione `partial`)

## Installazione

1. Clona il progetto e accedi alla cartella:

```bash
cd MLOps_DataCollection_QA
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

## Utilizzo

### Esecuzione interattiva

```bash
docker-compose run --rm pipeline
```

Lo script interattivo chiederà:
1. **Modalità**: estrazione da CSV + QA oppure QA su file locali
2. Se CSV: tipo di anonimizzazione

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

e deve essere inserito nella cartella `input_csv/`.

## Struttura del Progetto

```
MLOps_DataCollection_QA/
├── pipeline.nf              # Pipeline Nextflow
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

Inoltre verrà generata la cartella `volumes` contenente i volumi ricostruiti. 

## Connessione e Estrazione dal PACS

### Connessione al PACS (DCM4CHEE)

La comunicazione con il server PACS avviene tramite il protocollo **DICOMweb** (REST API). L'URL base si configura nel file `.env` tramite la variabile `PACS_BASE_URL`:

```bash
# Docker sulla stessa rete di DCM4CHEE
PACS_BASE_URL=http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs

# Docker con host.docker.internal
PACS_BASE_URL=http://host.docker.internal:8080/dcm4chee-arc/aets/DCM4CHEE/rs

# IP diretto del server
PACS_BASE_URL=http://192.168.1.100:8080/dcm4chee-arc/aets/DCM4CHEE/rs
```

### Endpoint utilizzati

La struttura DICOM è organizzata ad albero:
```
Paziente
  └── Studio (una sessione di esame, es. "TAC del 15 marzo")
        └── Serie (un gruppo di immagini, es. "sequenza assiale con contrasto")
              └── Istanza (un singolo file DICOM, una singola immagine)
```

La gerarchia delle chiamate nel codice segue esattamente questa struttura: `process_patient()` → `process_study()` → `process_series()` → `process_instance()` → `download_instance()`. Ogni funzione chiama la successiva, scendendo di un livello fino ad arrivare al singolo file DICOM da scaricare.

La pipeline utilizza quattro endpoint della DICOMweb WADO-RS/QIDO-RS API. Tutti gli endpoint (eccetto `/patients`) utilizzano i parametri comuni `includefield=all` e `offset=0`. I parametri specifici di ciascun endpoint sono:
<br>
| Endpoint | Parametri specifici |
|----------|-----------|
| `/patients` | nessuno |
| `/studies` | `PatientID` |
| `/series` | `StudyInstanceUID` |
| `/instances` | `StudyInstanceUID`, `SeriesInstanceUID` |

Nello specifico:

- **`/patients`** — Recupera la lista di tutti i pazienti presenti nel PACS. Viene usato per cercare il `PatientID` a partire dal nome contenuto nel CSV, confrontando il campo DICOM `PatientName` (tag `0010,0010`).

  In `src/extraction/network_utils.py`, funzione `get_patient_id`:
    ```python
    response = requests.get(url)  # url = PACS_BASE_URL + /patients
    ```
    L'URL viene composto in `src/extraction/extraction_config.py`:
    ```python
  PACS_PATIENTS_URL = f"{PACS_BASE_URL}/patients"
    ```
<br>

- **`/studies`** — Dato un `PatientID`, restituisce tutti gli studi DICOM associati a quel paziente. Da ogni studio viene estratto lo `StudyInstanceUID` (tag `0020,000D`).

  In `src/extraction/network_utils.py`, funzione `get_studies`:
    ```python
  url_with_patient_id = f"{studies_url}&PatientID={patient_id}"
  response = requests.get(url_with_patient_id)
    ```
<br>

- **`/series`** — Dato uno `StudyInstanceUID`, restituisce tutte le serie contenute nello studio. Da ogni serie viene estratto il `SeriesInstanceUID` (tag `0020,000E`).

    In `src/extraction/network_utils.py`, funzione `get_series`:
    ```python
    url_with_study_uid = f"{series_url}&StudyInstanceUID={study_uid}"
    response = requests.get(url_with_study_uid)
    ```
<br>

- **`/instances`** — Dati `StudyInstanceUID` e `SeriesInstanceUID`, restituisce tutte le istanze (immagini) della serie. Da ogni istanza viene estratto il `SOPInstanceUID` (tag `0008,0018`).

    In `src/extraction/network_utils.py`, funzione `get_instances`:
    ```python
    url_with_uids = f"{instances_url}&StudyInstanceUID={study_uid}&SeriesInstanceUID={series_uid}"
    response = requests.get(url_with_uids)
    ```


### Download delle istanze DICOM

Il download di ogni singolo file DICOM avviene tramite una richiesta HTTP GET all'endpoint WADO-RS. In `src/extraction/dicom_handler.py`, funzione `download_instance`:
    
```python
instance_url = (
    f"{cfg.PACS_BASE_URL}/studies/{study_uid}"
    f"/series/{series_uid}"
    f"/instances/{sop_instance_uid}"
)
response = requests.get(instance_url)
```

La risposta è in formato `multipart/related` con content type `application/dicom`. Il file DICOM viene estratto dalla risposta multipart e salvato su disco all'interno della cartella `extractions/`, nella directory del progetto. Per ogni esecuzione che prevede l'estrazione dal PACS, viene creata una sottocartella `Extraction_(data)_(ora)_(modalità)` contenente i file DICOM e, per estrazioni non `clear`, un file `pseudonym_map.csv` con la mappatura tra nomi reali e pseudonimi.

### Flusso completo di estrazione

Il processo segue la gerarchia DICOM: per ogni paziente nel CSV, lo script cerca il `PatientID` sul PACS, poi scende nella struttura paziente → studi → serie → istanze, scaricando ogni istanza e applicando l'anonimizzazione richiesta (`clear`, `irreversible` o `partial`). I file vengono salvati in una struttura di cartelle che rispecchia la gerarchia DICOM: una cartella per paziente, una sottocartella per studio, una sottocartella per serie.

## Note

- Se DCM4CHEE è già avviato con un docker-compose separato, modifica il campo `networks` in `docker-compose.yaml` per usare la rete esterna esistente.
- I file DICOM locali vanno messi nella cartella `data/`.

