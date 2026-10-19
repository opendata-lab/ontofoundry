"""Core search labels and explicit synonyms."""


def synonyms(item):
    return item.get("synonyms", [])


def matches(item, query):
    query = query.casefold()
    return [
        {"source": field, "value": text}
        for field in ("name", "technical_name", "description", "synonyms", "tags", "source_role_name", "target_role_name", "verbalizes")
        for text in (
            item.get(field, [])
            if isinstance(item.get(field), list)
            else [item.get(field) or ""]
        )
        if query in text.casefold()
    ]
