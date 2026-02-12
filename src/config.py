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

OPTIONAL_DWI_TAGS: List[str] = [
    "DiffusionBValue",
    "DiffusionGradientOrientation"
]

PARSER_CONFIG = {
    "stop_before_pixels": True,
    "force_read": True, # pydicom: try reading even if preamble is missing
    "ignore_extensions": (".jpg", ".jpeg", ".png", ".txt", ".csv", ".pdf", ".json")
}



def all_tags() -> List[str]:
    # returns a list with every tag for QA
    return ID_TAGS + CORE_TAGS + GEOMETRY_TAGS + OPTIONAL_DWI_TAGS