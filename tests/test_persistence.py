"""Real files, complete round trips, and failed writes protect the current plan."""

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from persistence_helpers import strip_work_context, strip_work_priority

from planacity.document import Document
from planacity.domain import WorkGroup, WorkPriority
from planacity.domain.models import ImportedWork, ImportSnapshot
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import export_backup, load_project, restore_backup, save_project


@pytest.fixture
def plan():
    example = Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    return replace(restore_backup(example), name="  Aur\u00f3ra \u2192 validation  ")


def test_complete_example_sqlite_and_backup_round_trip(plan, tmp_path):
    project, backup = tmp_path / "program.planacity", tmp_path / "backup.json"
    save_project(plan, project)
    assert load_project(project) == plan
    export_backup(plan, backup)
    assert restore_backup(backup) == plan
    assert loads(dumps(plan)) == plan
    assert plan.work_items[3].estimate_hours == Decimal("4.25")
    assert plan.work_items[-1].estimate_hours is None
    changed = replace(plan, description="Continue after reopening")
    save_project(changed, project)
    assert load_project(project) == changed
    assert restore_backup(backup) == plan


def test_schema_nine_preserves_context_and_priority_in_current_and_imported_work(plan, tmp_path):
    group = WorkGroup(name="Reporting")
    current = replace(
        plan.work_items[0],
        description="Primary integration topic\nOwner notes stay local.",
        labels=("firmware", "Customer-A"),
        primary_group_id=group.id,
        priority=WorkPriority.HIGHEST,
    )
    baseline = replace(
        current,
        description="Imported source description",
        labels=("source-label",),
        primary_group_id=None,
        priority=WorkPriority.LOW,
    )
    source = ImportSnapshot(
        name="source.csv",
        headers=("Key", "Summary"),
        rows=(("CTX-1", baseline.title),),
        records=(ImportedWork(item=baseline, external_reference="CTX-1"),),
    )
    contextual = replace(
        plan,
        work_items=(current, *plan.work_items[1:]),
        work_groups=(*plan.work_groups, group),
        imports=(source,),
    )
    data = json.loads(dumps(contextual))

    assert data["schema_version"] == 9
    assert data["plan"]["work_items"][0]["description"] == current.description
    assert data["plan"]["work_items"][0]["labels"] == list(current.labels)
    assert data["plan"]["work_items"][0]["primary_group_id"] == str(group.id)
    assert data["plan"]["work_items"][0]["priority"] == "highest"
    baseline_data = data["plan"]["imports"][0]["records"][0]["item"]
    assert baseline_data["description"] == baseline.description
    assert baseline_data["labels"] == list(baseline.labels)
    assert baseline_data["priority"] == "low"
    assert loads(json.dumps(data)) == contextual

    path = tmp_path / "context.planacity"
    save_project(contextual, path)
    assert load_project(path) == contextual


@pytest.mark.parametrize("priority", [None, *WorkPriority])
def test_every_priority_level_round_trips_through_project_and_backup(plan, tmp_path, priority):
    prioritized = replace(
        plan,
        work_items=(replace(plan.work_items[0], priority=priority), *plan.work_items[1:]),
    )
    project = tmp_path / "priority.planacity"
    backup = tmp_path / "priority.json"

    save_project(prioritized, project)
    export_backup(prioritized, backup)

    assert load_project(project).work_items[0].priority == priority
    assert restore_backup(backup).work_items[0].priority == priority


@pytest.mark.parametrize("version", range(1, 9))
def test_schemas_one_to_eight_load_priority_as_unset(plan, version):
    data = json.loads(dumps(plan))
    data["schema_version"] = version
    if version < 8:
        strip_work_context(data)
    else:
        strip_work_priority(data)
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
    loaded = loads(json.dumps(data))
    assert all(item.description == "" for item in loaded.work_items)
    assert all(item.labels == () for item in loaded.work_items)
    assert all(item.primary_group_id is None for item in loaded.work_items)
    assert all(item.priority is None for item in loaded.work_items)
    assert all(
        record.item.priority is None for source in loaded.imports for record in source.records
    )


def test_empty_and_incomplete_plan_round_trip(plan, tmp_path):
    plan = replace(plan, people=(), work_items=(), work_groups=(), relationships=())
    path = tmp_path / "empty.planacity"
    save_project(plan, path)
    assert load_project(path) == plan


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema_version=99),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(format="foreign"),
        lambda d: d.update(unknown="data"),
        lambda d: d["plan"].update(unknown="data"),
        lambda d: d["plan"].pop("people"),
        lambda d: d["plan"]["work_items"][0].update(unknown=1),
        lambda d: d["plan"]["work_items"][1].update(estimate_hours=1.5),
        lambda d: d["plan"]["work_items"][1].update(estimate_hours="NaN"),
        lambda d: d["plan"]["work_items"][1].update(description=1),
        lambda d: d["plan"]["work_items"][1].update(labels="firmware"),
        lambda d: d["plan"]["work_items"][1].update(labels=["firmware", "Firmware"]),
        lambda d: d["plan"]["work_items"][1].update(primary_group_id=str(uuid4())),
        lambda d: d["plan"]["work_items"][1].update(priority="urgent"),
        lambda d: d["plan"]["work_items"][1].update(
            parent_id="00000000-0000-0000-0000-000000000000"
        ),
        lambda d: d["plan"]["people"].append(d["plan"]["people"][0]),
        lambda d: d["plan"]["relationships"][0].update(target_id="not-a-uuid"),
        lambda d: d["plan"]["horizon"].update(start="2026-10-01T12:00:00"),
    ],
)
def test_malformed_or_newer_backup_is_rejected_without_partial_loading(plan, change):
    data = json.loads(dumps(plan))
    change(data)
    with pytest.raises(ValueError, match="Cannot read plan"):
        loads(json.dumps(data))


