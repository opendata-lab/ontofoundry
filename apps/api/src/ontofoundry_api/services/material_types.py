"""File types accepted as modeling materials.

Every material goes through the same UTF-8 text pipeline: chunked by line for
evidence locators and handed to the agent under its original name. Any plain
text format works, so the list only names the ones worth offering.
"""

from pathlib import Path

MATERIAL_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".csv": "text/csv",
}


def is_material_name(name: str) -> bool:
    return Path(name).suffix.lower() in MATERIAL_MEDIA_TYPES


def material_media_type(name: str) -> str:
    return MATERIAL_MEDIA_TYPES.get(Path(name).suffix.lower(), "text/plain")
