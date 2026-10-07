"""Data integrity across mapping, imports, edits, persistence, and export."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from persistence_helpers import strip_work_context

from planacity.domain import Person, PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.integrations.jira.csv_io import Mapping, preview_import, read_csv
from planacity.integrations.jira.export import ExportOptions, export_csv
from planacity.integrations.jira.profiles import dump_profile, load_profile
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import load_project, save_project
from planacity.planning.changes import work_changes

CSV = (
    "Issue key,Summary,Issue Type,Parent,Original Estimate,Assignee,Status,Custom,Custom\n"
    'A-2,"Task, with commas",Task,A-1,3601,Alice,Open,one,two\n'
    'A-1,"Epic\nmultiline",Epic,,,Alice,Open,three,four\n'
)
MAPPING = Mapping(
    (
        ("reference", 0),
        ("title", 1),
        ("type", 2),
        ("parent", 3),
        ("estimate", 4),
        ("person", 5),
        ("status", 6),
    )
)


@pytest.fixture
def plan():
    return ProgramPlan(name="Test", horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 12, 31)))


def imported(plan):
    return preview_import(plan, read_csv(CSV), MAPPING, {"Alice": Person(name="Alice")}, "test.csv")


def test_roundtrip_preserves_baseline_and_unmapped_cells(plan, tmp_path):
    result = imported(plan)
    assert not plan.work_items and not plan.imports
    assert result.work_items[0].parent_id == result.work_items[1].id
    assert result.imports[0].rows[0][-2:] == ("one", "two")
    assert result.imports[0].records[0].person == result.people[0]
    baseline = result.imports
    changed = replace(
        result, work_items=(replace(result.work_items[0], title="Agreed"), result.work_items[1])
    )
    path = tmp_path / "plan.planacity"
    save_project(changed, path)
    reopened = load_project(path)
    assert reopened == changed == loads(dumps(changed))
    assert reopened.imports == baseline
    changes = work_changes(reopened)
    assert len(changes) == 1 and changes[0].fields == ("title",)
    output = read_csv(export_csv(reopened))
    assert output.rows[0][0] == "A-1"
    assert output.rows[1][4] == output.rows[0][1]
    assert output.rows[1][5] == "3601"
    assert output.rows[1][3] == "Agreed"
    assert reopened.imports == baseline


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "headers"),
        ("a,b\n1\n", "expected 2"),
        ('a,b\n"unclosed,b', "CSV line"),
        ("a,b\n", "no work"),
        ("a,b\n\n", "expected 2"),
    ],
)
def test_malformed_csv_is_actionable(text, message):
    with pytest.raises(ValueError, match=message):
        read_csv(text)


@pytest.mark.parametrize(
    "old,new,message",
    [
        ("A-2,", "A-1,", "unique"),
        ("Task,A-1", "Task,UNKNOWN", "Parent"),
        ("3601", "NaN", "finite"),
        ("3601", "-1", "non-negative"),
        ("3601", "1h", "CSV row 2"),
        ("Task,A-1", "Story,A-1", "Map work type"),
        ("Epic,,,", "Sub-task,,,", r"CSV row 3 \(A-1\): .*requires a Task"),
        ("Epic,,,", "Task,,,", r"CSV row 2 \(A-2\): .*requires an Epic"),
    ],
)
def test_invalid_mapping_rows_never_modify_plan(plan, old, new, message):
    with pytest.raises(ValueError, match=message):
        preview_import(
            plan,
            read_csv(CSV.replace(old, new)),
            MAPPING,
            {"Alice": Person(name="Alice")},
            "bad.csv",
        )
    assert not plan.work_items and not plan.imports and not plan.people


def test_people_must_be_explicit_and_reimport_cannot_replace_baseline(plan):
    with pytest.raises(ValueError, match="Map these external people"):
        preview_import(plan, read_csv(CSV), MAPPING, {}, "test.csv")
    result = imported(plan)
    with pytest.raises(ValueError, match="already imported"):
        preview_import(result, read_csv(CSV), MAPPING, {"Alice": result.people[0]}, "test.csv")
    assert not work_changes(result)


def test_changes_include_added_and_removed_and_remain_computed(plan):
    result = imported(plan)
    new = WorkItem(title="New", kind=WorkItemType.TASK)
    changed = replace(result, work_items=(result.work_items[1], new))
    assert [c.kind for c in work_changes(changed)] == ["Removed", "Added"]
    assert not work_changes(result)


def test_numeric_parent_ids_explicit_hours_and_dates(plan):
    table = read_csv(
        "Ref;ID;Name;Type;Parent;Hours;Date\nA-2;2;Task;Task;1;1.25;31/01/2026\n"
        "A-1;1;Epic;Epic;;;\n",
        ";",
    )
    mapping = Mapping(
        (
            ("reference", 0),
            ("row_id", 1),
            ("title", 2),
            ("type", 3),
            ("parent", 4),
            ("estimate", 5),
            ("end", 6),
        ),
        "hours",
        "%d/%m/%Y",
    )
    result = preview_import(plan, table, mapping, {}, "numeric.csv")
    assert result.work_items[0].estimate_hours == Decimal("1.25")
    assert result.work_items[0].end == date(2026, 1, 31)
    profile = dump_profile(table.headers, mapping)
    assert load_profile(profile, table.headers) == mapping
    with pytest.raises(ValueError, match="columns differ"):
        load_profile(profile, tuple(reversed(table.headers)))
    assert "31/01/2026" not in profile


def test_v1_migration_and_strict_baseline_validation(plan):
    data = json.loads(dumps(plan))
    data["schema_version"] = 1
    strip_work_context(data)
    data["plan"].pop("imports")
    data["plan"].pop("work_calendars")
    data["plan"].pop("person_calendars")
    data["plan"].pop("availability_events")
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    data["plan"].pop("allocations")
    assert loads(json.dumps(data)) == plan
    data = json.loads(dumps(imported(plan)))
    data["plan"]["imports"][0]["records"][0]["unexpected"] = "keep me"
    with pytest.raises(ValueError, match="exactly these fields"):
        loads(json.dumps(data))


def test_configurable_export_preserves_unicode_and_quotes(plan):
    item = WorkItem(
        title='Rubén "test"\nsecond line', kind=WorkItemType.TASK, estimate_hours=Decimal("1.25")
    )
    result = replace(plan, work_items=(item,))
    table = read_csv(export_csv(result, ExportOptions(estimate_unit="hours", delimiter=";")), ";")
    assert table.rows[0][3] == item.title
    assert table.rows[0][5] == "1.25"
    assert table.rows[0][0] == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("columns", [1]),
        ("columns", [["title", True]]),
        ("columns", [["title", -1]]),
        ("types", [[3, "task"]]),
        ("types", [["Task", "unknown"]]),
        ("version", True),
    ],
)
def test_malformed_profile_is_actionable(field, value):
    table = read_csv(CSV)
    data = json.loads(dump_profile(table.headers, MAPPING))
    data[field] = value
    with pytest.raises(ValueError, match="Cannot load mapping profile"):
        load_profile(json.dumps(data), table.headers)


@pytest.mark.parametrize(
    "duplicate,field",
    [
        ('"estimate_unit": "hours"', "estimate_unit"),
        ('"version": 1', "version"),
        ('"columns": [["title", 0], ["type", 1], ["reference", 2]]', "columns"),
        ('"estimate_\\u0075nit": "hours"', "estimate_unit"),
    ],
)
def test_duplicate_profile_fields_are_rejected(duplicate, field):
    table = read_csv(CSV)
    profile = dump_profile(table.headers, MAPPING)
    ambiguous = profile[:-1] + ", " + duplicate + "}"
    with pytest.raises(ValueError, match=f"Duplicate mapping profile field: {field}"):
        load_profile(ambiguous, table.headers)


def test_real_v1_project_upgrade_preserves_data(plan, tmp_path):
    import sqlite3

    from planacity.persistence.project import APPLICATION_ID

    path = tmp_path / "old.planacity"
    data = json.loads(dumps(plan))
    data["schema_version"] = 1
    strip_work_context(data)
    data["plan"].pop("imports")
    data["plan"].pop("work_calendars")
    data["plan"].pop("person_calendars")
    data["plan"].pop("availability_events")
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    data["plan"].pop("allocations")
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (json.dumps(data),))
    connection.close()
    assert load_project(path) == plan
    updated = imported(load_project(path))
    save_project(updated, path)
    assert load_project(path) == updated
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
    connection.close()
