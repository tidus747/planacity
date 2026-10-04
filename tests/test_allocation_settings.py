"""Saved allocations, migration, deletion consent, and immutable Jira baselines."""

import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    Person,
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
)
from planacity.integrations.jira.csv_io import preview_import, read_csv
from planacity.integrations.jira.export import ExportOptions, export_csv
from planacity.persistence.codec import dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.allocation_settings import (
    add_allocation,
    remove_allocation,
    update_allocation,
)
from planacity.planning.allocations import summarize_allocations
from planacity.planning.people import remove_person, rename_person
from planacity.planning.work_items import (
    add_work_item,
    move_work_item,
    remove_work_item,
    resolve_container_effort,
)


def allocated_plan():
    epic = WorkItem(title="Program", kind=WorkItemType.EPIC)
    task = WorkItem(
        title="Integration", kind=WorkItemType.TASK, parent_id=epic.id, estimate_hours=Decimal(100)
    )
    other = WorkItem(title="Follow-up", kind=WorkItemType.TASK)
    people = tuple(Person(name=name) for name in ("Alex", "Sam", "Robin"))
    return ProgramPlan(
        name="Shared work",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 12, 31)),
        work_items=(epic, task, other),
        people=people,
        allocations=tuple(
            Allocation(work_item_id=task.id, person_id=person.id, hours=Decimal(hours))
            for person, hours in zip(people[:2], ("60", "40"), strict=True)
        ),
    )


def test_lifecycle_preserves_ids_order_and_unrelated_data():
    plan = allocated_plan()
    first, second = plan.allocations
    changed = update_allocation(plan, replace(first, hours=Decimal("70.125")))
    assert changed.allocations == (replace(first, hours=Decimal("70.125")), second)
    assert changed.work_items is plan.work_items
    third = Allocation(
        work_item_id=plan.work_items[2].id,
        person_id=plan.people[0].id,
        hours=Decimal("1.000000000000000000000001"),
    )
    added = add_allocation(changed, third)
    assert added.allocations[-1] is third
    assert remove_allocation(added, first.id).allocations == (second, third)
    assert plan.allocations == (first, second)
    with pytest.raises(ValueError, match="does not exist"):
        update_allocation(plan, third)
    with pytest.raises(ValueError, match="does not exist"):
        remove_allocation(plan, uuid4())
    renamed = rename_person(plan, plan.people[0].id, "New name")
    moved = move_work_item(plan, plan.work_items[1].id, None)
    assert renamed.allocations is plan.allocations
    assert moved.allocations is plan.allocations


def test_new_allocations_are_leaf_only_but_legacy_container_entries_can_be_edited():
    plan = allocated_plan()
    container = plan.work_items[0]
    entry = Allocation(work_item_id=container.id, person_id=plan.people[0].id, hours=Decimal("8"))
    with pytest.raises(ValueError, match="leaf work"):
        add_allocation(plan, entry)
    legacy = replace(plan, allocations=(entry, *plan.allocations))
    changed = update_allocation(legacy, replace(entry, hours=Decimal("9")))
    assert changed.allocations[0].id == entry.id
    assert changed.allocations[0].hours == 9


def test_adding_child_to_allocated_leaf_requires_and_applies_explicit_transfer():
    plan = allocated_plan()
    leaf = plan.work_items[2]
    leaf = replace(leaf, estimate_hours=Decimal("12"), start=date(2026, 10, 4))
    entry = Allocation(work_item_id=leaf.id, person_id=plan.people[0].id, hours=Decimal("7"))
    plan = replace(
        plan,
        work_items=(*plan.work_items[:2], leaf),
        allocations=(*plan.allocations, entry),
    )
    child = WorkItem(title="Research", kind=WorkItemType.SUBTASK, parent_id=leaf.id)
    with pytest.raises(ValueError, match="direct allocations"):
        add_work_item(plan, child)
    resolved = add_work_item(plan, child, transfer_parent_effort=True)
    assert resolved.work_item(leaf.id).estimate_hours is None
    assert resolved.work_item(leaf.id).start == date(2026, 10, 4)
    assert resolved.work_item(child.id).estimate_hours == 12
    moved = next(allocation for allocation in resolved.allocations if allocation.id == entry.id)
    assert moved.work_item_id == child.id and moved.hours == 7
    assert resolved.imports is plan.imports


def test_reparenting_into_allocated_leaf_creates_resolution_leaf_and_preserves_ids():
    plan = allocated_plan()
    target = WorkItem(title="Target program", kind=WorkItemType.EPIC, estimate_hours=Decimal("5"))
    entry = Allocation(work_item_id=target.id, person_id=plan.people[2].id, hours=Decimal("5"))
    plan = replace(
        plan,
        work_items=(*plan.work_items, target),
        allocations=(*plan.allocations, entry),
    )
    moving = plan.work_items[1]
    with pytest.raises(ValueError, match="new leaf"):
        move_work_item(plan, moving.id, target.id)
    resolved = move_work_item(plan, moving.id, target.id, resolve_parent_effort=True)
    children = resolved.children(target.id)
    resolution = next(child for child in children if child.id != moving.id)
    assert resolution.title == "Target program effort"
    assert resolution.estimate_hours == 5
    assert resolved.work_item(target.id).estimate_hours is None
    assert next(a for a in resolved.allocations if a.id == entry.id).work_item_id == resolution.id


