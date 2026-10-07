"""Calendar references, migration, lifecycle and exact persistence."""

import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from persistence_helpers import strip_work_context

from planacity.domain import Person, PlanningHorizon, ProgramPlan, WorkCalendar
from planacity.domain.models import ImportedWork, ImportSnapshot, WorkItem, WorkItemType
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.calendar_settings import (
    add_calendar,
    assign_calendar,
    remove_calendar,
    update_calendar,
)
from planacity.planning.people import remove_person


def test_jira_import_and_export_preserve_calendar_settings_and_baseline():
    from test_jira_csv import CSV, MAPPING

    from planacity.integrations.jira.csv_io import preview_import, read_csv
    from planacity.integrations.jira.export import ExportOptions, export_csv

    plan = calendar_plan()
    imported = preview_import(plan, read_csv(CSV), MAPPING, {"Alice": plan.people[0]}, "more.csv")
    assert imported.work_calendars == plan.work_calendars
    assert imported.person_calendars == plan.person_calendars
    before = export_csv(imported, ExportOptions())
    changed = update_calendar(imported, replace(plan.work_calendars[0], name="Renamed"))
    assert changed.imports == imported.imports
    assert export_csv(changed, ExportOptions()) == before


def calendar_plan():
    person = Person(name="Alex")
    calendar = WorkCalendar(
        name="Six-hour week", weekday_hours=(Decimal("1.2"),) * 5 + (Decimal(0),) * 2
    )
    item = WorkItem(title="Imported", kind=WorkItemType.TASK)
    baseline = ImportSnapshot(
        name="Jira",
        headers=("Summary",),
        rows=((item.title,),),
        records=(ImportedWork(item=item, external_reference="LAB-1", person=person),),
    )
    plan = ProgramPlan(
        name="Calendars",
        horizon=PlanningHorizon(date(2026, 9, 28), date(2026, 10, 4)),
        people=(person,),
        work_items=(item,),
        imports=(baseline,),
    )
    return assign_calendar(add_calendar(plan, calendar), person.id, calendar.id)


def test_lifecycle_preserves_ids_source_snapshots_and_rejects_dangling_references():
    plan = calendar_plan()
    person, calendar = plan.people[0], plan.work_calendars[0]
    assert assign_calendar(plan, person.id, calendar.id) == plan
    updated = update_calendar(
        plan, replace(calendar, name="Renamed", weekday_hours=(Decimal("3.125"),) * 7)
    )
    assert updated.work_calendars[0].id == calendar.id
    assert updated.person_calendars == plan.person_calendars
    assert updated.imports is plan.imports
    with pytest.raises(ValueError, match="Confirm"):
        remove_calendar(plan, calendar.id)
    cleared = remove_calendar(plan, calendar.id, unassign=True)
    assert cleared.work_calendars == cleared.person_calendars == ()
    assert cleared.imports is plan.imports
    assert assign_calendar(plan, person.id, None).person_calendars == ()
    removed = remove_person(plan, person.id)
    assert removed.person_calendars == ()
    assert removed.imports[0].records[0].person == person
    assert removed.work_calendars == plan.work_calendars
    for person_id, calendar_id in ((uuid4(), calendar.id), (person.id, uuid4())):
        with pytest.raises(ValueError, match="does not exist"):
            assign_calendar(plan, person_id, calendar_id)
    with pytest.raises(ValueError, match="unique"):
        add_calendar(plan, calendar)
    with pytest.raises(ValueError, match="only one"):
        replace(plan, person_calendars=plan.person_calendars * 2)


def test_sqlite_and_json_roundtrip_keep_exact_hours_and_calendar_identity(tmp_path):
    plan = calendar_plan()
    calendar = replace(
        plan.work_calendars[0], weekday_hours=(Decimal("1.12345678901234567890123456789"),) * 7
    )
    plan = update_calendar(plan, calendar)
    assert loads(dumps(plan)) == plan
    path = tmp_path / "calendar.planacity"
    save_project(plan, path)
    assert load_project(path) == plan
    assert (
        load_project(path).work_calendars[0].weekday_hours[0].as_tuple()
        == calendar.weekday_hours[0].as_tuple()
    )


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_schema_migrates_without_inventing_calendars(version, tmp_path):
    original = calendar_plan()
    plan = replace(
        original,
        work_calendars=(),
        person_calendars=(),
        imports=() if version == 1 else original.imports,
    )
    data = json.loads(dumps(plan))
    data["schema_version"] = version
    strip_work_context(data)
    data["plan"].pop("work_calendars")
    data["plan"].pop("person_calendars")
    data["plan"].pop("availability_events")
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    data["plan"].pop("allocations")
    if version == 1:
        data["plan"].pop("imports")
    payload = json.dumps(data)
    assert loads(payload) == plan
    path = tmp_path / "legacy.planacity"
    with sqlite3.connect(path) as connection:
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
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["work_calendars"][0]["weekday_hours"].__setitem__(0, 1.2),
        lambda p: p["work_calendars"][0]["weekday_hours"].__setitem__(0, "NaN"),
        lambda p: p["work_calendars"][0]["weekday_hours"].pop(),
        lambda p: p["work_calendars"].append(p["work_calendars"][0]),
        lambda p: p["person_calendars"][0].update(calendar_id=str(uuid4())),
        lambda p: p["person_calendars"][0].update(person_id=str(uuid4())),
        lambda p: p["person_calendars"].append(p["person_calendars"][0]),
        lambda p: p.pop("work_calendars"),
    ],
)
def test_malformed_calendar_payloads_are_rejected(mutation):
    data = json.loads(dumps(calendar_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError):
        loads(json.dumps(data))
