"""Portable column mapping preferences; no CSV rows or person identities."""

import json

from planacity.domain import WorkItemType, WorkPriority
from planacity.integrations.jira.csv_io import Mapping
from planacity.integrations.jira.export import ExportOptions


def dump_profile(headers: tuple[str, ...], mapping: Mapping) -> str:
    return json.dumps(
        {
            "version": 2,
            "headers": headers,
            "columns": mapping.columns,
            "estimate_unit": mapping.estimate_unit,
            "date_format": mapping.date_format,
            "types": mapping.types,
            "priorities": mapping.priorities,
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
        if not isinstance(data, dict) or type(data.get("version")) is not int:
            raise ValueError("Unsupported mapping profile.")
        version = data["version"]
        expected = {"version", "headers", "columns", "estimate_unit", "date_format", "types"}
        if version == 2:
            expected.add("priorities")
        if version not in (1, 2) or set(data) != expected:
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
        priorities = data.get("priorities", [])
        if not isinstance(priorities, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or (pair[1] is not None and not isinstance(pair[1], str))
            for pair in priorities
        ):
            raise ValueError("Profile priority mappings must contain named pairs.")
        return Mapping(
            tuple((name, index) for name, index in data["columns"]),
            data["estimate_unit"],
            data["date_format"],
            tuple((name, WorkItemType(kind)) for name, kind in data["types"]),
            tuple(
                (name, None if priority is None else WorkPriority(priority))
                for name, priority in priorities
            ),
        )
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError(f"Cannot load mapping profile: {error}") from error


def dump_export_profile(options: ExportOptions) -> str:
    return json.dumps(
        {
            "version": 1,
            "kind": "jira-export",
            "headers": options.headers,
            "estimate_unit": options.estimate_unit,
            "date_format": options.date_format,
            "delimiter": options.delimiter,
            "priority_labels": options.priority_labels,
        },
        ensure_ascii=False,
    )


def load_export_profile(text: str) -> ExportOptions:
    try:
        data = json.loads(text, object_pairs_hook=_unique_fields)
        expected = {
            "version",
            "kind",
            "headers",
            "estimate_unit",
            "date_format",
            "delimiter",
            "priority_labels",
        }
        if (
            not isinstance(data, dict)
            or set(data) != expected
            or type(data["version"]) is not int
            or data["version"] != 1
            or data["kind"] != "jira-export"
        ):
            raise ValueError("Unsupported export mapping profile.")
        if not isinstance(data["headers"], list) or any(
            not isinstance(header, str) for header in data["headers"]
        ):
            raise ValueError("Export profile headers must be text.")
        labels = data["priority_labels"]
        if not isinstance(labels, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
            for pair in labels
        ):
            raise ValueError("Export priority labels must contain text pairs.")
        return ExportOptions(
            headers=tuple(data["headers"]),
            estimate_unit=data["estimate_unit"],
            date_format=data["date_format"],
            delimiter=data["delimiter"],
            priority_labels=tuple((WorkPriority(priority), label) for priority, label in labels),
        )
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError(f"Cannot load export mapping profile: {error}") from error
