from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from ontofoundry_api.domain.models import (
    LinkTypeDefinition,
    Multiplicity,
    OntologyDraft,
    PropertyDefinition,
    RuleKind,
    ValueKind,
)

from .mappings import compile_mappings
from .validator import semantics_can_run, validate_schema, validate_semantics

OSSIE_VERSION = "0.2.0.dev0"
# Ossie forbids extra properties everywhere except inside ai_context, which the
# official schema declares as an open object. The business names, tags and
# required flags the workspace shows have no field of their own in the standard,
# so they ride there under our own key; every other consumer can ignore it, and
# import works without it.
EXTENSION_KEY = "ontofoundry"
# v3 adds stable rule identities and action definitions (`rules`, `actions`).
EXTENSION_VERSION = "3"

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
    attribute: PropertyDefinition, object_key: str, value_concept: str
) -> list[str]:
    value_role = value_concept + (
        f":{attribute.target_role_name}" if attribute.target_role_name else ""
    )
    return [f"{{{object_key}}}的{attribute.name}是{{{value_role}}}"]


PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_:]+)\}")


def _resolve_readings(
    readings: list[str] | None,
    expected_placeholders: set[str],
    fallback: list[str],
    *,
    aliases: dict[str, str] | None = None,
) -> list[str]:
    """Sanitize and validate readings against expected role placeholders.

    Resolves case differences and common type aliases (e.g. {Integer} for an
    identifier value concept), and falls back to deterministic standard readings
    if any reading refers to unknown roles.
    """
    if not readings:
        return fallback
    alias_map = {p.casefold(): p for p in expected_placeholders}
    for p in expected_placeholders:
        if ":" in p:
            alias_map[p.split(":")[0].casefold()] = p
    if aliases:
        for k, v in aliases.items():
            alias_map[k.casefold()] = v

    cleaned: list[str] = []
    for reading in readings:
        if not isinstance(reading, str) or not reading.strip():
            continue

        def repl(match: re.Match) -> str:
            token = match.group(1)
            if token in expected_placeholders:
                return f"{{{token}}}"
            token_lower = token.casefold()
            if token_lower in alias_map:
                return f"{{{alias_map[token_lower]}}}"
            return match.group(0)

        rewritten = PLACEHOLDER_RE.sub(repl, reading)
        found = set(PLACEHOLDER_RE.findall(rewritten))
        if found and found <= expected_placeholders:
            cleaned.append(rewritten)

    return cleaned if cleaned else fallback


def _compile_link_relationship(
    link: LinkTypeDefinition,
    source_key: str,
    target_key: str,
    draft: OntologyDraft,
) -> dict[str, Any]:
    role_name = link.target_role_name or ("related" if source_key == target_key else None)
    target_ref = target_key + (":" + role_name if role_name else "")
    expected = {source_key, target_ref}
    fallback = link_verbalizations(link, source_key, target_key)
    verbalizes = _resolve_readings(
        link.verbalizes,
        expected,
        fallback,
        aliases={target_key: target_ref},
    )
    relationship: dict[str, Any] = {
        "name": link.technical_name,
        **({"description": link.description} if link.description else {}),
        "roles": [{"concept": target_key}],
        "verbalizes": verbalizes,
    }
    if role_name:
        relationship["roles"][0]["name"] = role_name
    multiplicity = OSSIE_MULTIPLICITY.get(link.multiplicity)
    if multiplicity:
        relationship["multiplicity"] = multiplicity
    if link.multiplicity == Multiplicity.ONE_TO_MANY:
        relationship["multiplicity"] = "ManyToOne"
    _attach_rules(relationship, draft, link.id)
    return relationship


def _attach_rules(target: dict[str, Any], draft: OntologyDraft, owner_id) -> None:
    """Project an element's Rule elements onto Ossie `requires`/`derived_by`."""
    requires = draft.expressions_of(owner_id, RuleKind.CONSTRAINT)
    derived = draft.expressions_of(owner_id, RuleKind.DERIVATION)
    if requires:
        target["requires"] = requires
    if derived:
        target["derived_by"] = derived


def _rule_entries(draft: OntologyDraft, owner_id) -> list[dict[str, Any]]:
    return [
        {
            "id": str(rule.id),
            "name": rule.name,
            "technical_name": rule.technical_name,
            **({"description": rule.description} if rule.description else {}),
            "rule_kind": rule.rule_kind.value,
            "expression": rule.expression,
        }
        for rule in draft.rules_of(owner_id)
    ]