def test_existing_container_effort_moves_to_named_leaf_without_touching_descendants():
    plan = allocated_plan()
    parent, existing = plan.work_items[:2]
    direct = Allocation(work_item_id=parent.id, person_id=plan.people[2].id, hours=Decimal("3"))
    legacy = replace(
        plan,
        work_items=(replace(parent, estimate_hours=Decimal("8")), *plan.work_items[1:]),
        allocations=(*plan.allocations, direct),
    )
    resolved = resolve_container_effort(legacy, parent.id, "Program coordination")
    leaf = resolved.work_items[-1]
    assert leaf.title == "Program coordination" and leaf.estimate_hours == 8
    assert resolved.work_item(parent.id).estimate_hours is None
    assert resolved.work_item(existing.id) == existing
    assert next(a for a in resolved.allocations if a.id == direct.id).work_item_id == leaf.id


def test_rollups_recompute_after_reparent_and_delete_without_rewriting_estimates():
    plan = allocated_plan()
    parent = replace(plan.work_items[0], estimate_hours=Decimal("150"))
    other = replace(plan.work_items[2], estimate_hours=Decimal("40"))
    plan = replace(plan, work_items=(parent, plan.work_items[1], other))
    moved = move_work_item(plan, other.id, parent.id)
    by_id = {item.work_item_id: item for item in summarize_allocations(moved, ()).work}
    assert by_id[parent.id].known_estimate_hours == 140
    assert moved.work_item(parent.id).estimate_hours == 150
    restored = remove_work_item(moved, other.id)
    parent_summary = summarize_allocations(restored, ()).work[0]
    assert parent_summary.known_estimate_hours == 100
    assert restored.work_item(parent.id).estimate_hours == 150


def test_jira_export_keeps_stored_container_estimate_instead_of_rollup():
    plan = allocated_plan()
    parent = replace(plan.work_items[0], estimate_hours=Decimal("150"))
    plan = replace(plan, work_items=(parent, *plan.work_items[1:]))
    table = read_csv(export_csv(plan, ExportOptions(estimate_unit="hours")))
    assert table.rows[0][5] == "150"
    assert table.rows[1][5] == "100"
    assert summarize_allocations(plan, ()).work[0].known_estimate_hours == 100


def test_save_load_and_backup_preserve_exact_hours_and_order(tmp_path):
    plan = allocated_plan()
    plan = update_allocation(
        plan,
        replace(plan.allocations[0], hours=Decimal("123.456789012345678901234567890123456789")),
    )
    assert loads(dumps(plan)) == plan
    path = tmp_path / "allocated.planacity"
    save_project(plan, path)
    reopened = load_project(path)
    assert reopened == plan
    assert reopened.allocations[0].hours.as_tuple() == plan.allocations[0].hours.as_tuple()


def test_deleting_work_requires_explicit_consent_for_descendant_allocations():
    plan = allocated_plan()
    with pytest.raises(ValueError, match="2 work allocation"):
        remove_work_item(plan, plan.work_items[0].id, delete_descendants=True)
    removed = remove_work_item(
        plan, plan.work_items[0].id, delete_descendants=True, remove_allocations=True
    )
    assert removed.work_items == (plan.work_items[2],)
    assert not removed.allocations
    assert len(plan.allocations) == 2
    with pytest.raises(ValueError, match="boolean"):
        remove_work_item(plan, plan.work_items[1].id, remove_allocations=1)


def test_deleting_person_requires_consent_and_keeps_other_people_allocations():
    plan = allocated_plan()
    with pytest.raises(ValueError, match="work allocations"):
        remove_person(plan, plan.people[0].id)
    removed = remove_person(plan, plan.people[0].id, remove_allocations=True)
    assert removed.allocations == (plan.allocations[1],)
    assert removed.work_items == plan.work_items
    with pytest.raises(ValueError, match="boolean"):
        remove_person(plan, plan.people[0].id, remove_allocations="yes")


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6])
def test_older_schemas_open_without_inferred_allocations(version, tmp_path):
    plan = replace(allocated_plan(), allocations=())
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
    connection.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.pop("allocations"),
        lambda p: p["allocations"][0].update(hours=1.5),
        lambda p: p["allocations"][0].update(hours="NaN"),
        lambda p: p["allocations"][0].update(hours="-1"),
        lambda p: p["allocations"][0].update(person_id=str(uuid4())),
        lambda p: p["allocations"][0].update(work_item_id=str(uuid4())),
        lambda p: p["allocations"][0].update(extra=True),
        lambda p: p["allocations"].append(p["allocations"][0]),
        lambda p: p["allocations"][1].update(person_id=p["allocations"][0]["person_id"]),
    ],
)
def test_malformed_saved_allocations_are_rejected(mutation):
    data = json.loads(dumps(allocated_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError):
        loads(json.dumps(data))


def test_jira_import_allocations_export_and_deletions_preserve_baselines():
    from test_jira_csv import CSV, MAPPING

    plan = allocated_plan()
    imported = preview_import(plan, read_csv(CSV), MAPPING, {"Alice": plan.people[0]}, "jira.csv")
    assert imported.allocations == plan.allocations
    work = imported.imports[0].records[0].item
    entry = Allocation(work_item_id=work.id, person_id=plan.people[0].id, hours=Decimal("2.25"))
    assigned = add_allocation(imported, entry)
    for unit in ("hours", "seconds"):
        assert export_csv(assigned, ExportOptions(estimate_unit=unit)) == export_csv(
            imported, ExportOptions(estimate_unit=unit)
        )
    assert loads(dumps(assigned)) == assigned
    assert assigned.imports is imported.imports
    removed_person = remove_person(assigned, plan.people[0].id, remove_allocations=True)
    removed_work = remove_work_item(assigned, work.id, remove_allocations=True)
    assert removed_person.imports is assigned.imports
    assert removed_work.imports is assigned.imports
    assert remove_allocation(assigned, entry.id).imports is assigned.imports