@pytest.mark.parametrize("data", ["{", '{"format":"planacity","format":"other"}', "NaN", "[]"])
def test_invalid_json_or_duplicate_fields(data):
    with pytest.raises(ValueError):
        loads(data)


@pytest.mark.parametrize(
    "kind", ["foreign", "corrupt", "newer", "extra", "extra_row", "bad_payload"]
)
def test_bad_sqlite_is_not_opened_or_overwritten(plan, tmp_path, kind):
    path = tmp_path / "bad.planacity"
    if kind == "corrupt":
        path.write_bytes(b"not a database")
    elif kind == "foreign":
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE important (data TEXT)")
        connection.close()
    else:
        save_project(plan, path)
        connection = sqlite3.connect(path)
        with connection:
            if kind == "newer":
                connection.execute("PRAGMA user_version=99")
            elif kind == "extra":
                connection.execute("CREATE TABLE extra (data TEXT)")
            elif kind == "extra_row":
                connection.execute("DELETE FROM document")
            else:
                connection.execute("UPDATE document SET payload='{}'")
        connection.close()
    before = path.read_bytes()
    with pytest.raises(ValueError):
        load_project(path)
    with pytest.raises(ValueError):
        save_project(plan, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(("container_version", "payload_version"), [(1, 2), (2, 1)])
def test_mismatched_project_and_payload_versions_are_not_opened_or_overwritten(
    plan, tmp_path, container_version, payload_version
):
    path = tmp_path / "mismatched.planacity"
    save_project(plan, path)
    data = json.loads(dumps(plan))
    data["schema_version"] = payload_version
    strip_work_context(data)
    data["plan"].pop("work_calendars")
    data["plan"].pop("person_calendars")
    data["plan"].pop("availability_events")
    data["plan"].pop("reservation_rules")
    data["plan"].pop("estimate_preferences")
    data["plan"].pop("allocations")
    if payload_version == 1:
        data["schema_version"] = 1
        data["plan"].pop("imports")
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version={container_version}")
        connection.execute("UPDATE document SET payload=?", (json.dumps(data),))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="does not match"):
        load_project(path)
    with pytest.raises(ValueError, match="does not match"):
        save_project(plan, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("backup", [False, True])
def test_failed_replace_preserves_previous_file_and_cleans_temporary(
    plan, tmp_path, monkeypatch, backup
):
    path = tmp_path / ("plan.json" if backup else "plan.planacity")
    save = export_backup if backup else save_project
    save(plan, path)
    before = path.read_bytes()

    def fail(*args):
        raise PermissionError("File is locked")

    monkeypatch.setattr("planacity.persistence.project.os.replace", fail)
    with pytest.raises(PermissionError):
        save(replace(plan, name="Changed"), path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_missing_open_never_creates_a_database(tmp_path):
    path = tmp_path / "missing.planacity"
    with pytest.raises(ValueError):
        load_project(path)
    assert not path.exists()


def test_document_lifecycle_and_failed_operations(plan, tmp_path):
    document = Document()
    document.new(plan)
    assert document.dirty and document.path is None
    path = tmp_path / "plan.planacity"
    document.save(path)
    assert not document.dirty
    changed = replace(plan, description="New draft")
    document.plan = changed
    assert document.dirty
    with pytest.raises((OSError, ValueError)):
        document.save(tmp_path / "missing-folder" / "plan.planacity")
    assert document.plan == changed and document.dirty and document.path == path
    with pytest.raises(ValueError):
        document.open(tmp_path / "missing.planacity")
    assert document.plan == changed and document.dirty
    backup = tmp_path / "backup.json"
    backup.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        document.restore(backup)
    assert document.plan == changed and document.path == path
    export_backup(plan, backup)
    document.restore(backup)
    assert document.plan == plan and document.path is None and document.dirty
    document.open(path)
    assert document.plan == plan and document.path == path and not document.dirty


def test_failed_sqlite_transaction_preserves_previous_project(plan, tmp_path, monkeypatch):
    path = tmp_path / "program.planacity"
    save_project(plan, path)
    before = path.read_bytes()
    connect = sqlite3.connect

    class FailedInsert(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("INSERT"):
                raise sqlite3.OperationalError("Simulated write failure")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(
        "planacity.persistence.project.sqlite3.connect",
        lambda *args, **kwargs: connect(*args, **kwargs, factory=FailedInsert),
    )
    with pytest.raises(sqlite3.OperationalError):
        save_project(replace(plan, name="Changed"), path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
