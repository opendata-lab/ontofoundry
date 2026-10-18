"""Published-version export metadata, including unavailable artifacts."""

from uuid import UUID

from ontofoundry_api.adapters.base import TranslationReport
from ontofoundry_api.domain.core import Strict


class ExportPreview(Strict):
    version_id: UUID
    adapter: str
    report: TranslationReport
    content_sha256: str | None
    filename: str
    media_type: str
    download_url: str | None


def exports_schema():
    return ExportPreview.model_json_schema()
