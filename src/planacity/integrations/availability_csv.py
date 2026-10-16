"""Generic availability CSV validation and immutable import, independent of Qt."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from planacity.domain import AvailabilityEvent, PlanningHorizon, ProgramPlan

FIELDS = ("person", "start", "end", "unavailable_fraction")


@dataclass(frozen=True)
class AvailabilityCsvTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    fingerprint: str


@dataclass(frozen=True)
class AvailabilityCsvMapping:
    columns: tuple[tuple[str, int], ...]
    delimiter: str = ","

    def __post_init__(self) -> None:
        names = [name for name, _ in self.columns]
        indices = [index for _, index in self.columns]
        if set(names) != set(FIELDS) or len(names) != len(FIELDS):
            raise ValueError("Map person, start, end, and unavailable share exactly once.")
        if len(set(indices)) != len(indices) or any(type(i) is not int or i < 0 for i in indices):
            raise ValueError("Map each CSV column at most once.")
        if self.delimiter not in (",", ";", "\t"):
            raise ValueError("Choose comma, semicolon, or tab as the delimiter.")


class AvailabilityRowState(StrEnum):
    READY = "ready"
    INVALID = "invalid"
    UNKNOWN_PERSON = "unknown_person"
    EXACT_DUPLICATE = "exact_duplicate"
    REPEATED_ROW = "repeated_row"


@dataclass(frozen=True)
class AvailabilityPreviewRow:
    line: int
    candidate_id: UUID
    raw: tuple[str, ...]
    person_value: str
    state: AvailabilityRowState
    event: AvailabilityEvent | None = None
    errors: tuple[str, ...] = ()
    overlapping_event_ids: tuple[UUID, ...] = ()
    outside_horizon: bool = False

    @property
    def selectable(self) -> bool:
        return self.state == AvailabilityRowState.READY and self.event is not None


@dataclass(frozen=True)
class AvailabilityImportPreview:
    table: AvailabilityCsvTable
    rows: tuple[AvailabilityPreviewRow, ...]

    @property
    def selectable_ids(self) -> frozenset[UUID]:
        return frozenset(row.candidate_id for row in self.rows if row.selectable)


def read_availability_csv(text: str, delimiter: str = ",") -> AvailabilityCsvTable:
    if delimiter not in (",", ";", "\t"):
        raise ValueError("Choose comma, semicolon, or tab as the delimiter.")
    clean = text.removeprefix("\ufeff")
    reader = csv.reader(io.StringIO(clean, newline=""), delimiter=delimiter, strict=True)
    try:
        headers = tuple(value.strip() for value in next(reader, ()))
        if not headers or any(not value for value in headers):
            raise ValueError("CSV requires nonblank column headers.")
        if len(set(headers)) != len(headers):
            raise ValueError("CSV column headers must be unique.")
        rows: list[tuple[str, ...]] = []
        for row in reader:
            if len(row) != len(headers):
                raise ValueError(
                    f"CSV line {reader.line_num}: expected {len(headers)} cells, "
                    f"found {len(row)}. Check the delimiter and quoting."
                )
            rows.append(tuple(row))
    except csv.Error as error:
        raise ValueError(f"CSV line {reader.line_num}: {error}.") from error
    if not rows:
        raise ValueError("The CSV has no availability rows.")
    return AvailabilityCsvTable(headers, tuple(rows), hashlib.sha256(clean.encode()).hexdigest())


def external_people(
    table: AvailabilityCsvTable, mapping: AvailabilityCsvMapping
) -> tuple[str, ...]:
    _validate_columns(table, mapping)
    index = dict(mapping.columns)["person"]
    return tuple(dict.fromkeys(row[index] for row in table.rows if row[index].strip()))


def preview_availability_import(
    plan: ProgramPlan,
    table: AvailabilityCsvTable,
    mapping: AvailabilityCsvMapping,
    people: dict[str, UUID],
) -> AvailabilityImportPreview:
    _validate_columns(table, mapping)
    known_people = {person.id for person in plan.people}
    if any(person_id not in known_people for person_id in people.values()):
        raise ValueError("Person mappings must reference the current plan roster.")
    columns = dict(mapping.columns)
    seen: set[tuple[str, str, str, str]] = set()
    result: list[AvailabilityPreviewRow] = []
    for line, raw in enumerate(table.rows, start=2):
        candidate_id = uuid5(NAMESPACE_URL, f"planacity:availability:{table.fingerprint}:{line}")
        values = {name: raw[index].strip() for name, index in columns.items()}
        signature = (
            values["person"],
            values["start"],
            values["end"],
            values["unavailable_fraction"],
        )
        person_value = values["person"]
        if signature in seen:
            result.append(
                AvailabilityPreviewRow(
                    line,
                    candidate_id,
                    raw,
                    person_value,
                    AvailabilityRowState.REPEATED_ROW,
                    errors=("This row repeats an earlier source row.",),
                )
            )
            continue
        seen.add(signature)
        person_id = people.get(person_value)
        if not person_value or person_id is None:
            result.append(
                AvailabilityPreviewRow(
                    line,
                    candidate_id,
                    raw,
                    person_value,
                    AvailabilityRowState.UNKNOWN_PERSON,
                    errors=(f"Map source person {person_value!r} to one roster person.",),
                )
            )
            continue
        try:
            start = _iso_date(values["start"], "start")
            end = _iso_date(values["end"], "end")
            period = PlanningHorizon(start, end)
            share = Decimal(values["unavailable_fraction"])
            event = AvailabilityEvent(
                id=candidate_id,
                person_id=person_id,
                period=period,
                unavailable_fraction=share,
            )
        except (ValueError, InvalidOperation) as error:
            result.append(
                AvailabilityPreviewRow(
                    line,
                    candidate_id,
                    raw,
                    person_value,
                    AvailabilityRowState.INVALID,
                    errors=(str(error),),
                )
            )
            continue
        exact = next(
            (
                current
                for current in plan.availability_events
                if current.person_id == event.person_id
                and current.period == event.period
                and current.unavailable_fraction == event.unavailable_fraction
            ),
            None,
        )
        overlaps = tuple(
            current.id
            for current in plan.availability_events
            if current.person_id == event.person_id
            and current.period.start <= event.period.end
            and event.period.start <= current.period.end
        )
        state = AvailabilityRowState.EXACT_DUPLICATE if exact else AvailabilityRowState.READY
        result.append(
            AvailabilityPreviewRow(
                line,
                candidate_id,
                raw,
                person_value,
                state,
                event,
                ("An identical availability entry already exists.",) if exact else (),
                overlaps,
                event.period.end < plan.horizon.start or event.period.start > plan.horizon.end,
            )
        )
    return AvailabilityImportPreview(table, tuple(result))


def apply_availability_import(
    plan: ProgramPlan, preview: AvailabilityImportPreview, selected_ids: frozenset[UUID]
) -> ProgramPlan:
    unknown = selected_ids - preview.selectable_ids
    if unknown:
        raise ValueError("Selection contains unavailable or invalid CSV rows.")
    events = tuple(
        row.event
        for row in preview.rows
        if row.candidate_id in selected_ids and row.event is not None
    )
    existing_ids = {current.id for current in plan.availability_events}
    if any(event.id in existing_ids for event in events):
        raise ValueError("An imported availability ID already exists in this plan.")
    known_people = {person.id for person in plan.people}
    if any(event.person_id not in known_people for event in events):
        raise ValueError("The roster changed after preview. Review the CSV again.")
    if any(
        current.person_id == event.person_id
        and current.period == event.period
        and current.unavailable_fraction == event.unavailable_fraction
        for event in events
        for current in plan.availability_events
    ):
        raise ValueError("Availability changed after preview. Review duplicate rows again.")
    return replace(plan, availability_events=(*plan.availability_events, *events))


def dump_mapping_profile(headers: tuple[str, ...], mapping: AvailabilityCsvMapping) -> str:
    return json.dumps(
        {
            "version": 1,
            "kind": "availability-csv",
            "headers": headers,
            "columns": mapping.columns,
            "delimiter": mapping.delimiter,
        },
        ensure_ascii=False,
    )


def load_mapping_profile(text: str, headers: tuple[str, ...]) -> AvailabilityCsvMapping:
    try:
        data = json.loads(text, object_pairs_hook=_unique_fields)
        if not isinstance(data, dict) or set(data) != {
            "version",
            "kind",
            "headers",
            "columns",
            "delimiter",
        }:
            raise ValueError("Unsupported availability mapping profile.")
        if data["version"] != 1 or data["kind"] != "availability-csv":
            raise ValueError("Unsupported availability mapping profile.")
        if data["headers"] != list(headers):
            raise ValueError("The profile's columns differ from this CSV. Map them again.")
        columns = data["columns"]
        if not isinstance(columns, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or type(pair[1]) is not int
            for pair in columns
        ):
            raise ValueError("Profile columns must contain name and position pairs.")
        return AvailabilityCsvMapping(
            tuple((name, index) for name, index in columns), data["delimiter"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Cannot load availability mapping profile: {error}") from error


def _validate_columns(table: AvailabilityCsvTable, mapping: AvailabilityCsvMapping) -> None:
    if any(index >= len(table.headers) for _, index in mapping.columns):
        raise ValueError("A mapped column is missing. Review the field mapping.")


def _iso_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field.title()} must use YYYY-MM-DD: {value!r}.") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field.title()} must use YYYY-MM-DD: {value!r}.")
    return parsed


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate mapping profile field: {name}.")
        result[name] = value
    return result
