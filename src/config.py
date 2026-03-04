'''
Definisce quali tag DICOM estrarre e alcune opzioni per la lettura/scansione
'''
from typing import List

CORE_TAGS: List[str] = [
    "Modality",
    "ImageOrientationPatient",
    "PixelSpacing",
    "SliceThickness",
    "Rows",
    "Columns",
    "SeriesDescription"
]

ID_TAGS: List[str] = [
    "PatientID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "InstanceNumber",
    "SeriesNumber",
    "ProtocolName",
    "StudyDescription",
    "Manufacturer",
    "ManufacturerModelName"
]

GEOMETRY_TAGS: List[str] = [
    "ImagePositionPatient",
    "SpacingBetweenSlices"
]

PARSER_CONFIG = {
    "stop_before_pixels": True,
    "force_read": True, # pydicom: try reading even if preamble is missing
    "ignore_extensions": (".jpg", ".jpeg", ".png", ".txt", ".csv", ".pdf", ".json")
}

ESSENTIAL_TAGS = [
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "PixelSpacing",
    "Rows",
    "Columns",
]

QC_CONFIG = {
    "ranges": {
        "SliceThickness": (0.1, 20.0),
        "PixelSpacing":   (0.01, 10.0),
        "Rows":           (16, 4096),
        "Columns":        (16, 4096),
        "BitsAllocated":  (8, 32),
        "BitsStored":     (8, 32),
    },
    "expected_modalities": ["CT", "MR", "PT", "NM", "US"],
    "orientation_tolerance": 1e-3
}

def essential_tags() -> List[str]:
    return ESSENTIAL_TAGS

def all_tags() -> List[str]:
    # returns a list with every tag for QA
    return ID_TAGS + CORE_TAGS + GEOMETRY_TAGS
