from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from ontofoundry_api.domain.models import (
    AttributeDefinition,
    LinkTypeDefinition,
    Multiplicity,
    OntologyDraft,
    ValueKind,
)

from .validator import semantics_can_run, validate_schema, validate_semantics

OSSIE_VERSION = "0.2.0.dev0"
# Ossie forbids extra properties everywhere except inside ai_context, which the
# official schema declares as an open object. The business names, tags and
# required flags the workspace shows have no field of their own in the standard,
# so they ride there under our own key; every other consumer can ignore it, and
# import works without it.
EXTENSION_KEY = "ontofoundry"
EXTENSION_VERSION = "1"

VALUE_BASES = {
    ValueKind.STRING: "String",
    ValueKind.INTEGER: "Integer",
    ValueKind.DECIMAL: "Decimal",
    ValueKind.FLOAT: "Float",
    ValueKind.BOOLEAN: "Boolean",
    ValueKind.DATE: "Date",
    ValueKind.DATETIME: "DateTime",
}

OSSIE_MULTIPLICITY = {
    Multiplicity.ONE_TO_ONE: "OneToOne",
    Multiplicity.MANY_TO_ONE: "ManyToOne",
}


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_json(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def _value_concept(object_key: str, attribute_key: str) -> str:
    return f"{object_key}_{attribute_key}_value"


def link_verbalizations(
    link: LinkTypeDefinition, source_key: str, target_key: str
) -> list[str]:
    """The standard reading of a relation, used when the model stores none."""
    role_name = link.target_role_name or ("related" if source_key == target_key else None)
    target_ref = target_key + (":" + role_name if role_name else "")
    if link.multiplicity == Multiplicity.ONE_TO_MANY:
        return [
            f"{{{target_ref}}}{link.name}{{{source_key}}}",
            f"{{{source_key}}}是{{{target_ref}}}通过“{link.name}”关联的对象",
        ]
    return [
        f"{{{source_key}}}{link.name}{{{target_ref}}}",
        f"{{{target_ref}}}是{{{source_key}}}通过“{link.name}”关联的对象",
    ]


def attribute_verbalizations(
    attribute: AttributeDefinition, object_key: str, value_concept: str
) -> list[str]:
    return [f"{{{object_key}}}的{attribute.name}是{{{value_concept}}}"]


def _compile_link_relationship(
    link: LinkTypeDefinition,
    source_key: str,
    target_key: str,
) -> dict[str, Any]:
    role_name = link.target_role_name or ("related" if source_key == target_key else None)
    relationship: dict[str, Any] = {
        "name": link.technical_name,
        "description": link.description or f"{link.name}：{source_key} 到 {target_key}",
        "roles": [{"concept": target_key}],
        # Hand-written readings win; otherwise the standard one is generated.
        "verbalizes": link.verbalizes or link_verbalizations(link, source_key, target_key),
    }
    if role_name:
        relationship["roles"][0]["name"] = role_name
    multiplicity = OSSIE_MULTIPLICITY.get(link.multiplicity)
    if multiplicity:
        relationship["multiplicity"] = multiplicity
    if link.multiplicity == Multiplicity.ONE_TO_MANY:
        relationship["multiplicity"] = "ManyToOne"
    if link.requires:
        relationship["requires"] = list(link.requires)
    if link.derived_by:
        relationship["derived_by"] = list(link.derived_by)
    return relationship


def compile_ossie(
    draft: OntologyDraft,
    *,
    ontology_name: str,
    ontology_description: str,
) -> dict[str, Any]:
    """Compile the internal graph into deterministic Apache Ossie JSON."""
    objects = sorted(draft.object_types, key=lambda item: item.technical_name.casefold())
    by_id = {item.id: item for item in objects}
    links_by_source: dict[Any, list[LinkTypeDefinition]] = defaultdict(list)
    for link in draft.link_types:
        links_by_source[link.owner_type_id].append(link)

    value_components: list[dict[str, Any]] = []
    entity_components: list[dict[str, Any]] = []
    display_names: dict[str, str] = {}
    tags: dict[str, list[str]] = {}
    required_attributes: list[str] = []

    for object_type in objects:
        relationships: list[dict[str, Any]] = []
        identifiers: list[str] = []
        display_names[object_type.technical_name] = object_type.name
        if object_type.tags:
            tags[object_type.technical_name] = sorted(object_type.tags)
        # A composite identifier can pair attributes with identifying relations,
        # so a lone identifier is only OneToOne when nothing else identifies.
        identifier_count = sum(item.identifier for item in object_type.attributes) + sum(
            link.identifier for link in links_by_source[object_type.id]
        )

        for attribute in sorted(
            object_type.attributes, key=lambda item: item.technical_name.casefold()
        ):
            value_concept = VALUE_BASES[attribute.value_kind]
            if attribute.identifier:
                value_concept = _value_concept(
                    object_type.technical_name, attribute.technical_name
                )
                value_components.append(
                    {
                        "concept": value_concept,
                        "type": "ValueType",
                        "description": attribute.description
                        or f"{object_type.name}的{attribute.name}",
                        "extends": [VALUE_BASES[attribute.value_kind]],
                    }
                )
            relationship: dict[str, Any] = {
                "name": attribute.technical_name,
                "description": attribute.description or attribute.name,
                "roles": [{"concept": value_concept}],
                "verbalizes": attribute.verbalizes
                or attribute_verbalizations(
                    attribute, object_type.technical_name, value_concept
                ),
            }
            if attribute.identifier:
                relationship["multiplicity"] = (
                    "OneToOne" if identifier_count == 1 else "ManyToOne"
                )
                identifiers.append(attribute.technical_name)
            else:
                relationship["multiplicity"] = "ManyToOne"
            if attribute.requires:
                relationship["requires"] = list(attribute.requires)
            if attribute.derived_by:
                relationship["derived_by"] = list(attribute.derived_by)
            key = f"{object_type.technical_name}.{attribute.technical_name}"
            display_names[key] = attribute.name
            if attribute.required:
                required_attributes.append(key)
            relationships.append(relationship)

        for link in sorted(
            links_by_source[object_type.id],
            key=lambda item: item.technical_name.casefold(),
        ):
            target = by_id[
                link.source_type_id
                if link.multiplicity == Multiplicity.ONE_TO_MANY
                else link.target_type_id
            ]
            relationships.append(
                _compile_link_relationship(
                    link,
                    object_type.technical_name,
                    target.technical_name,
                )
            )
            if link.identifier:
                identifiers.append(link.technical_name)
            key = f"{object_type.technical_name}.{link.technical_name}"
            display_names[key] = link.name
            if link.tags:
                tags[key] = sorted(link.tags)

        component: dict[str, Any] = {
            "concept": object_type.technical_name,
            "type": "EntityType",
            "description": object_type.description or object_type.name,
        }
        if object_type.extends:
            component["extends"] = sorted(
                by_id[parent].technical_name
                for parent in object_type.extends
                if parent in by_id
            )
        if identifiers:
            component["identify_by"] = sorted(identifiers)
        if object_type.requires:
            component["requires"] = list(object_type.requires)
        if object_type.derived_by:
            component["derived_by"] = list(object_type.derived_by)
        if relationships:
            component["relationships"] = sorted(
                relationships, key=lambda item: item["name"].casefold()
            )
        entity_components.append(component)

    components = sorted(
        value_components + entity_components,
        key=lambda item: (item["type"], item["concept"].casefold()),
    )
    document: dict[str, Any] = {
        "version": OSSIE_VERSION,
        "name": ontology_name,
        "description": ontology_description,
        "ai_context": {
            "instructions": "依据已发布的业务对象、属性和关系解释企业业务语义",
            "synonyms": [ontology_description] if ontology_description else [],
            EXTENSION_KEY: {
                "version": EXTENSION_VERSION,
                "display_names": display_names,
                "tags": tags,
                "required_attributes": sorted(required_attributes),
            },
        },
        "ontology": components,
    }
    if draft.requires:
        document["requires"] = list(draft.requires)
    return document


def validate_ossie(document: dict[str, Any]) -> dict[str, Any]:
    schema_issues = validate_schema(document)
    semantic_issues = (
        validate_semantics(document)
        if not schema_issues and semantics_can_run(document)
        else []
    )
    issues = schema_issues + semantic_issues
    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    return {
        "standard": f"apache-ossie/{OSSIE_VERSION}",
        "schema_status": "passed" if not schema_issues else "failed",
        "semantic_status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "publishable": not errors,
    }
