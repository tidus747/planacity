"""Shared calendar-event domain, persistence, and capacity behavior."""

import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    AvailabilityEvent,
    CalendarEvent,
    CalendarEventKind,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    ReservationRule,
    WorkCalendar,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import SCHEMA_VERSION, dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.availability import availability_capacity
from planacity.planning.calendar_events import (
    add_calendar_event,
    remove_calendar_event,
    update_calendar_event,
)
from planacity.planning.capacity import calculate_dated_capacity
from planacity.planning.capacity_breakdown import calculate_capacity_breakdown
from planacity.planning.reservation_preview import preview_plan_reservations

MONDAY = date(2027, 1, 4)
TUESDAY = date(2027, 1, 5)
WEEK = PlanningHorizon(MONDAY, date(2027, 1, 8))


def event(
    fraction: str,
    *,
    name: str = "Shared event",
    kind: CalendarEventKind = CalendarEventKind.PROGRAM_EVENT,
    period: PlanningHorizon | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        name=name,
        kind=kind,
        period=period or PlanningHorizon(MONDAY, MONDAY),
        unavailable_fraction=Decimal(fraction),
    )


def capacity_plan(*events: CalendarEvent) -> ProgramPlan:
    alex = Person(name="Alex")
    sam = Person(name="Sam")
    full_time = WorkCalendar(
        name="Full time",
        weekday_hours=(Decimal(8),) * 5 + (Decimal(0),) * 2,
    )
    part_time = WorkCalendar(
        name="Part time",
        weekday_hours=(Decimal(4),) * 5 + (Decimal(0),) * 2,
    )
    return ProgramPlan(
        name="Shared calendar",
        horizon=WEEK,
        people=(alex, sam),
        work_calendars=(full_time, part_time),
        person_calendars=(
            PersonCalendar(person_id=alex.id, calendar_id=full_time.id),
            PersonCalendar(person_id=sam.id, calendar_id=part_time.id),
        ),
        calendar_events=events,
    )


