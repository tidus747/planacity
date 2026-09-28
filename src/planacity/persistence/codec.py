"""Strict, versioned JSON representation shared by project files and backups."""

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

from planacity.domain import (
    Person,
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.domain.models import ImportedWork, ImportSnapshot

FORMAT = "planacity"
SCHEMA_VERSION = 2


def _encode(value: object) -> str:
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Unsupported project value: {type(value).__name__}")


def dumps(plan: ProgramPlan) -> str:
    return (
        json.dumps(
            {"format": FORMAT, "schema_version": SCHEMA_VERSION, "plan": asdict(plan)},
            default=_encode,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _object(value: object, keys: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError(f"Expected exactly these fields: {keys}.")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text; automatic conversion is not supported.")
    return value


def _id(value: object) -> UUID:
    return UUID(_text(value))


def _date(value: object) -> date:
    text = _text(value)
    result = date.fromisoformat(text)
    if result.isoformat() != text:
        raise ValueError("Dates must use YYYY-MM-DD.")
    return result


def _rows(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Expected an array.")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"Invalid JSON number: {value}.")


def loads(text: str) -> ProgramPlan:
    """Reject unknown fields and malformed data before constructing an editable plan."""
    try:
        root = _object(
            json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant),
            "format schema_version plan",
        )
        if root["format"] != FORMAT:
            raise ValueError("This is not a Planacity backup.")
        if type(root["schema_version"]) is not int or root["schema_version"] not in (
            1,
            SCHEMA_VERSION,
        ):
            raise ValueError(
                "Unsupported schema version. Open this file with a compatible Planacity."
            )
        p = _object(
            root["plan"],
            "id name description horizon work_items people work_groups relationships"
            + (" imports" if root["schema_version"] == 2 else ""),
        )
        h = _object(p["horizon"], "start end")
        people = []
        for value in _rows(p["people"]):
            row = _object(value, "id name")
            people.append(Person(id=_id(row["id"]), name=_text(row["name"])))
        work = [_work(value) for value in _rows(p["work_items"])]
        groups = []
        for value in _rows(p["work_groups"]):
            row = _object(value, "id name epic_ids")
            groups.append(
                WorkGroup(
                    id=_id(row["id"]),
                    name=_text(row["name"]),
                    epic_ids=tuple(_id(i) for i in _rows(row["epic_ids"])),
                )
            )
        links = []
        for value in _rows(p["relationships"]):
            row = _object(value, "id source_id target_id kind")
            links.append(
                Relationship(
                    id=_id(row["id"]),
                    source_id=_id(row["source_id"]),
                    target_id=_id(row["target_id"]),
                    kind=RelationshipType(_text(row["kind"])),
                )
            )
        return ProgramPlan(
            id=_id(p["id"]),
            name=_text(p["name"]),
            description=_text(p["description"]),
            horizon=PlanningHorizon(_date(h["start"]), _date(h["end"])),
            work_items=tuple(work),
            people=tuple(people),
            work_groups=tuple(groups),
            relationships=tuple(links),
            imports=tuple(_source(value) for value in _rows(p.get("imports", []))),
        )
    except (ValueError, InvalidOperation, RecursionError) as error:
        raise ValueError(f"Cannot read plan: {error}") from error


def _work(value: object) -> WorkItem:
    row = _object(value, "id title kind parent_id estimate_hours start end")
    return WorkItem(
        id=_id(row["id"]),
        title=_text(row["title"]),
        kind=WorkItemType(_text(row["kind"])),
        parent_id=None if row["parent_id"] is None else _id(row["parent_id"]),
        estimate_hours=None
        if row["estimate_hours"] is None
        else Decimal(_text(row["estimate_hours"])),
        start=None if row["start"] is None else _date(row["start"]),
        end=None if row["end"] is None else _date(row["end"]),
    )


def _source(value: object) -> ImportSnapshot:
    row = _object(value, "id name headers rows records")
    records = []
    for entry in _rows(row["records"]):
        r = _object(entry, "item external_reference external_person person status")
        person = None
        if r["person"] is not None:
            person_row = _object(r["person"], "id name")
            person = Person(id=_id(person_row["id"]), name=_text(person_row["name"]))
        records.append(
            ImportedWork(
                item=_work(r["item"]),
                external_reference=_text(r["external_reference"]),
                external_person=_text(r["external_person"]),
                person=person,
                status=_text(r["status"]),
            )
        )
    return ImportSnapshot(
        id=_id(row["id"]),
        name=_text(row["name"]),
        headers=tuple(_text(cell) for cell in _rows(row["headers"])),
        rows=tuple(tuple(_text(cell) for cell in _rows(cells)) for cells in _rows(row["rows"])),
        records=tuple(records),
    )
