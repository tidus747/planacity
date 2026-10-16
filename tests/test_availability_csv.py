"""Generic availability CSV imports remain explicit, reviewable, and immutable."""

from datetime import date
from decimal import Decimal

import pytest

from planacity.domain import AvailabilityEvent, Person, PlanningHorizon, ProgramPlan
from planacity.integrations.availability_csv import (
    AvailabilityCsvMapping,
    AvailabilityRowState,
    apply_availability_import,
    dump_mapping_profile,
    external_people,
    load_mapping_profile,
    preview_availability_import,
    read_availability_csv,
)

CSV = (
    "Person,From,To,Share,Note\n"
    "Alice,2027-01-05,2027-01-06,1,Holiday\n"
    "Bob,2027-02-01,2027-02-02,0.5,Quoted\n"
)
MAPPING = AvailabilityCsvMapping(
    (("person", 0), ("start", 1), ("end", 2), ("unavailable_fraction", 3))
)


def plan() -> ProgramPlan:
    return ProgramPlan(
        name="Availability import",
        horizon=PlanningHorizon(date(2027, 1, 1), date(2027, 1, 31)),
        people=(Person(name="Alice"), Person(name="Bob")),
    )


def test_preview_and_selected_apply_preserve_unrelated_plan_data() -> None:
    original = plan()
    table = read_availability_csv(CSV)
    preview = preview_availability_import(
        original, table, MAPPING, {person.name: person.id for person in original.people}
    )

    assert external_people(table, MAPPING) == ("Alice", "Bob")
    assert [row.state for row in preview.rows] == [
        AvailabilityRowState.READY,
        AvailabilityRowState.READY,
    ]
    assert preview.rows[1].outside_horizon
    assert preview.rows[0].event is not None
    assert preview.rows[0].event.unavailable_fraction == Decimal(1)

    updated = apply_availability_import(
        original, preview, frozenset((preview.rows[0].candidate_id,))
    )

    assert original.availability_events == ()
    assert len(updated.availability_events) == 1
    assert updated.people is original.people
    assert updated.imports is original.imports


def test_preview_reports_unknown_invalid_repeated_duplicate_and_overlap() -> None:
    original = plan()
    alice = original.people[0]
    existing = AvailabilityEvent(
        person_id=alice.id,
        period=PlanningHorizon(date(2027, 1, 5), date(2027, 1, 6)),
        unavailable_fraction=Decimal(1),
    )
    original = ProgramPlan(
        name=original.name,
        horizon=original.horizon,
        people=original.people,
        availability_events=(existing,),
    )
    text = (
        "Person,From,To,Share\n"
        "Alice,2027-01-05,2027-01-06,1\n"
        "Alice,2027-01-06,2027-01-07,0.5\n"
        "Alice,2027-01-06,2027-01-07,0.5\n"
        "Unknown,2027-01-08,2027-01-08,1\n"
        "Alice,2027/01/09,2027-01-09,1\n"
        "Alice,2027-01-10,2027-01-10,1.1\n"
    )
    preview = preview_availability_import(
        original, read_availability_csv(text), MAPPING, {"Alice": alice.id}
    )

    assert [row.state for row in preview.rows] == [
        AvailabilityRowState.EXACT_DUPLICATE,
        AvailabilityRowState.READY,
        AvailabilityRowState.REPEATED_ROW,
        AvailabilityRowState.UNKNOWN_PERSON,
        AvailabilityRowState.INVALID,
        AvailabilityRowState.INVALID,
    ]
    assert preview.rows[0].overlapping_event_ids == (existing.id,)
    assert preview.rows[1].overlapping_event_ids == (existing.id,)
    assert preview.selectable_ids == frozenset((preview.rows[1].candidate_id,))
    with pytest.raises(ValueError, match="invalid CSV rows"):
        apply_availability_import(original, preview, frozenset((preview.rows[0].candidate_id,)))


@pytest.mark.parametrize(
    ("text", "message"),
    (
        ("", "nonblank column headers"),
        ("A,A\n1,2\n", "headers must be unique"),
        ("A,B\n1\n", "expected 2 cells"),
        ('A,B\n"open,2\n', "CSV line"),
        ("A,B\n", "no availability rows"),
    ),
)
def test_csv_structure_errors_are_actionable(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        read_availability_csv(text)


def test_bom_quoted_values_custom_order_and_stable_candidate_ids() -> None:
    source = '\ufeffShare,End,Person,Start\n"0.25",2027-01-04,"Alice",2027-01-03\n'
    mapping = AvailabilityCsvMapping(
        (("unavailable_fraction", 0), ("end", 1), ("person", 2), ("start", 3))
    )
    original = plan()
    table = read_availability_csv(source)

    first = preview_availability_import(original, table, mapping, {"Alice": original.people[0].id})
    second = preview_availability_import(original, table, mapping, {"Alice": original.people[0].id})

    assert first.rows[0].candidate_id == second.rows[0].candidate_id
    assert first.rows[0].event is not None
    assert first.rows[0].event.period.start == date(2027, 1, 3)


def test_mapping_profile_roundtrip_rejects_rows_and_ambiguous_json() -> None:
    headers = read_availability_csv(CSV).headers
    encoded = dump_mapping_profile(headers, MAPPING)
    assert load_mapping_profile(encoded, headers) == MAPPING
    assert "Alice" not in encoded
    with pytest.raises(ValueError, match="columns differ"):
        load_mapping_profile(encoded, ("Different",))
    with pytest.raises(ValueError, match="Duplicate mapping profile field"):
        load_mapping_profile(
            '{"version":1,"version":1,"kind":"availability-csv",'
            '"headers":[],"columns":[],"delimiter":","}',
            (),
        )


def test_mapping_and_people_references_are_validated() -> None:
    table = read_availability_csv(CSV)
    original = plan()
    with pytest.raises(ValueError, match="mapped column is missing"):
        preview_availability_import(
            original,
            table,
            AvailabilityCsvMapping(
                (("person", 0), ("start", 1), ("end", 2), ("unavailable_fraction", 99))
            ),
            {},
        )
    with pytest.raises(ValueError, match="current plan roster"):
        preview_availability_import(original, table, MAPPING, {"Alice": existing_uuid()})


def test_apply_rejects_a_duplicate_added_after_preview() -> None:
    original = plan()
    preview = preview_availability_import(
        original,
        read_availability_csv(CSV),
        MAPPING,
        {person.name: person.id for person in original.people},
    )
    candidate = preview.rows[0]
    assert candidate.event is not None
    changed = ProgramPlan(
        name=original.name,
        horizon=original.horizon,
        people=original.people,
        availability_events=(
            AvailabilityEvent(
                person_id=candidate.event.person_id,
                period=candidate.event.period,
                unavailable_fraction=candidate.event.unavailable_fraction,
            ),
        ),
    )

    with pytest.raises(ValueError, match="changed after preview"):
        apply_availability_import(changed, preview, frozenset((candidate.candidate_id,)))


def existing_uuid():
    from uuid import uuid4

    return uuid4()
