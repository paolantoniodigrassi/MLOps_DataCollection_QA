"""
Utility per la comunicazione con il server PACS (DCM4CHEE).
"""
import requests
from src.extraction.helpers import format_patient_name


def get_patient_id(patient_name, url):
    """
    Ottiene l'ID del paziente corrispondente al nome fornito.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[WARN] Errore nella richiesta al PACS: {e}")
        return None

    for record in data:
        if "00100010" in record and "Value" in record["00100010"]:
            record_patient_name = record["00100010"]["Value"][0]["Alphabetic"]
            if format_patient_name(record_patient_name).lower() == format_patient_name(patient_name).lower():
                return record["00100020"]["Value"][0]
    return None


def get_studies(patient_id, studies_url):
    """
    Recupera gli studi DICOM associati a un dato ID paziente.
    """
    url_with_patient_id = f"{studies_url}&PatientID={patient_id}"
    try:
        response = requests.get(url_with_patient_id)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[WARN] Errore nel recupero degli studi: {e}")
        return []


def get_series(study_uid, series_url):
    """
    Recupera le serie DICOM associate a uno specifico UID di studio.
    """
    url_with_study_uid = f"{series_url}&StudyInstanceUID={study_uid}"
    try:
        response = requests.get(url_with_study_uid)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[WARN] Errore nel recupero delle serie: {e}")
        return []


def get_instances(study_uid, series_uid, instances_url):
    """
    Recupera le istanze DICOM associate a una specifica serie e studio.
    """
    url_with_uids = f"{instances_url}&StudyInstanceUID={study_uid}&SeriesInstanceUID={series_uid}"
    try:
        response = requests.get(url_with_uids)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[WARN] Errore nel recupero delle istanze: {e}")
        return []


def check_patient_id(patient_name, url):
    """
    Verifica se un paziente esiste nel sistema PACS.
    """
    patient_id = get_patient_id(patient_name, url)
    return patient_id is not None