def _compile_actions(draft: OntologyDraft) -> list[dict[str, Any]]:
    """Action definitions for the extension, referencing concepts by name.

    Ossie has no action construct. Names rather than ids keep the extension
    readable by the importer, which derives ids from concept names.
    """
    types = draft.type_by_id()
    props = {p.id: p for p in draft.properties}
    links = {link.id: link for link in draft.link_types}

    def property_key(prop_id) -> str:
        prop = props[prop_id]
        return f"{types[prop.owner_type_id].technical_name}.{prop.technical_name}"

    def link_key(link_id) -> str:
        link = links[link_id]
        return f"{types[link.owner_type_id].technical_name}.{link.technical_name}"

    rules = {r.id: r for r in draft.rules}
    result = []
    for action in sorted(draft.actions, key=lambda a: a.technical_name.casefold()):
        result.append(
            {
                "id": str(action.id),
                "name": action.name,
                "technical_name": action.technical_name,
                **({"description": action.description} if action.description else {}),
                "input_type": types[action.input_type_id].technical_name,
                "parameters": [
                    p.model_dump(mode="json") for p in action.parameters
                ],
                "preconditions": [
                    rules[rule_id].technical_name for rule_id in action.precondition_rule_ids
                ],
                "effects": [
                    {
                        "id": str(effect.id),
                        "kind": effect.kind.value,
                        **(
                            {"property": property_key(effect.property_id)}
                            if effect.property_id
                            else {}
                        ),
                        **({"link": link_key(effect.link_type_id)} if effect.link_type_id else {}),
                        **({"expression": effect.expression} if effect.expression else {}),
                    }
                    for effect in action.effects
                ],
                "rules": _rule_entries(draft, action.id),
            }
        )
    return result


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
    rule_ids: dict[str, list[dict[str, Any]]] = {}

    def remember_rules(key: str, owner_id) -> None:
        entries = _rule_entries(draft, owner_id)
        if entries:
            rule_ids[key] = entries

    for object_type in objects:
        relationships: list[dict[str, Any]] = []
        identifiers: list[str] = []
        display_names[object_type.technical_name] = object_type.name
        if object_type.tags:
            tags[object_type.technical_name] = sorted(object_type.tags)
        # A composite identifier can pair attributes with identifying relations,
        # so a lone identifier is only OneToOne when nothing else identifies.
        own_properties = draft.properties_of(object_type.id)
        identifier_count = sum(item.identifier for item in own_properties) + sum(
            link.identifier for link in links_by_source[object_type.id]
        )
        remember_rules(object_type.technical_name, object_type.id)

        for attribute in sorted(own_properties, key=lambda item: item.technical_name.casefold()):
            # A stored concept name wins; otherwise identifiers get a generated
            # value concept and plain attributes point at the built-in type.
            value_concept = attribute.value_concept or (
                _value_concept(object_type.technical_name, attribute.technical_name)
                if attribute.identifier
                else VALUE_BASES[attribute.value_kind]
            )
            if value_concept not in VALUE_BASES.values() and value_concept not in {
                item["concept"] for item in value_components
            }:
                value_components.append(
                    {
                        "concept": value_concept,
                        "type": "ValueType",
                        **(
                            {"description": attribute.description}
                            if attribute.description
                            else {}
                        ),
                        "extends": [VALUE_BASES[attribute.value_kind]],
                    }
                )
            value_role = value_concept + (
                f":{attribute.target_role_name}" if attribute.target_role_name else ""
            )
            expected = {object_type.technical_name, value_role}
            fallback = attribute_verbalizations(
                attribute, object_type.technical_name, value_concept
            )
            aliases = {}
            if attribute.identifier:
                base_name = VALUE_BASES.get(attribute.value_kind)
                if base_name:
                    aliases[base_name] = value_role
            verbalizes = _resolve_readings(
                attribute.verbalizes,
                expected,
                fallback,
                aliases=aliases,
            )
            relationship: dict[str, Any] = {
                "name": attribute.technical_name,
                **({"description": attribute.description} if attribute.description else {}),
                "roles": [
                    {
                        "concept": value_concept,
                        **(
                            {"name": attribute.target_role_name}
                            if attribute.target_role_name
                            else {}
                        ),
                    }
                ],
                "verbalizes": verbalizes,
            }
            relationship["multiplicity"] = (
                OSSIE_MULTIPLICITY[attribute.multiplicity]
                if attribute.multiplicity is not None
                else "OneToOne"
                if attribute.identifier and identifier_count == 1
                else "ManyToOne"
            )
            if attribute.identifier:
                identifiers.append(attribute.technical_name)
            _attach_rules(relationship, draft, attribute.id)
            key = f"{object_type.technical_name}.{attribute.technical_name}"
            remember_rules(key, attribute.id)
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
                    draft,
                )
            )
            if link.identifier:
                identifiers.append(link.technical_name)
            key = f"{object_type.technical_name}.{link.technical_name}"
            display_names[key] = link.name
            remember_rules(key, link.id)
            if link.tags:
                tags[key] = sorted(link.tags)

        component: dict[str, Any] = {
            "concept": object_type.technical_name,
            "type": "EntityType",
            **({"description": object_type.description} if object_type.description else {}),
        }
        if object_type.extends:
            component["extends"] = sorted(
                by_id[parent].technical_name
                for parent in object_type.extends
                if parent in by_id
            )
        if identifiers:
            component["identify_by"] = sorted(identifiers)
        _attach_rules(component, draft, object_type.id)
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
                "rules": rule_ids,
                "actions": _compile_actions(draft),
            },
        },
        "ontology": components,
    }
    if draft.ontology_requires:
        document["requires"] = list(draft.ontology_requires)
    # Data mappings travel as ontology_mappings: table, key column and the
    # column behind each attribute, with no connection or credentials.
    ontology_mappings = compile_mappings(draft, objects)
    if ontology_mappings:
        document["ontology_mappings"] = ontology_mappings
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
