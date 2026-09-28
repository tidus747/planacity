"""Portable column mapping preferences; no CSV rows or person identities."""

import json

from planacity.domain import WorkItemType
from planacity.integrations.jira.csv_io import Mapping


def dump_profile(headers: tuple[str, ...], mapping: Mapping) -> str:
    return json.dumps(
        {
            "version": 1,
            "headers": headers,
            "columns": mapping.columns,
            "estimate_unit": mapping.estimate_unit,
            "date_format": mapping.date_format,
            "types": mapping.types,
        },
        ensure_ascii=False,
    )


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguity before JSON decoding can discard an earlier setting."""
    fields: dict[str, object] = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError(
                f"Duplicate mapping profile field: {name}. "
                "Keep one value for each field, or save a new profile from the import wizard."
            )
        fields[name] = value
    return fields


def load_profile(text: str, headers: tuple[str, ...]) -> Mapping:
    try:
        data = json.loads(text, object_pairs_hook=_unique_fields)
        if (
            not isinstance(data, dict)
            or set(data)
            != {"version", "headers", "columns", "estimate_unit", "date_format", "types"}
            or type(data["version"]) is not int
            or data["version"] != 1
        ):
            raise ValueError("Unsupported mapping profile.")
        if data["headers"] != list(headers):
            raise ValueError("The profile's columns differ from this CSV. Map them again.")
        for key in ("columns", "types"):
            if not isinstance(data[key], list) or any(
                not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str)
                for pair in data[key]
            ):
                raise ValueError("Profile mappings must contain named pairs.")
        if any(type(pair[1]) is not int for pair in data["columns"]):
            raise ValueError("Profile column positions must be integers.")
        if any(not isinstance(pair[1], str) for pair in data["types"]):
            raise ValueError("Profile work types must be text.")
        return Mapping(
            tuple((name, index) for name, index in data["columns"]),
            data["estimate_unit"],
            data["date_format"],
            tuple((name, WorkItemType(kind)) for name, kind in data["types"]),
        )
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError(f"Cannot load mapping profile: {error}") from error