@pytest.mark.parametrize("kind", list(CalendarEventKind))
def test_every_kind_is_valid_and_round_trips(kind):
    shared = event("0", kind=kind)
    plan = capacity_plan(shared)

    assert loads(dumps(plan)) == plan
    assert loads(dumps(plan)).calendar_events[0].kind == kind


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"id": "not a UUID"}, "ID"),
        ({"name": "  "}, "name"),
        ({"kind": "holiday"}, "kind"),
        ({"period": "2027-01-04"}, "period"),
        ({"unavailable_fraction": Decimal("NaN")}, "fraction"),
        ({"unavailable_fraction": Decimal("-0.01")}, "fraction"),
        ({"unavailable_fraction": Decimal("1.01")}, "fraction"),
        ({"unavailable_fraction": 0.5}, "fraction"),
    ],
)
def test_domain_rejects_invalid_values(changes, message):
    values = {
        "name": "Holiday",
        "kind": CalendarEventKind.PUBLIC_HOLIDAY,
        "period": PlanningHorizon(MONDAY, MONDAY),
        "unavailable_fraction": Decimal(1),
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        CalendarEvent(**values)


def test_lifecycle_preserves_identity_imports_and_unrelated_plan_data():
    first = event("1", name="Holiday", kind=CalendarEventKind.PUBLIC_HOLIDAY)
    second = event("0", name="Customer visit", kind=CalendarEventKind.CUSTOMER_VISIT)
    plan = capacity_plan(first)
    added = add_calendar_event(plan, second)
    changed = update_calendar_event(added, replace(first, name="Company shutdown"))
    removed = remove_calendar_event(changed, second.id)

    assert changed.calendar_events == (replace(first, name="Company shutdown"), second)
    assert removed.calendar_events[0].id == first.id
    assert removed.people is plan.people
    assert removed.imports is plan.imports
    assert plan.calendar_events == (first,)
    with pytest.raises(ValueError, match="unique"):
        add_calendar_event(plan, first)
    with pytest.raises(ValueError, match="does not exist"):
        update_calendar_event(plan, replace(first, id=uuid4()))
    with pytest.raises(ValueError, match="does not exist"):
        remove_calendar_event(plan, uuid4())
    with pytest.raises(ValueError, match="UUID"):
        remove_calendar_event(plan, "bad")  # type: ignore[arg-type]


def test_full_and_partial_events_use_each_persons_nominal_calendar_hours():
    holiday = event("1", name="Holiday", kind=CalendarEventKind.PUBLIC_HOLIDAY)
    review = event(
        "0.25",
        name="Review",
        period=PlanningHorizon(TUESDAY, TUESDAY),
    )
    result = calculate_dated_capacity(capacity_plan(holiday, review), WEEK)

    assert [person.unavailable_hours for person in result.people] == [10, 5]
    assert [person.available_hours for person in result.people] == [30, 15]
    assert [person.days[0].available_hours for person in result.people] == [0, 0]
    assert [person.days[1].available_hours for person in result.people] == [6, 3]


def test_zero_and_outside_events_do_not_change_capacity():
    visit = event("0", kind=CalendarEventKind.CUSTOMER_VISIT)
    outside = event(
        "1",
        period=PlanningHorizon(date(2028, 1, 3), date(2028, 1, 3)),
    )
    result = calculate_dated_capacity(capacity_plan(visit, outside), WEEK)

    assert [person.unavailable_hours for person in result.people] == [0, 0]
    assert [person.available_hours for person in result.people] == [40, 20]


def test_personal_and_shared_overlaps_use_the_strongest_fraction_once():
    plan = capacity_plan(event("0.25"))
    personal = AvailabilityEvent(
        person_id=plan.people[0].id,
        period=PlanningHorizon(MONDAY, MONDAY),
        unavailable_fraction=Decimal("0.5"),
    )
    plan = replace(plan, availability_events=(personal,))
    result = calculate_dated_capacity(plan, WEEK)

    assert result.people[0].days[0].unavailable_hours == 4
    assert result.people[0].days[0].available_hours == 4
    assert result.people[1].days[0].unavailable_hours == 1
    overlap = availability_capacity(
        plan.work_calendars[0],
        PlanningHorizon(MONDAY, MONDAY),
        plan.people[0].id,
        (personal,),
        plan.calendar_events,
    ).overlaps
    assert overlap[0].event_ids == tuple(sorted((personal.id, plan.calendar_events[0].id), key=str))


def test_full_holiday_and_full_personal_leave_do_not_double_deduct():
    plan = capacity_plan(event("1", kind=CalendarEventKind.PUBLIC_HOLIDAY))
    absence = AvailabilityEvent(
        person_id=plan.people[0].id,
        period=PlanningHorizon(MONDAY, MONDAY),
        unavailable_fraction=Decimal(1),
    )
    result = calculate_dated_capacity(replace(plan, availability_events=(absence,)), WEEK)

    assert result.people[0].days[0].nominal_hours == 8
    assert result.people[0].days[0].unavailable_hours == 8
    assert result.people[0].days[0].available_hours == 0


def test_shared_events_shape_reservations_and_work_after_availability():
    plan = capacity_plan(event("1", kind=CalendarEventKind.PUBLIC_HOLIDAY))
    person = plan.people[0]
    work = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        start=MONDAY,
        end=TUESDAY,
    )
    duty = ReservationRule(
        name="Support",
        person_ids=(person.id,),
        hours_per_person=Decimal(2),
        anchor=MONDAY,
        interval_weeks=1,
        effective=PlanningHorizon(MONDAY, TUESDAY),
    )
    plan = replace(
        plan,
        work_items=(work,),
        allocations=(Allocation(work_item_id=work.id, person_id=person.id, hours=Decimal(12)),),
        reservation_rules=(duty,),
    )
    result = calculate_dated_capacity(plan, PlanningHorizon(MONDAY, TUESDAY)).people[0]
    breakdown = calculate_capacity_breakdown(plan, PlanningHorizon(MONDAY, TUESDAY)).people[0]
    preview = preview_plan_reservations(plan)[0]

    assert result.days[0].planning_hours == 0
    assert result.days[0].allocated_hours == 0
    assert result.days[1].reserved_hours == Fraction(1, 2)
    assert result.days[1].allocated_hours == 12
    assert result.days[1].remaining_hours == Fraction(-9, 2)
    assert breakdown.unavailable_hours == result.unavailable_hours == 8
    assert breakdown.reserved_hours == result.reserved_hours == Fraction(1, 2)
    assert preview.days[0].available_hours == 0
    assert preview.days[0].reserved_hours == 0
    # The weekly rule is prorated over Tuesday-Friday after Monday's holiday,
    # while its effective range includes only Tuesday in this preview.
    assert preview.reserved_hours == Fraction(1, 2)


