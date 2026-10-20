"""Canonical sprint lifecycle, diagnostics, persistence, and migration."""

import json
import sqlite3
from dataclasses import replace
from datetime import date

import pytest

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Sprint,
    SprintAssignment,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import SCHEMA_VERSION, dumps, loads
from planacity.persistence.project import APPLICATION_ID, load_project, save_project
from planacity.planning.sprints import (
    SprintFindingKind,
    add_sprint,
    assign_work_to_sprint,
    remove_sprint,
    sprint_findings,
    unassign_work_from_sprint,
    update_sprint,
)
from planacity.planning.structure import remove_work_group
from planacity.planning.work_items import remove_work_item


def sprint_plan() -> tuple[ProgramPlan, Sprint, Sprint, WorkItem, WorkItem]:
    epic = WorkItem(title="Mission", kind=WorkItemType.EPIC)
    task = WorkItem(
        title="Guidance",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        start=date(2027, 1, 5),
        end=date(2027, 1, 9),
    )
    undated = WorkItem(title="Review", kind=WorkItemType.TASK, parent_id=epic.id)
    group = WorkGroup(name="Flight", epic_ids=(epic.id,))
    first = Sprint(
        name="Sprint 1",
        period=PlanningHorizon(date(2027, 1, 4), date(2027, 1, 10)),
        external_reference="board-42:1",
        work_group_id=group.id,
    )
    second = Sprint(
        name="Sprint 2",
        period=PlanningHorizon(date(2027, 1, 9), date(2027, 1, 17)),
    )
    plan = ProgramPlan(
        name="Sprint plan",
        horizon=PlanningHorizon(date(2027, 1, 4), date(2027, 2, 28)),
        work_items=(epic, task, undated),
        work_groups=(group,),
    )
    return plan, first, second, task, undated


def test_sprint_lifecycle_assignment_and_identity_are_immutable():
    plan, first, second, task, _ = sprint_plan()
    with_first = add_sprint(plan, first)
    scheduled = assign_work_to_sprint(with_first, first.id, task.id)
    assignment = scheduled.sprint_assignments[0]

    assert plan.sprints == plan.sprint_assignments == ()
    assert assign_work_to_sprint(scheduled, first.id, task.id) is scheduled
    with_second = add_sprint(scheduled, second)
    moved = assign_work_to_sprint(with_second, second.id, task.id)
    assert moved.sprint_assignments[0].id == assignment.id
    assert moved.sprint_assignments[0].sprint_id == second.id
    assert unassign_work_from_sprint(moved, task.id).sprint_assignments == ()

    renamed = update_sprint(with_second, replace(first, name="Iteration Alpha"))
    assert renamed.sprints[0].name == "Iteration Alpha"
    removed = remove_sprint(renamed, first.id)
    assert removed.sprints == (second,)
    assert removed.sprint_assignments == ()


def test_sprint_assignments_accept_only_existing_executable_leaves():
    plan, first, _, task, _ = sprint_plan()
    plan = add_sprint(plan, first)
    epic = plan.work_items[0]
    child = WorkItem(title="Detail", kind=WorkItemType.SUBTASK, parent_id=task.id)
    container = replace(plan, work_items=(*plan.work_items, child))

    with pytest.raises(ValueError, match="executable leaf"):
        assign_work_to_sprint(plan, first.id, epic.id)
    with pytest.raises(ValueError, match="executable leaf"):
        assign_work_to_sprint(container, first.id, task.id)
    with pytest.raises(ValueError, match="does not exist"):
        assign_work_to_sprint(plan, Sprint(name="Other", period=first.period).id, task.id)


def test_sprint_findings_retain_overlaps_irregular_dates_and_incomplete_work():
    plan, first, second, task, undated = sprint_plan()
    outside = Sprint(
        name="Early",
        period=PlanningHorizon(date(2026, 12, 28), date(2027, 1, 5)),
    )
    plan = replace(plan, sprints=(outside, first, second))
    plan = assign_work_to_sprint(plan, second.id, task.id)
    plan = assign_work_to_sprint(plan, first.id, undated.id)

    findings = sprint_findings(plan)

    assert sum(value.kind == SprintFindingKind.OVERLAP for value in findings) == 2
    assert any(value.kind == SprintFindingKind.OUTSIDE_HORIZON for value in findings)
    assert any(value.kind == SprintFindingKind.WORK_OUTSIDE_SPRINT for value in findings)
    assert any(value.kind == SprintFindingKind.WORK_DATES_INCOMPLETE for value in findings)
    assert len(plan.sprints) == 3


