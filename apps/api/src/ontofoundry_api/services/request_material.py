"""Persist modeling requests as ordinary, citable text materials."""

from zoneinfo import ZoneInfo

from ontofoundry_api.db_models import MaterialRecord, utc_now
from ontofoundry_api.services.material_store import store_text_material

MIN_REQUEST_CHARACTERS = 20


def store_request_material(db, settings, workspace_id: str, content: str, mode: str) -> MaterialRecord | None:
    """The caller commits the material together with the session run claim."""
    if mode != "model" or len(content.strip()) < MIN_REQUEST_CHARACTERS:
        return None
    timestamp = utc_now().astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d-%H%M")
    return store_text_material(
        db, settings, workspace_id, f"建模需求-{timestamp}.md", content,
        origin="conversation_request",
    )
