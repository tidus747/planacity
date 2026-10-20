"""Saved reservation coverage and safe lifecycle behavior."""

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
    ReservationCoverage,
    ReservationRule,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import SCHEMA_VERSION, dumps, loads
from planacity.persistence.project import (
    APPLICATION_ID,
    export_backup,
    load_project,
    restore_backup,
    save_project,
)
from planacity.planning.allocation_settings import remove_allocation, update_allocation
from planacity.planning.assignees import set_work_assignment
from planacity.planning.assignment_resolution import preview_assignment_consolidation
from planacity.planning.people import remove_person
from planacity.planning.reservation_coverage_settings import (
    add_reservation_coverage,
    remove_reservation_coverage,
    update_reservation_coverage,
)
from planacity.planning.reservation_settings import remove_reservation, update_reservation
from planacity.planning.work_items import remove_work_item


def coverage_plan() -> ProgramPlan:
    people = (Person(name="Alex"), Person(name="Sam"))
    work = (
        WorkItem(
            title="Front Office",
            kind=WorkItemType.TASK,
            assignee_id=people[0].id,
        ),
        WorkItem(
            title="Meetings",
            kind=WorkItemType.TASK,
            assignee_id=people[1].id,
        ),
    )
    allocations = tuple(
        Allocation(work_item_id=item.id, person_id=person.id, hours=Decimal(hours))
        for item, person, hours in zip(work, people, ("8.125", "4"), strict=True)
    )
    horizon = PlanningHorizon(date(2026, 10, 1), date(2026, 10, 31))
    rules = (
        ReservationRule(
            name="Duties",
            person_ids=tuple(person.id for person in people),
            hours_per_person=Decimal("6.25"),
            anchor=horizon.start,
            interval_weeks=1,
            effective=horizon,
        ),
        ReservationRule(
            name="Sam meetings",
            person_ids=(people[1].id,),
            hours_per_person=Decimal("2"),
            anchor=horizon.start,
            interval_weeks=1,
            effective=horizon,
        ),
    )
    return ProgramPlan(
        name="Covered duties",
        horizon=horizon,
        people=people,
        work_items=work,
        allocations=allocations,
        reservation_rules=rules,
    )


def linked_plan() -> ProgramPlan:
    plan = coverage_plan()
    return add_reservation_coverage(
        add_reservation_coverage(
            plan,
            ReservationCoverage(
                allocation_id=plan.allocations[0].id,
                reservation_rule_id=plan.reservation_rules[0].id,
            ),
        ),
        ReservationCoverage(
            allocation_id=plan.allocations[1].id,
            reservation_rule_id=plan.reservation_rules[1].id,
        ),
    )


def test_lifecycle_preserves_ids_order_and_unrelated_plan_data() -> None:
    plan = linked_plan()
    first, second = plan.reservation_coverages
    changed = update_reservation_coverage(
        plan,
        replace(first, reservation_rule_id=plan.reservation_rules[0].id),
    )
    assert changed.reservation_coverages == (first, second)
    assert changed.imports is plan.imports
    assert remove_reservation_coverage(changed, first.id).reservation_coverages == (second,)
    assert plan.reservation_coverages == (first, second)

    with pytest.raises(ValueError, match="already has"):
        add_reservation_coverage(
            plan,
            ReservationCoverage(
                allocation_id=plan.allocations[0].id,
                reservation_rule_id=plan.reservation_rules[0].id,
            ),
        )
    unknown = replace(first, id=uuid4())
    with pytest.raises(ValueError, match="does not exist"):
        update_reservation_coverage(plan, unknown)
    with pytest.raises(ValueError, match="does not exist"):
        remove_reservation_coverage(plan, uuid4())


def test_project_and_backup_roundtrip_schema_fourteen_exactly(tmp_path) -> None:
    plan = linked_plan()
    project = tmp_path / "covered.planacity"
    backup = tmp_path / "covered.json"

    save_project(plan, project)
    export_backup(plan, backup)

    assert SCHEMA_VERSION == 14
    assert load_project(project) == plan
    assert restore_backup(backup) == plan
    data = json.loads(dumps(plan))
    assert data["schema_version"] == 14
    assert data["plan"]["reservation_coverages"] == [
        {
            "allocation_id": str(value.allocation_id),
            "reservation_rule_id": str(value.reservation_rule_id),
            "id": str(value.id),
        }
        for value in plan.reservation_coverages
    ]


