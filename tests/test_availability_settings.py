"""Availability persistence, reference validation, and immutable lifecycle."""

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from test_calendar_settings import calendar_plan

from planacity.domain import AvailabilityEvent, Person
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.availability_settings import (
    add_availability,
    person_availability,
    remove_availability,
    update_availability,
)
from planacity.planning.calendar_settings import assign_calendar, remove_calendar
from planacity.planning.people import remove_person


def availability_plan():
    plan = calendar_plan()
    return add_availability(
        plan,
        AvailabilityEvent(
            person_id=plan.people[0].id,
            period=plan.horizon,
            unavailable_fraction=Decimal("0.5"),
        ),
    )


def test_lifecycle_keeps_identity_and_source_baseline():
    plan = availability_plan()
    event = plan.availability_events[0]
    changed = update_availability(plan, replace(event, unavailable_fraction=Decimal("0.25")))
    assert changed.availability_events[0].id == event.id
    assert changed.imports is plan.imports
    assert person_availability(changed, event.person_id).available_hours == Decimal("4.5")
    assert remove_availability(changed, event.id).availability_events == ()
    with pytest.raises(ValueError, match="Confirm"):
        remove_person(plan, event.person_id)
    removed = remove_person(plan, event.person_id, remove_availability=True)
    assert removed.availability_events == removed.person_calendars == ()
    assert removed.imports == plan.imports
    assert plan.availability_events == (event,)
    with pytest.raises(ValueError, match="unique"):
        add_availability(plan, event)
    with pytest.raises(ValueError, match="does not exist"):
        update_availability(plan, replace(event, id=uuid4()))
    with pytest.raises(ValueError, match="does not exist"):
        remove_availability(plan, uuid4())
    another = Person(name="Another")
    with pytest.raises(ValueError, match="cannot change"):
        update_availability(
            replace(plan, people=(*plan.people, another)), replace(event, person_id=another.id)
        )


def test_clearing_calendar_preserves_availability_and_reports_unknown():
    plan = availability_plan()
    person = plan.people[0]
    cleared = assign_calendar(plan, person.id, None)
    assert person_availability(cleared, person.id) is None
    assert cleared.availability_events == plan.availability_events
    deleted = remove_calendar(plan, plan.work_calendars[0].id, unassign=True)
    assert deleted.availability_events == plan.availability_events
    restored = assign_calendar(cleared, person.id, plan.work_calendars[0].id)
    assert person_availability(restored, person.id).available_hours == 3


def test_roundtrip_precision_and_jira_baseline(tmp_path):
    from test_jira_csv import CSV, MAPPING

    from planacity.integrations.jira.csv_io import preview_import, read_csv
    from planacity.integrations.jira.export import ExportOptions, export_csv

    plan = availability_plan()
    event = replace(
        plan.availability_events[0],
        unavailable_fraction=Decimal("0.123456789012345678901234567890"),
    )
    plan = update_availability(plan, event)
    path = tmp_path / "availability.planacity"
    save_project(plan, path)
    assert load_project(path) == loads(dumps(plan)) == plan
    assert load_project(path).availability_events[0].unavailable_fraction.as_tuple() == (
        event.unavailable_fraction.as_tuple()
    )
    imported = preview_import(plan, read_csv(CSV), MAPPING, {"Alice": plan.people[0]}, "more.csv")
    assert imported.availability_events == plan.availability_events
    removed = remove_availability(imported, event.id)
    assert removed.imports == imported.imports
    assert export_csv(imported, ExportOptions()) == export_csv(removed, ExportOptions())


@pytest.mark.parametrize("version", [1, 2, 3])
def test_old_schemas_open_unchanged_and_save_as_four(version, tmp_path):
    plan = calendar_plan()
    if version < 3:
        plan = replace(plan, work_calendars=(), person_calendars=())
    if version == 1:
        plan = replace(plan, imports=())
    data = json.loads(dumps(plan))
    data["schema_version"] = version
    data["plan"].pop("availability_events")
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    if version < 3:
        data["plan"].pop("work_calendars")
        data["plan"].pop("person_calendars")
    if version == 1:
        data["plan"].pop("imports")
    payload = json.dumps(data)
    assert loads(payload) == plan
    path = tmp_path / "old.planacity"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={version}")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (payload,))
    connection.close()
    before = path.read_bytes()
    assert load_project(path) == plan
    assert path.read_bytes() == before
    save_project(plan, path)
    assert load_project(path) == plan
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["availability_events"][0].update(person_id=str(uuid4())),
        lambda p: p["availability_events"][0].update(unavailable_fraction=0.5),
        lambda p: p["availability_events"][0].update(unavailable_fraction="NaN"),
        lambda p: p["availability_events"][0].update(unavailable_fraction="1.01"),
        lambda p: p["availability_events"][0]["period"].update(end="2026-01-01"),
        lambda p: p["availability_events"].append(p["availability_events"][0]),
        lambda p: p.pop("availability_events"),
    ],
)
def test_reject_malformed_or_dangling_availability(mutation):
    data = json.loads(dumps(availability_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError):
        loads(json.dumps(data))
