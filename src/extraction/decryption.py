"""
Utility di decifratura per DICOM anonimizzati.
Versione standalone senza dipendenze Django.
"""
import base64
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError

from src.extraction import extraction_config as cfg

# Client KMS lazy-initialized
_kms_client = None


def _get_kms_client():
    global _kms_client
    if _kms_client is None:
        _kms_client = boto3.client('kms', region_name=cfg.AWS_REGION)
    return _kms_client


def decrypt_value_with_kms(encrypted_value):
    """Decifra un valore cifrato usando AWS KMS."""
    try:
        kms_client = _get_kms_client()
        ciphertext_blob = bytes.fromhex(encrypted_value)
        response = kms_client.decrypt(CiphertextBlob=ciphertext_blob)
        return response['Plaintext'].decode('utf-8')
    except (ClientError, Exception) as e:
        return None


def decrypt_with_offset(camouflaged_value, offset, value_type):
    """Ripristina un valore camuffato (data o orario) aggiungendo un offset."""
    if camouflaged_value:
        try:
            if value_type == "date":
                date_format = "%Y%m%d"
                value_obj = datetime.strptime(camouflaged_value, date_format)
                original_value_obj = value_obj + timedelta(days=offset)
                return original_value_obj.strftime(date_format)
            elif value_type == "time":
                time_format = "%H%M%S"
                value_obj = datetime.strptime(camouflaged_value, time_format)
                original_value_obj = value_obj + timedelta(minutes=offset)
                return original_value_obj.strftime(time_format)
        except Exception:
            return None
    return None


def decrypt_person_name(encrypted_patient_name_hex):
    """Decifra il nome di un paziente cifrato usando AWS KMS."""
    try:
        if not isinstance(encrypted_patient_name_hex, str):
            encrypted_patient_name_hex = str(encrypted_patient_name_hex)
        encrypted_patient_name_bytes = bytes.fromhex(encrypted_patient_name_hex)
        kms_client = _get_kms_client()
        response = kms_client.decrypt(CiphertextBlob=encrypted_patient_name_bytes)
        return response['Plaintext'].decode('utf-8')
    except Exception:
        return None


def decrypt_base64_value(encrypted_value_base64):
    """Decifra un valore cifrato in formato base64 usando AWS KMS."""
    if not encrypted_value_base64:
        return ""
    try:
        encrypted_value_bytes = base64.b64decode(encrypted_value_base64)
        kms_client = _get_kms_client()
        response = kms_client.decrypt(CiphertextBlob=encrypted_value_bytes)
        return response['Plaintext'].decode('utf-8')
    except Exception:
        return ""


def partially_decrypt_uid(encrypted_uid_hex, clear_length=20):
    """Decifra parzialmente un UID cifrato."""
    if len(encrypted_uid_hex) > clear_length:
        clear_part = encrypted_uid_hex[:clear_length]
        encrypted_part_hex = encrypted_uid_hex[clear_length:]
        decrypted_part = decrypt_value_with_kms(encrypted_part_hex)
        if decrypted_part is not None:
            return clear_part + decrypted_part
        else:
            return None
    else:
        return encrypted_uid_hex


def decrypt_institution_name(encrypted_institution_name):
    """Decifra parzialmente il nome di un'istituzione."""
    if encrypted_institution_name:
        try:
            words = encrypted_institution_name.split()
            partially_decrypted_words = []
            for word in words:
                if len(word) > 3:
                    first_three_chars = word[:3]
                    encrypted_remaining_hex = word[3:]
                    decrypted_remaining = decrypt_value_with_kms(encrypted_remaining_hex)
                    if decrypted_remaining is not None:
                        partially_decrypted_word = first_three_chars + decrypted_remaining
                    else:
                        return ""
                else:
                    partially_decrypted_word = word
                partially_decrypted_words.append(partially_decrypted_word)
            return " ".join(partially_decrypted_words)
        except Exception:
            return ""
    return ""


def decrypt_fields(anonymized_ds, patient_id_mapping):
    """
    Decifra i campi di un dataset DICOM anonimizzato.
    """
    decrypted_values = {}

    # Decifratura del PatientID tramite mappatura in memoria
    if hasattr(anonymized_ds, 'PatientID') and anonymized_ds.PatientID:
        pseudonymized_id = anonymized_ds.PatientID
        original_patient_id = patient_id_mapping.get(pseudonymized_id)
        if original_patient_id:
            decrypted_values['PatientID'] = original_patient_id
        else:
            decrypted_values['PatientID'] = pseudonymized_id

    # Campi da decifrare direttamente
    fields_to_decrypt = [
        ('PatientName', decrypt_person_name),
        ('SOPInstanceUID', partially_decrypt_uid),
        ('MediaStorageSOPInstanceUID', partially_decrypt_uid),
        ('StudyInstanceUID', partially_decrypt_uid),
        ('SeriesInstanceUID', partially_decrypt_uid),
        ('StudyID', decrypt_value_with_kms),
        ('InstitutionName', decrypt_institution_name),
        ('InstitutionAddress', decrypt_value_with_kms),
        ('ReferringPhysicianName', decrypt_person_name),
        ('IssuerOfPatientID', decrypt_value_with_kms),
        ('OtherPatientIDs', decrypt_value_with_kms),
        ('PatientAddress', decrypt_value_with_kms),
        ('PatientComments', decrypt_value_with_kms),
        ('DeviceSerialNumber', decrypt_value_with_kms),
        ('AccessionNumber', decrypt_value_with_kms),
        ('AdmissionID', decrypt_value_with_kms),
        ('ImageComments', decrypt_value_with_kms),
        ('StudyDate', decrypt_with_offset),
        ('SeriesDate', decrypt_with_offset),
        ('AcquisitionDate', decrypt_with_offset),
        ('ContentDate', decrypt_with_offset),
        ('InstanceCreationDate', decrypt_with_offset),
        ('StudyTime', decrypt_with_offset),
        ('SeriesTime', decrypt_with_offset),
        ('AcquisitionTime', decrypt_with_offset),
        ('ContentTime', decrypt_with_offset),
        ('InstanceCreationTime', decrypt_with_offset),
    ]

    date_fields = {'StudyDate', 'SeriesDate', 'AcquisitionDate', 'ContentDate', 'InstanceCreationDate'}
    time_fields = {'StudyTime', 'SeriesTime', 'AcquisitionTime', 'ContentTime', 'InstanceCreationTime'}

    for field_name, decrypt_func in fields_to_decrypt:
        if hasattr(anonymized_ds, field_name) and getattr(anonymized_ds, field_name):
            if field_name in date_fields:
                decrypted_values[field_name] = decrypt_func(
                    getattr(anonymized_ds, field_name),
                    cfg.ANONYMIZATION_DATE_OFFSET_DAYS,
                    "date"
                )
            elif field_name in time_fields:
                decrypted_values[field_name] = decrypt_func(
                    getattr(anonymized_ds, field_name),
                    cfg.ANONYMIZATION_TIME_OFFSET_MINUTES,
                    "time"
                )
            else:
                decrypted_values[field_name] = decrypt_func(getattr(anonymized_ds, field_name))

    return decrypted_values
