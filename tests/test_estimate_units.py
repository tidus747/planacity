"""Explicit calendar equivalents preserve precise hours and external baselines."""

import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import uuid4

import pytest

from planacity.domain import PlanningHorizon, ProgramPlan, WorkCalendar, WorkItem, WorkItemType
from planacity.domain.estimate_units import EstimatePreferences, EstimateUnit
from planacity.integrations.jira.csv_io import preview_import, read_csv
from planacity.integrations.jira.export import ExportOptions, export_csv
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.calendar_settings import remove_calendar, update_calendar
from planacity.planning.changes import work_changes
from planacity.planning.estimate_units import (
    estimate_text,
    hours_per_unit,
    parse_estimate,
    set_estimate_preferences,
)


def unit_plan(hours=("6", "6", "6", "6", "3", "0", "0")):
    calendar = WorkCalendar(name="Reference week", weekday_hours=tuple(Decimal(v) for v in hours))
    return ProgramPlan(
        name="Unit checks",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 12, 31)),
        work_calendars=(calendar,),
        work_items=(WorkItem(title="Build", kind=WorkItemType.TASK, estimate_hours=Decimal("27")),),
    )


@pytest.mark.parametrize(
    "unit,factor,text",
    [
        (EstimateUnit.HOURS, Fraction(1), "27"),
        (EstimateUnit.DAYS, Fraction(27, 5), "5"),
        (EstimateUnit.WEEKS, Fraction(27), "1"),
    ],
)
def test_variable_calendar_conversion_and_preference_do_not_change_hours(unit, factor, text):
    original = unit_plan()
    plan = set_estimate_preferences(original, unit, original.work_calendars[0].id)
    assert hours_per_unit(plan) == factor
    assert estimate_text(plan, Decimal(27)) == text
    assert parse_estimate(plan, text) == 27
    assert parse_estimate(plan, "0") == 0
    assert parse_estimate(plan, " ") is None
    assert parse_estimate(plan, "1.250 h") == Decimal("1.250")
    assert plan.work_items is original.work_items
    assert plan.imports is original.imports


def test_weekend_calendar_and_fractional_precision_ignore_decimal_context():
    plan = unit_plan(("0", "0", "0", "0", "0", "4.125", "4.125"))
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, plan.work_calendars[0].id)
    with localcontext() as context:
        context.prec = 3
        assert hours_per_unit(plan) == Fraction(33, 8)
        assert parse_estimate(plan, "0.12345678901234567890123456789") == Decimal(
            "0.50925925467592592546759259254625"
        )
        hours = Decimal("0.000000000000000000000000000033")
        assert parse_estimate(plan, estimate_text(plan, hours, editing=True)) == hours


def test_repeating_display_uses_exact_hours_when_editing_and_rejects_lossy_entry():
    plan = unit_plan(("7", "7", "8", "0", "0", "0", "0"))
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, plan.work_calendars[0].id)
    assert hours_per_unit(plan) == Fraction(22, 3)
    assert estimate_text(plan, Decimal(1)).startswith("~")
    assert estimate_text(plan, Decimal("1.00"), editing=True) == "1.00 h"
    assert parse_estimate(plan, "1.00 h").as_tuple() == Decimal("1.00").as_tuple()
    with pytest.raises(ValueError, match="repeating hour decimals"):
        parse_estimate(plan, "1")
    assert parse_estimate(plan, "3") == 22


@pytest.mark.parametrize("value", ["-1", "NaN", "sNaN", "Infinity", "-Infinity", "oops", "1 d"])
def test_invalid_estimates_are_actionable(value):
    with pytest.raises(ValueError):
        parse_estimate(unit_plan(), value)


def test_missing_invalid_and_zero_calendars_are_rejected():
    plan = unit_plan()
    with pytest.raises(ValueError, match="Choose a work calendar"):
        set_estimate_preferences(plan, EstimateUnit.DAYS)
    with pytest.raises(ValueError, match="missing calendar"):
        set_estimate_preferences(plan, EstimateUnit.WEEKS, uuid4())
    zero = unit_plan(("0",) * 7)
    with pytest.raises(ValueError, match="positive working hours"):
        set_estimate_preferences(zero, EstimateUnit.DAYS, zero.work_calendars[0].id)
    with pytest.raises(ValueError):
        EstimatePreferences(unit="days")
    with pytest.raises(ValueError):
        EstimatePreferences(calendar_id="bad")
    with pytest.raises(ValueError):
        replace(plan, estimate_preferences={})


