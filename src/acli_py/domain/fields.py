"""The site's fields: what each is called, its type, and how a custom field is made."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

CUSTOM = "com.atlassian.jira.plugin.system.customfieldtypes:"
# Friendly names for custom field types: name → (type, the searcher that fits it).
FIELD_TYPES: dict[str, tuple[str, str]] = {
    "text": ("textfield", "textsearcher"),
    "textarea": ("textarea", "textsearcher"),
    "number": ("float", "exactnumber"),
    "select": ("select", "multiselectsearcher"),
    "multiselect": ("multiselect", "multiselectsearcher"),
    "checkbox": ("multicheckboxes", "multiselectsearcher"),
    "radio": ("radiobuttons", "multiselectsearcher"),
    "date": ("datepicker", "daterange"),
    "datetime": ("datetime", "datetimerange"),
    "url": ("url", "exacttextsearcher"),
    "labels": ("labels", "labelsearcher"),
    "user": ("userpicker", "userpickergroupsearcher"),
    "multiuser": ("multiuserpicker", "userpickergroupsearcher"),
    "group": ("grouppicker", "grouppickersearcher"),
}


def custom_field_type(kind: str, searcher: str | None = None) -> tuple[str, str | None]:
    """Return the Jira type and searcher keys for `kind`: a name from `FIELD_TYPES`, or a key.

    Raises `ValueError` for anything else.
    """
    if kind.lower() in FIELD_TYPES:
        name, default_searcher = FIELD_TYPES[kind.lower()]
        return CUSTOM + name, searcher or CUSTOM + default_searcher
    if ":" in kind:
        return kind, searcher
    raise ValueError(f"Unknown field type {kind!r}. Use one of: {', '.join(FIELD_TYPES)}.")


@dataclass(frozen=True)
class FieldInfo:
    """A field of the site: its id (for --field and JQL), name, type and JQL names."""

    id: str
    name: str
    type: str = ""
    custom: bool = False
    clauses: tuple[str, ...] = ()

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> FieldInfo:
        """Read a field from Jira's JSON."""
        schema = data.get("schema") or {}
        custom_type = schema.get("custom", "")
        kind = custom_type.split(":")[-1] if custom_type else schema.get("type", "")
        if schema.get("type") == "array" and not custom_type:
            kind = f"{schema.get('items')}[]"
        return cls(
            str(data.get("id", "")),
            data.get("name", ""),
            kind,
            bool(data.get("custom")),
            tuple(data.get("clauseNames") or ()),
        )

    def matches(self, text: str) -> bool:
        """Return whether `text` is part of the field's name or id, ignoring case."""
        text = text.lower()
        return text in self.name.lower() or text in self.id.lower()
