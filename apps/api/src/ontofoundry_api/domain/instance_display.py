"""Derived instance labels and complete business identities."""

from ontofoundry_api.domain.graph import draft_index


def present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def business_identity(draft, type_id, values):
    props = draft_index(draft).identifier(type_id)
    if not props or any(not present(values.get(p.name)) for p in props):
        return None
    return tuple((p.value_kind.value, values[p.name]) for p in props)


def _label(draft, type_id, values):
    prop = draft_index(draft).title_property(type_id)
    if prop and present(values.get(prop.name)):
        return str(values[prop.name])
    identity = business_identity(draft, type_id, values)
    if identity is not None:
        return " · ".join(str(v) for _, v in identity)
    return None


def document_display_text(draft, fact):
    label = _label(draft, fact.type_id, fact.values)
    if label is not None:
        return label
    quotes = sorted(
        (e for e in fact.evidence if e.kind == "material" and e.quote.strip()),
        key=lambda e: e.id.bytes,
    )
    return quotes[0].quote[:80] if quotes else str(fact.id)


def database_display_text(draft, type_id, values, key):
    return _label(draft, type_id, values) or " · ".join(str(part["value"]) for part in key)
