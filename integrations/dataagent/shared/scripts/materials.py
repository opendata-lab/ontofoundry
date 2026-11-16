"""This run's material lines, so evidence can be written as a line number and quoted by script."""

from pathlib import Path


def material_lines(pack):
    """material id -> text lines; an unreadable material maps to no lines."""
    lines = {}
    for material in pack.get("materials") or []:
        if material.get("path") and material.get("id"):
            try:
                lines[material["id"]] = Path(material["path"]).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                lines[material["id"]] = []
    return lines


def quote(lines, start, end):
    return " ".join(line.strip() for line in lines[start - 1:end])[:2000]


def fill_quotes(value, texts):
    """Quote every material evidence that names lines but no text; a written quote is kept.

    The platform accepts an empty quote but stores what is given, so reviewers see the
    cited text without the agent copying it (2026-11-15 review: copying cost output tokens).
    """
    if isinstance(value, dict):
        locator = value.get("locator")
        if (value.get("kind", "material") == "material" and value.get("material_id") in texts
                and not value.get("quote") and isinstance(locator, dict)):
            start, end = locator.get("line_start"), locator.get("line_end")
            lines = texts[value["material_id"]]
            if isinstance(start, int) and isinstance(end, int) and 0 < start <= end <= len(lines):
                value["quote"] = quote(lines, start, end)
        for child in value.values():
            fill_quotes(child, texts)
    elif isinstance(value, list):
        for child in value:
            fill_quotes(child, texts)