def test_schema_thirteen_loads_without_links_and_upgrades_only_on_save(tmp_path) -> None:
    plan = coverage_plan()
    data = json.loads(dumps(plan))
    data["schema_version"] = 13
    data["plan"].pop("reservation_coverages")
    payload = json.dumps(data)
    project = tmp_path / "schema-13.planacity"
    with sqlite3.connect(project) as connection:
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=13")
        connection.execute("CREATE TABLE document (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO document VALUES (1, ?)", (payload,))
    connection.close()

    before = project.read_bytes()
    loaded = load_project(project)
    assert loaded == plan
    assert loaded.reservation_coverages == ()
    assert project.read_bytes() == before

    save_project(loaded, project)
    assert load_project(project) == plan
    with sqlite3.connect(project) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.pop("reservation_coverages"),
        lambda p: p["reservation_coverages"][0].update(extra=True),
        lambda p: p["reservation_coverages"][0].update(id="not-a-uuid"),
        lambda p: p["reservation_coverages"][0].update(allocation_id=str(uuid4())),
        lambda p: p["reservation_coverages"][0].update(reservation_rule_id=str(uuid4())),
        lambda p: p["reservation_coverages"].append(p["reservation_coverages"][0]),
        lambda p: p["reservation_coverages"][1].update(
            allocation_id=p["reservation_coverages"][0]["allocation_id"]
        ),
        lambda p: p["reservation_coverages"][0].update(
            reservation_rule_id=p["reservation_rules"][1]["id"]
        ),
    ],
)
def test_malformed_saved_coverages_are_rejected(mutation) -> None:
    data = json.loads(dumps(linked_plan()))
    mutation(data["plan"])
    with pytest.raises(ValueError, match="Cannot read plan"):
        loads(json.dumps(data))


def test_direct_deletions_require_confirmation_and_remove_only_dependent_links() -> None:
    plan = linked_plan()
    first, second = plan.reservation_coverages
    with pytest.raises(ValueError, match="coverage"):
        remove_allocation(plan, first.allocation_id)
    without_allocation = remove_allocation(plan, first.allocation_id, remove_coverage=True)
    assert without_allocation.reservation_coverages == (second,)
    assert len(without_allocation.allocations) == 1

    with pytest.raises(ValueError, match="coverage"):
        remove_reservation(plan, second.reservation_rule_id)
    without_rule = remove_reservation(plan, second.reservation_rule_id, remove_coverages=True)
    assert without_rule.reservation_coverages == (first,)
    assert len(without_rule.reservation_rules) == 1

    with pytest.raises(ValueError, match="explicit boolean"):
        remove_allocation(plan, first.allocation_id, remove_coverage=1)
    with pytest.raises(ValueError, match="explicit boolean"):
        remove_reservation(plan, first.reservation_rule_id, remove_coverages="yes")


def test_incompatible_edits_are_rejected_while_compatible_edits_keep_links() -> None:
    plan = linked_plan()
    allocation = plan.allocations[0]
    incompatible_allocation = plan.allocations[1]
    rule = plan.reservation_rules[0]
    incompatible_rule = plan.reservation_rules[1]

    changed = update_allocation(plan, replace(allocation, hours=Decimal("9.75")))
    assert changed.reservation_coverages is plan.reservation_coverages
    changed = update_reservation(changed, replace(rule, name="Shared duties"))
    assert changed.reservation_coverages is plan.reservation_coverages

    with pytest.raises(ValueError, match="does not include"):
        update_allocation(
            plan,
            replace(incompatible_allocation, person_id=plan.people[0].id),
        )
    with pytest.raises(ValueError, match="does not include"):
        update_reservation(
            plan,
            replace(incompatible_rule, person_ids=(plan.people[0].id,)),
        )


def test_confirmed_person_and_work_removals_clean_only_dependent_links() -> None:
    plan = linked_plan()
    first, second = plan.reservation_coverages
    removed_work = remove_work_item(
        plan,
        plan.work_items[0].id,
        remove_allocations=True,
    )
    assert removed_work.reservation_coverages == (second,)
    assert removed_work.reservation_rules == plan.reservation_rules

    removed_person = remove_person(
        plan,
        plan.people[0].id,
        remove_allocations=True,
        remove_reservations=True,
        clear_assignees=True,
    )
    assert removed_person.reservation_coverages == (second,)
    assert removed_person.allocations == (plan.allocations[1],)
    assert removed_person.reservation_rules[0].person_ids == (plan.people[1].id,)
    assert first not in removed_person.reservation_coverages


def test_other_allocation_removal_workflows_require_coverage_cleanup() -> None:
    plan = linked_plan()
    with pytest.raises(ValueError, match="reservation coverage"):
        set_work_assignment(plan, plan.work_items[0].id, None, None)

    extra = Allocation(
        work_item_id=plan.work_items[0].id,
        person_id=plan.people[1].id,
        hours=Decimal("2"),
    )
    extra_coverage = ReservationCoverage(
        allocation_id=extra.id,
        reservation_rule_id=plan.reservation_rules[0].id,
    )
    legacy = replace(
        plan,
        allocations=(*plan.allocations, extra),
        reservation_coverages=(*plan.reservation_coverages, extra_coverage),
    )
    with pytest.raises(ValueError, match="coverage"):
        preview_assignment_consolidation(
            legacy,
            plan.work_items[0].id,
            plan.allocations[0].id,
        )