def test_order_precision_and_input_are_preserved():
    first = event("0.123456789012345678901234567890", name="First")
    second = event("0.25", name="Second")
    plan = capacity_plan(first, second)
    before = repr(plan)

    with localcontext() as context:
        context.prec = 2
        expected = calculate_dated_capacity(plan, WEEK)
        reordered = calculate_dated_capacity(replace(plan, calendar_events=(second, first)), WEEK)
        assert expected == reordered
        assert expected.people[0].days[0].unavailable_hours == Fraction(2)
        assert context.prec == 2
    assert repr(plan) == before


def test_schema_twelve_json_and_sqlite_roundtrip(tmp_path):
    plan = capacity_plan(event("0.333333333333333333333333333333"))
    data = json.loads(dumps(plan))
    path = tmp_path / "calendar.planacity"
    save_project(plan, path)

    assert data["schema_version"] == SCHEMA_VERSION == 12
    assert data["plan"]["calendar_events"][0]["unavailable_fraction"] == (
        "0.333333333333333333333333333333"
    )
    assert loads(json.dumps(data)) == load_project(path) == plan
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12


def test_schema_eleven_loads_without_events_and_upgrades_only_on_save(tmp_path):
    plan = capacity_plan()
    data = json.loads(dumps(plan))
    data["schema_version"] = 11
    data["plan"].pop("calendar_events")
    payload = json.dumps(data)
    path = tmp_path / "schema-11.planacity"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=11")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (payload,))
    connection.close()
    before = path.read_bytes()

    assert loads(payload) == plan
    assert load_project(path) == plan
    assert path.read_bytes() == before
    save_project(plan, path)
    assert load_project(path) == plan
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event.update(name=""),
        lambda event: event.update(kind="vacation"),
        lambda event: event.update(unavailable_fraction=0.5),
        lambda event: event.update(unavailable_fraction="NaN"),
        lambda event: event.update(unavailable_fraction="1.01"),
        lambda event: event["period"].update(start="2027-01-04T12:00:00"),
        lambda event: event.update(extra="value"),
    ],
)
def test_malformed_persisted_event_is_rejected(mutation):
    data = json.loads(dumps(capacity_plan(event("0.5"))))
    mutation(data["plan"]["calendar_events"][0])
    with pytest.raises(ValueError, match="Cannot read plan"):
        loads(json.dumps(data))


def test_duplicate_event_ids_and_missing_collection_are_rejected():
    data = json.loads(dumps(capacity_plan(event("0.5"))))
    data["plan"]["calendar_events"].append(data["plan"]["calendar_events"][0])
    with pytest.raises(ValueError, match="unique"):
        loads(json.dumps(data))
    data = json.loads(dumps(capacity_plan()))
    data["plan"].pop("calendar_events")
    with pytest.raises(ValueError, match="exactly these fields"):
        loads(json.dumps(data))
