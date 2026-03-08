"""
Utility di crittografia per l'anonimizzazione DICOM.
Versione standalone senza dipendenze Django.
"""
from datetime import datetime, timedelta
import boto3
import secrets
import hashlib
from botocore.exceptions import ClientError

from src.extraction import extraction_config as cfg

# Client KMS lazy-initialized
_kms_client = None


def _get_kms_client():
    global _kms_client
    if _kms_client is None:
        if not cfg.AWS_REGION or not cfg.AWS_KMS_KEY_ID:
            raise RuntimeError(
                "Credenziali AWS non configurate. "
                "Per usare la modalità 'partial' è necessario configurare "
                "AWS_KMS_KEY_ID e AWS_REGION nel file .env"
            )
        _kms_client = boto3.client('kms', region_name=cfg.AWS_REGION)
    return _kms_client


def anonymize_referenced_sop_instance_uid(ds, key_id, anonymization_type):
    """
    Anonimizza tutti i campi 'Referenced SOP Instance UID' ricorsivamente.
    """
    if hasattr(ds, 'ReferencedSOPInstanceUID'):
        referenced_uid = str(ds.ReferencedSOPInstanceUID)
        if anonymization_type == 'partial':
            ds.ReferencedSOPInstanceUID = partially_encrypt_uid_with_kms(key_id, referenced_uid)
        elif anonymization_type == 'irreversible':
            ds.ReferencedSOPInstanceUID = hash_value(referenced_uid)

    for elem in ds:
        if elem.VR == 'SQ':
            for item in elem:
                anonymize_referenced_sop_instance_uid(item, key_id, anonymization_type)


def partially_encrypt_uid_with_kms(key_id, uid, clear_length=20):
    """
    Cifra parzialmente un UID lasciando in chiaro le prime clear_length cifre.
    """
    if len(uid) > clear_length:
        clear_part = uid[:clear_length]
        to_encrypt_part = uid[clear_length:]
        encrypted_part_hex = encrypt_value_with_kms(to_encrypt_part, key_id)
        if encrypted_part_hex:
            return clear_part + encrypted_part_hex
        else:
            return ""
    else:
        return ""


def partially_encrypt_institution_name_with_kms(institution_name, key_id):
    """
    Cifra parzialmente il nome dell'istituzione, lasciando le prime 3 lettere.
    """
    words = institution_name.split()
    partially_encrypted_words = []
    for word in words:
        if len(word) > 3:
            first_three_chars = word[:3]
            remaining_value = word[3:]
            encrypted_remaining = encrypt_value_with_kms(remaining_value, key_id)
            if encrypted_remaining:
                partially_encrypted_word = first_three_chars + encrypted_remaining
            else:
                partially_encrypted_word = word
        else:
            partially_encrypted_word = word
        partially_encrypted_words.append(partially_encrypted_word)
    return " ".join(partially_encrypted_words)


def anonymize_date(original_date):
    """
    Anonimizza una data sottraendo un offset di giorni.
    """
    if original_date:
        date_format = "%Y%m%d"
        date_obj = datetime.strptime(original_date, date_format)
        offset_days = cfg.ANONYMIZATION_DATE_OFFSET_DAYS
        new_date_obj = date_obj - timedelta(days=offset_days)
        return new_date_obj.strftime(date_format)
    return None


def anonymize_time(original_time):
    """
    Anonimizza un orario sottraendo un offset di minuti.
    """
    if original_time:
        try:
            time_format = "%H%M%S.%f" if '.' in original_time else "%H%M%S"
            time_obj = datetime.strptime(original_time, time_format)
            offset_minutes = cfg.ANONYMIZATION_TIME_OFFSET_MINUTES
            new_time_obj = time_obj - timedelta(minutes=offset_minutes)
            return new_time_obj.strftime("%H%M%S")
        except ValueError:
            return None
    return None


def hash_value(value):
    """
    Genera un hash SHA-256 irreversibile con salt casuale.
    """
    if value:
        salt = secrets.token_hex(8)
        return hashlib.sha256((salt + value).encode('utf-8')).hexdigest()
    return None


def encrypt_value_with_kms(value, key_id=None):
    """
    Cifra un valore usando AWS KMS.
    """
    try:
        kms_client = _get_kms_client()
        actual_key_id = key_id or cfg.AWS_KMS_KEY_ID

        if isinstance(value, str):
            plaintext = value.encode('utf-8')
        elif isinstance(value, bytes):
            plaintext = value
        else:
            plaintext = str(value).encode('utf-8')

        response = kms_client.encrypt(
            KeyId=actual_key_id,
            Plaintext=plaintext
        )
        encrypted_value = response['CiphertextBlob'].hex()
        return encrypted_value

    except ClientError as e:
        print(f"[WARN] Errore AWS KMS encrypt: {e}")
        return None
    except Exception as e:
        print(f"[WARN] Errore encrypt: {e}")
        return None