def test_reference_calendar_lifecycle_preserves_hours():
    original = unit_plan()
    calendar = original.work_calendars[0]
    plan = set_estimate_preferences(original, EstimateUnit.WEEKS, calendar.id)
    with pytest.raises(ValueError, match="switch to Hours"):
        remove_calendar(plan, calendar.id)
    with pytest.raises(ValueError, match="positive working hours"):
        update_calendar(plan, replace(calendar, weekday_hours=(Decimal(0),) * 7))
    changed = update_calendar(plan, replace(calendar, weekday_hours=(Decimal(3),) * 7))
    assert hours_per_unit(changed) == 21
    assert changed.work_items is original.work_items
    cleared = set_estimate_preferences(plan, EstimateUnit.HOURS)
    assert not remove_calendar(cleared, calendar.id).work_calendars


@pytest.mark.parametrize("unit", list(EstimateUnit))
def test_preferences_and_precise_estimate_persist(unit, tmp_path):
    plan = unit_plan()
    plan = replace(
        plan,
        work_items=(
            replace(
                plan.work_items[0],
                estimate_hours=Decimal("123.456789012345678901234567890123456789"),
            ),
        ),
    )
    plan = set_estimate_preferences(plan, unit, plan.work_calendars[0].id)
    assert loads(dumps(plan)) == plan
    path = tmp_path / "units.planacity"
    save_project(plan, path)
    reopened = load_project(path)
    assert reopened == plan
    assert (
        reopened.work_items[0].estimate_hours.as_tuple()
        == plan.work_items[0].estimate_hours.as_tuple()
    )


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5])
def test_legacy_files_open_in_hours_without_inventing_conversions(version, tmp_path):
    plan = unit_plan()
    if version < 3:
        plan = replace(plan, work_calendars=())
    data = json.loads(dumps(plan))
    data["schema_version"] = version
    for key, introduced in (
        ("imports", 2),
        ("work_calendars", 3),
        ("person_calendars", 3),
        ("availability_events", 4),
        ("reservation_rules", 5),
        ("estimate_preferences", 6),
        ("allocations", 7),
    ):
        if version < introduced:
            data["plan"].pop(key)
    assert loads(json.dumps(data)) == plan
    path = tmp_path / "legacy.planacity"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={version}")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (json.dumps(data),))
    connection.close()
    before = path.read_bytes()
    assert load_project(path) == plan
    assert path.read_bytes() == before
    save_project(plan, path)
    assert load_project(path) == plan
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
    connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.pop("estimate_preferences"),
        lambda p: p["estimate_preferences"].update(unit="months"),
        lambda p: p["estimate_preferences"].update(unit="days", calendar_id=None),
        lambda p: p["estimate_preferences"].update(calendar_id=str(uuid4())),
        lambda p: p["estimate_preferences"].update(calendar_id=42),
        lambda p: p["estimate_preferences"].update(extra=True),
    ],
)
def test_invalid_saved_preferences_are_rejected(mutation):
    data = json.loads(dumps(unit_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError):
        loads(json.dumps(data))


def test_jira_import_export_units_and_baselines_are_independent():
    from test_jira_csv import CSV, MAPPING

    from planacity.domain import Person

    plan = unit_plan()
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, plan.work_calendars[0].id)
    imported = preview_import(
        plan,
        read_csv(CSV.replace("3601", "5400")),
        MAPPING,
        {"Alice": Person(name="Alice")},
        "jira.csv",
    )
    assert imported.estimate_preferences == plan.estimate_preferences
    task = next(i for i in imported.work_items if i.title == "Task, with commas")
    assert task.estimate_hours == Decimal("1.5")
    changed = set_estimate_preferences(imported, EstimateUnit.WEEKS, plan.work_calendars[0].id)
    assert changed.imports is imported.imports
    assert changed.work_items is imported.work_items
    assert work_changes(changed) == work_changes(imported)
    restored = loads(dumps(changed))
    assert restored == changed
    for unit in ("seconds", "hours"):
        assert export_csv(restored, ExportOptions(estimate_unit=unit)) == export_csv(
            imported, ExportOptions(estimate_unit=unit)
        )
