"""Core publication validation independent of exchange formats."""

from ontofoundry_api.domain.instance_validation import include_instance_validation
from ontofoundry_api.domain.models import OntologyDraft


def validation_report(data):
    try:
        model = OntologyDraft.model_validate(data)
        return include_instance_validation(
            {
                "standard": "core-1",
                "schema_status": "passed",
                "semantic_status": "passed",
                "errors": [],
                "warnings": [],
                "publishable": True,
            },
            model,
        )
    except ValueError as exc:
        return {
            "standard": "core-1",
            "schema_status": "failed",
            "semantic_status": "failed",
            "errors": [{"message": str(exc)}],
            "warnings": [],
            "publishable": False,
        }