def test_referenced_group_and_work_removal_require_explicit_resolution():
    plan, first, _, task, _ = sprint_plan()
    plan = assign_work_to_sprint(add_sprint(plan, first), first.id, task.id)
    group_id = plan.work_groups[0].id

    with pytest.raises(ValueError, match="sprint scope"):
        remove_work_group(plan, group_id)
    without_group = remove_work_group(plan, group_id, clear_primary_references=True)
    assert without_group.sprints[0].work_group_id is None

    with pytest.raises(ValueError, match="sprint assignment"):
        remove_work_item(plan, task.id)
    without_work = remove_work_item(plan, task.id, remove_references=True)
    assert without_work.sprint_assignments == ()


def test_schema_thirteen_roundtrip_and_schema_twelve_migration(tmp_path):
    plan, first, _, task, _ = sprint_plan()
    plan = assign_work_to_sprint(add_sprint(plan, first), first.id, task.id)
    payload = dumps(plan)
    data = json.loads(payload)
    path = tmp_path / "sprints.planacity"
    save_project(plan, path)

    assert data["schema_version"] == SCHEMA_VERSION == 14
    assert data["plan"]["sprints"][0]["external_reference"] == "board-42:1"
    assert loads(payload) == load_project(path) == plan
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14

    data["schema_version"] = 12
    data["plan"].pop("sprints")
    data["plan"].pop("sprint_assignments")
    data["plan"].pop("reservation_coverages")
    old_payload = json.dumps(data)
    old_path = tmp_path / "schema-12.planacity"
    with sqlite3.connect(old_path) as connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=12")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (old_payload,))
    migrated = replace(plan, sprints=(), sprint_assignments=())
    assert loads(old_payload) == load_project(old_path) == migrated


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda p: p["sprints"][0].update(name=""), "non-blank"),
        (lambda p: p["sprints"][0].update(external_reference=""), "non-blank"),
        (
            lambda p: p["sprints"][0].update(
                work_group_id=str(
                    Sprint(name="x", period=PlanningHorizon(date(2027, 1, 1), date(2027, 1, 1))).id
                )
            ),
            "WorkGroup",
        ),
        (lambda p: p["sprint_assignments"].append(p["sprint_assignments"][0]), "unique"),
        (
            lambda p: p["sprint_assignments"][0].update(
                sprint_id=str(
                    Sprint(name="x", period=PlanningHorizon(date(2027, 1, 1), date(2027, 1, 1))).id
                )
            ),
            "existing Sprint",
        ),
        (lambda p: p.pop("sprints"), "exactly these fields"),
    ],
)
def test_malformed_sprint_data_is_rejected(mutation, message):
    plan, first, _, task, _ = sprint_plan()
    data = json.loads(dumps(assign_work_to_sprint(add_sprint(plan, first), first.id, task.id)))
    mutation(data["plan"])
    with pytest.raises(ValueError, match=message):
        loads(json.dumps(data))


def test_program_plan_rejects_duplicate_work_assignment_and_container_reference():
    plan, first, _, task, _ = sprint_plan()
    assignment = SprintAssignment(sprint_id=first.id, work_item_id=task.id)
    with pytest.raises(ValueError, match="at most one sprint"):
        replace(
            plan,
            sprints=(first,),
            sprint_assignments=(
                assignment,
                replace(
                    assignment, id=SprintAssignment(sprint_id=first.id, work_item_id=task.id).id
                ),
            ),
        )
    with pytest.raises(ValueError, match="executable leaf"):
        replace(
            plan,
            sprints=(first,),
            sprint_assignments=(
                SprintAssignment(sprint_id=first.id, work_item_id=plan.work_items[0].id),
            ),
        )
