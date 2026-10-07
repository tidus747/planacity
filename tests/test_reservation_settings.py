"""Reservation storage, candidate edits, roster lifecycle, and schema upgrades."""

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from persistence_helpers import strip_work_context
from test_availability_settings import availability_plan
from test_reservations import capacity

from planacity.domain import Person, ReservationRule
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.people import remove_person
from planacity.planning.reservation_settings import (
    add_reservation,
    preview_reservations,
    remove_reservation,
    update_reservation,
)


def reservation_plan():
    plan = availability_plan()
    person = plan.people[0]
    shared_person = Person(name="Morgan")
    plan = replace(plan, people=(*plan.people, shared_person))
    meetings = ReservationRule(
        name="Meetings",
        person_ids=(person.id, shared_person.id),
        hours_per_person=Decimal("1.123456789012345678901234567890"),
        anchor=plan.horizon.start,
        interval_weeks=1,
        effective=plan.horizon,
    )
    support = replace(
        meetings, id=uuid4(), name="Support", person_ids=(person.id,), hours_per_person=Decimal(2)
    )
    return add_reservation(add_reservation(plan, meetings), support)


def inputs(plan):
    return tuple(capacity(person=p.id, period=plan.horizon) for p in plan.people)


def test_roundtrip_preserves_rules_exact_hours_and_calculation(tmp_path):
    plan = reservation_plan()
    path = tmp_path / "rules.planacity"
    save_project(plan, path)
    reopened = load_project(path)
    assert reopened == loads(dumps(plan)) == plan
    assert reopened.reservation_rules[0].hours_per_person.as_tuple() == (
        plan.reservation_rules[0].hours_per_person.as_tuple()
    )
    assert preview_reservations(reopened, inputs(plan)) == preview_reservations(plan, inputs(plan))
    assert '"occurrences"' not in dumps(plan)


def test_edit_preview_cancel_and_delete_do_not_duplicate_or_mutate_rules():
    plan = reservation_plan()
    original = dumps(plan)
    first, second = plan.reservation_rules
    candidate = update_reservation(plan, replace(first, hours_per_person=Decimal(3)))
    assert len(candidate.reservation_rules) == 2
    assert candidate.reservation_rules[0].id == first.id
    preview = preview_reservations(candidate, inputs(plan))
    assert next(r for r in preview if r.person_id == plan.people[0].id).reserved_hours == 5
    assert preview_reservations(candidate, inputs(plan)) == preview
    assert dumps(plan) == original  # Cancelling simply discards this candidate.
    remaining = remove_reservation(candidate, first.id)
    assert remaining.reservation_rules == (second,)
    result = preview_reservations(remaining, inputs(plan))
    assert next(r for r in result if r.person_id == plan.people[0].id).reserved_hours == 2
    assert next(r for r in result if r.person_id == plan.people[1].id).reserved_hours == 0
    with pytest.raises(ValueError):
        preview_reservations(candidate, ())
    assert dumps(plan) == original
    with pytest.raises(ValueError, match="unique"):
        add_reservation(plan, first)
    with pytest.raises(ValueError, match="does not exist"):
        update_reservation(plan, replace(first, id=uuid4()))
    with pytest.raises(ValueError, match="does not exist"):
        remove_reservation(plan, uuid4())
    with pytest.raises(ValueError, match="does not exist"):
        update_reservation(plan, replace(first, person_ids=(uuid4(),)))


def test_person_removal_requires_explicit_resolution_and_retains_other_people():
    plan = reservation_plan()
    person, other = plan.people
    with pytest.raises(ValueError, match="reservation"):
        remove_person(plan, person.id, remove_availability=True)
    with pytest.raises(ValueError, match="availability"):
        remove_person(plan, person.id, remove_reservations=True)
    removed = remove_person(plan, person.id, remove_availability=True, remove_reservations=True)
    assert removed.people == (other,)
    assert removed.availability_events == removed.person_calendars == ()
    assert removed.reservation_rules == (
        replace(plan.reservation_rules[0], person_ids=(other.id,)),
    )
    assert removed.imports == plan.imports
    assert removed.work_calendars == plan.work_calendars
    assert len(plan.reservation_rules) == 2


def test_jira_import_export_and_calendar_clear_preserve_rules():
    from test_jira_csv import CSV, MAPPING

    from planacity.integrations.jira.csv_io import preview_import, read_csv
    from planacity.integrations.jira.export import ExportOptions, export_csv
    from planacity.planning.calendar_settings import assign_calendar, remove_calendar

    plan = reservation_plan()
    imported = preview_import(plan, read_csv(CSV), MAPPING, {"Alice": plan.people[0]}, "more.csv")
    assert imported.reservation_rules == plan.reservation_rules
    changed = remove_reservation(imported, plan.reservation_rules[0].id)
    assert changed.imports == imported.imports
    assert export_csv(changed, ExportOptions()) == export_csv(imported, ExportOptions())
    assert (
        assign_calendar(plan, plan.people[0].id, None).reservation_rules == plan.reservation_rules
    )
    assert (
        remove_calendar(plan, plan.work_calendars[0].id, unassign=True).reservation_rules
        == plan.reservation_rules
    )


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_older_schemas_open_without_rules_and_upgrade_on_save(version, tmp_path):
    plan = replace(reservation_plan(), reservation_rules=())
    if version < 4:
        plan = replace(plan, availability_events=())
    if version < 3:
        plan = replace(plan, work_calendars=(), person_calendars=())
    if version < 2:
        plan = replace(plan, imports=())
    data = json.loads(dumps(plan))
    data["schema_version"] = version
    strip_work_context(data)
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    data["plan"].pop("allocations")
    if version < 4:
        data["plan"].pop("availability_events")
    if version < 3:
        data["plan"].pop("work_calendars")
        data["plan"].pop("person_calendars")
    if version < 2:
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
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["reservation_rules"][0].update(person_ids=[str(uuid4())]),
        lambda p: p["reservation_rules"][0].update(person_ids=[]),
        lambda p: p["reservation_rules"][0].update(hours_per_person=1.5),
        lambda p: p["reservation_rules"][0].update(hours_per_person="NaN"),
        lambda p: p["reservation_rules"][0].update(hours_per_person="0"),
        lambda p: p["reservation_rules"][0].update(interval_weeks=True),
        lambda p: p["reservation_rules"][0].update(interval_weeks=1.5),
        lambda p: p["reservation_rules"][0].update(interval_weeks=0),
        lambda p: p["reservation_rules"][0].update(anchor="bad"),
        lambda p: p["reservation_rules"][0]["effective"].update(end="2020-01-01"),
        lambda p: p["reservation_rules"].append(p["reservation_rules"][0]),
        lambda p: p.pop("reservation_rules"),
    ],
)
def test_malformed_rules_are_rejected(mutation):
    data = json.loads(dumps(reservation_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError):
        loads(json.dumps(data))


def test_roster_confirmation_cancel_and_accept(app, window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    plan = reservation_plan()
    window.session.apply(plan)
    page = window.people_page
    page.table.setCurrentIndex(page.model.index(0, 0))
    try:

        def cancel(*args):
            assert "Meetings" in args[2] and "Support" in args[2]
            assert "no remaining people" in args[2]
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", cancel)
        page.edit("remove")
        assert window.session.document.plan is plan
        monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
        page.edit("remove")
        assert window.session.document.plan == remove_person(
            plan, plan.people[0].id, remove_availability=True, remove_reservations=True
        )
    finally:
        window.session.document.saved_plan = window.session.document.plan
