"""Acceptance contract for the reproducible v0.4 demonstration."""

import csv
import io
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItemType, WorkPriority
from planacity.integrations.jira.csv_io import Mapping, preview_import, read_csv
from planacity.integrations.jira.export import export_csv
from planacity.persistence.codec import SCHEMA_VERSION, dumps, loads
from planacity.persistence.project import (
    export_backup,
    load_project,
    restore_backup,
    save_project,
)
from planacity.planning.capacity import calculate_dated_capacity
from planacity.planning.changes import work_changes
from planacity.planning.dependency_validation import dependency_findings
from planacity.planning.findings import planning_findings

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "moon-heist.planacity.json"
JIRA_SAMPLE = ROOT / "examples" / "jira-moon-heist.csv"


def load_example():
    return restore_backup(EXAMPLE)


def test_moon_heist_is_a_complete_deterministic_v04_baseline():
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    plan = load_example()

    assert raw["schema_version"] == SCHEMA_VERSION == 11
    assert dumps(plan) == EXAMPLE.read_text(encoding="utf-8")
    assert plan.id == uuid5(
        NAMESPACE_URL, "https://planacity.example/moon-heist/plan/operation-moon-heist"
    )
    assert plan.horizon == PlanningHorizon(date(2027, 1, 4), date(2027, 2, 12))
    assert len(plan.people) == 5
    assert len(plan.work_groups) == 4
    assert len(plan.work_items) == 19
    assert len(plan.relationships) == 12

    leaves = tuple(item for item in plan.work_items if not plan.children(item.id))
    containers = tuple(item for item in plan.work_items if plan.children(item.id))
    allocations_by_work = defaultdict(list)
    for allocation in plan.allocations:
        allocations_by_work[allocation.work_item_id].append(allocation)

    assert len(leaves) == 14
    for leaf in leaves:
        assert leaf.kind in (WorkItemType.TASK, WorkItemType.SUBTASK)
        assert leaf.assignee_id is not None
        assert leaf.estimate_hours is not None and leaf.estimate_hours > 0
        assert leaf.start is not None and leaf.end is not None
        assert leaf.description.strip()
        assert leaf.priority is not None
        assert leaf.primary_group_id is not None
        assert len(allocations_by_work[leaf.id]) == 1
        allocation = allocations_by_work[leaf.id][0]
        assert allocation.person_id == leaf.assignee_id
        assert allocation.hours == leaf.estimate_hours

    assert all(item.estimate_hours is None for item in containers)
    assert all(not allocations_by_work[item.id] for item in containers)
    assert all(epic.assignee_id is not None for epic in plan.children())

    calibration = next(item for item in plan.work_items if item.title == "Calibrate the beam")
    calibration_leaves = plan.children(calibration.id)
    assert {item.title for item in calibration_leaves} == {
        "Adjust the optics",
        "Verify the beam",
    }
    assert sum(item.estimate_hours for item in calibration_leaves) == 24
    assert len({item.assignee_id for item in calibration_leaves}) == 2

    hours_by_person = defaultdict(int)
    hours_by_group = defaultdict(int)
    groups_by_person = defaultdict(set)
    for allocation in plan.allocations:
        item = plan.work_item(allocation.work_item_id)
        hours_by_person[plan.person(allocation.person_id).name] += allocation.hours
        group = plan.work_group(item.primary_group_id)
        hours_by_group[group.name] += allocation.hours
        groups_by_person[plan.person(allocation.person_id).name].add(group.name)

    assert dict(hours_by_person) == {
        "Dr. Nefario": 28,
        "Bob": 32,
        "Kevin": 60,
        "Stuart": 60,
        "Dave": 56,
    }
    assert dict(hours_by_group) == {
        "Shrink technology": 48,
        "Spacecraft": 60,
        "Lunar operations": 76,
        "Mission support": 52,
    }
    assert sum(hours_by_person.values()) == 236
    assert groups_by_person["Kevin"] == {"Spacecraft", "Lunar operations"}
    assert groups_by_person["Dave"] == {"Lunar operations", "Mission support"}

    assert planning_findings(plan) == ()
    assert dependency_findings(plan) == ()


