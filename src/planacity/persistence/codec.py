"""Strict, versioned JSON representation shared by project files and backups."""

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

from planacity.domain import (
    Allocation,
    AvailabilityEvent,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    ReservationRule,
    WorkCalendar,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.domain.estimate_units import EstimatePreferences, EstimateUnit
from planacity.domain.models import ImportedWork, ImportSnapshot

FORMAT = "planacity"
SCHEMA_VERSION = 8
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8)


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


def loads(text: str, *, expected_schema_version: int | None = None) -> ProgramPlan:
    """Reject unknown fields and malformed data before constructing an editable plan."""
    try:
        root = _object(
            json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant),
            "format schema_version plan",
        )
        if root["format"] != FORMAT:
            raise ValueError("This is not a Planacity backup.")
        if (
            type(root["schema_version"]) is not int
            or root["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS
        ):
            raise ValueError(
                "Unsupported schema version. Open this file with a compatible Planacity."
            )
        if (
            expected_schema_version is not None
            and root["schema_version"] != expected_schema_version
        ):
            raise ValueError(
                f"Project container version {expected_schema_version} does not match "
                f"document schema version {root['schema_version']}."
            )
        schema_version = root["schema_version"]
        p = _object(
            root["plan"],
            "id name description horizon work_items people work_groups relationships"
            + (" imports" if schema_version in (2, 3, 4, 5, 6, 7, 8) else "")
            + (" work_calendars person_calendars" if schema_version in (3, 4, 5, 6, 7, 8) else "")
            + (" availability_events" if schema_version in (4, 5, 6, 7, 8) else "")
            + (" reservation_rules" if schema_version in (5, 6, 7, 8) else "")
            + (" estimate_preferences" if schema_version in (6, 7, 8) else "")
            + (" allocations" if schema_version in (7, 8) else ""),
        )
        h = _object(p["horizon"], "start end")
        people = []
        for value in _rows(p["people"]):
            row = _object(value, "id name")
            people.append(Person(id=_id(row["id"]), name=_text(row["name"])))
        work = [_work(value, schema_version) for value in _rows(p["work_items"])]
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
            imports=tuple(_source(value, schema_version) for value in _rows(p.get("imports", []))),
            work_calendars=tuple(_calendar(value) for value in _rows(p.get("work_calendars", []))),
            person_calendars=tuple(
                _assignment(value) for value in _rows(p.get("person_calendars", []))
            ),
            availability_events=tuple(
                _availability(value) for value in _rows(p.get("availability_events", []))
            ),
            reservation_rules=tuple(
                _reservation(value) for value in _rows(p.get("reservation_rules", []))
            ),
            allocations=tuple(_allocation(value) for value in _rows(p.get("allocations", []))),
            estimate_preferences=(
                _estimate_preferences(p["estimate_preferences"])
                if "estimate_preferences" in p
                else EstimatePreferences()
            ),
        )
    except (ValueError, InvalidOperation, RecursionError) as error:
        raise ValueError(f"Cannot read plan: {error}") from error


def _allocation(value: object) -> Allocation:
    row = _object(value, "id work_item_id person_id hours")
    return Allocation(
        id=_id(row["id"]),
        work_item_id=_id(row["work_item_id"]),
        person_id=_id(row["person_id"]),
        hours=Decimal(_text(row["hours"])),
    )


def _estimate_preferences(value: object) -> EstimatePreferences:
    row = _object(value, "unit calendar_id")
    return EstimatePreferences(
        unit=EstimateUnit(_text(row["unit"])),
        calendar_id=_id(row["calendar_id"]) if row["calendar_id"] is not None else None,
    )


def _reservation(value: object) -> ReservationRule:
    row = _object(value, "id name person_ids hours_per_person anchor interval_weeks effective")
    effective = _object(row["effective"], "start end")
    interval = row["interval_weeks"]
    if type(interval) is not int:
        raise ValueError("Reservation interval must be a whole number of weeks.")
    return ReservationRule(
        id=_id(row["id"]),
        name=_text(row["name"]),
        person_ids=tuple(_id(value) for value in _rows(row["person_ids"])),
        hours_per_person=Decimal(_text(row["hours_per_person"])),
        anchor=_date(row["anchor"]),
        interval_weeks=interval,
        effective=PlanningHorizon(_date(effective["start"]), _date(effective["end"])),
    )


def _availability(value: object) -> AvailabilityEvent:
    row = _object(value, "id person_id period unavailable_fraction")
    period = _object(row["period"], "start end")
    return AvailabilityEvent(
        id=_id(row["id"]),
        person_id=_id(row["person_id"]),
        period=PlanningHorizon(_date(period["start"]), _date(period["end"])),
        unavailable_fraction=Decimal(_text(row["unavailable_fraction"])),
    )


def _calendar(value: object) -> WorkCalendar:
    row = _object(value, "id name weekday_hours")
    return WorkCalendar(
        id=_id(row["id"]),
        name=_text(row["name"]),
        weekday_hours=tuple(Decimal(_text(value)) for value in _rows(row["weekday_hours"])),
    )


def _assignment(value: object) -> PersonCalendar:
    row = _object(value, "person_id calendar_id")
    return PersonCalendar(person_id=_id(row["person_id"]), calendar_id=_id(row["calendar_id"]))


def _work(value: object, schema_version: int) -> WorkItem:
    fields = "id title kind parent_id estimate_hours start end"
    if schema_version >= 8:
        fields += " description labels primary_group_id"
    row = _object(value, fields)
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
        description=_text(row["description"]) if schema_version >= 8 else "",
        labels=(
            tuple(_text(label) for label in _rows(row["labels"])) if schema_version >= 8 else ()
        ),
        primary_group_id=(
            None
            if schema_version < 8 or row["primary_group_id"] is None
            else _id(row["primary_group_id"])
        ),
    )


def _source(value: object, schema_version: int) -> ImportSnapshot:
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
                item=_work(r["item"], schema_version),
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