def test_moon_heist_capacity_reconciles_and_is_feasible_every_day():
    plan = load_example()
    capacity = calculate_dated_capacity(plan, plan.horizon)
    results = {plan.person(result.person_id).name: result for result in capacity.people}

    assert capacity.complete
    assert {
        name: (
            result.nominal_hours,
            result.unavailable_hours,
            result.reserved_hours,
            result.planning_hours,
            result.allocated_hours,
            result.remaining_hours,
        )
        for name, result in results.items()
    } == {
        "Dr. Nefario": (240, 0, 12, 228, 28, 200),
        "Kevin": (240, 0, 36, 204, 60, 144),
        "Stuart": (240, 8, 12, 220, 60, 160),
        "Bob": (180, 0, 12, 168, 32, 136),
        "Dave": (240, 0, 12, 228, 56, 172),
    }
    assert sum(result.planning_hours for result in results.values()) == 1048
    assert sum(result.allocated_hours for result in results.values()) == 236
    assert sum(result.remaining_hours for result in results.values()) == 812
    assert all(day.remaining_hours >= 0 for result in results.values() for day in result.days)


def test_moon_heist_project_backup_and_jira_baseline_round_trip(tmp_path):
    original = load_example()
    project = tmp_path / "moon-heist.planacity"
    backup = tmp_path / "moon-heist.json"

    save_project(original, project)
    export_backup(original, backup)

    assert load_project(project) == original
    assert restore_backup(backup) == original
    assert loads(dumps(original)) == original
    assert restore_backup(EXAMPLE) == original

    source = original.imports[0]
    table = read_csv(JIRA_SAMPLE.read_text(encoding="utf-8"))
    assert table.headers == source.headers
    assert table.rows == source.rows
    assert not [change for change in work_changes(original) if change.kind != "Added"]

    priority_mapping = (("High", WorkPriority.HIGH), ("Highest", WorkPriority.HIGHEST))
    mapping = Mapping(
        columns=(
            ("reference", 0),
            ("row_id", 1),
            ("type", 2),
            ("title", 3),
            ("priority", 4),
            ("parent", 5),
            ("estimate", 6),
            ("start", 7),
            ("end", 8),
            ("person", 9),
            ("status", 10),
        ),
        priorities=priority_mapping,
    )
    people = {person.name: person for person in original.people}
    imported = preview_import(
        ProgramPlan(
            name="CSV import check",
            horizon=original.horizon,
            people=original.people,
        ),
        table,
        mapping,
        {
            "nefario@example.test": people["Dr. Nefario"],
            "bob@example.test": people["Bob"],
        },
        "Operation Moon Heist Jira sample",
    )
    assert not work_changes(imported)
    assert [item.estimate_hours for item in imported.work_items] == [None, 12, None, 16, 8, 12]

    identities = {
        "Dr. Nefario": "nefario@example.test",
        "Kevin": "kevin@example.test",
        "Stuart": "stuart@example.test",
        "Bob": "bob@example.test",
        "Dave": "dave@example.test",
    }
    exported = tuple(
        csv.DictReader(
            io.StringIO(
                export_csv(
                    original,
                    person_mappings=tuple(
                        (person.id, identities[person.name]) for person in original.people
                    ),
                )
            )
        )
    )
    imported_rows = {row["Issue key"]: row for row in exported if row["Issue key"]}
    assert set(imported_rows) == {f"MH-{number}" for number in range(1, 7)}
    assert imported_rows["MH-1"]["Assignee"] == "nefario@example.test"
    assert imported_rows["MH-3"]["Assignee"] == ""
    assert imported_rows["MH-5"]["Assignee"] == "bob@example.test"
    assert imported_rows["MH-6"]["Priority"] == "Highest"
    assert imported_rows["MH-6"]["Status"] == "To Do"
