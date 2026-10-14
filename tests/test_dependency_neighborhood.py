"""Selected-work dependency graph projections stay bounded and domain-only."""

from datetime import date
from decimal import Decimal

from planacity.domain import (
    Allocation,
    Person,
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkItem,
    WorkItemType,
)
from planacity.planning.dependency_neighborhood import project_dependency_neighborhood


def test_neighborhood_normalizes_edges_and_exposes_people_dates_warnings_and_visibility():
    alice, bob, owner = (Person(name=name) for name in ("Alice", "Bob", "Owner"))
    predecessor = WorkItem(
        title="A predecessor with a deliberately long title that remains available in full",
        kind=WorkItemType.EPIC,
        assignee_id=owner.id,
        start=date(2026, 1, 1),
        end=date(2026, 1, 3),
    )
    child = WorkItem(
        title="Predecessor leaf",
        kind=WorkItemType.TASK,
        parent_id=predecessor.id,
    )
    selected = WorkItem(
        title="Selected integration",
        kind=WorkItemType.TASK,
        start=date(2026, 1, 3),
    )
    successor = WorkItem(
        title="Successor",
        kind=WorkItemType.TASK,
        start=date(2026, 1, 4),
        end=date(2026, 1, 8),
    )
    plan = ProgramPlan(
        name="Graph",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        people=(alice, bob, owner),
        work_items=(predecessor, child, selected, successor),
        allocations=(
            Allocation(work_item_id=child.id, person_id=alice.id, hours=Decimal(8)),
            Allocation(work_item_id=selected.id, person_id=alice.id, hours=Decimal(4)),
            Allocation(work_item_id=selected.id, person_id=bob.id, hours=Decimal(4)),
        ),
        relationships=(
            Relationship(
                source_id=selected.id,
                target_id=predecessor.id,
                kind=RelationshipType.DEPENDS_ON,
            ),
            Relationship(
                source_id=selected.id,
                target_id=successor.id,
                kind=RelationshipType.BLOCKS,
            ),
            Relationship(
                source_id=predecessor.id,
                target_id=successor.id,
                kind=RelationshipType.RELATED_TO,
            ),
        ),
    )

    graph = project_dependency_neighborhood(
        plan, selected.id, visible_ids=frozenset((selected.id, successor.id))
    )

    assert [card.item_id for card in graph.predecessors] == [predecessor.id]
    assert [card.item_id for card in graph.successors] == [successor.id]
    assert graph.predecessors[0].title == predecessor.title
    assert graph.predecessors[0].assignment == ("Feature owner: Owner | Aggregate team: Alice")
    assert not graph.predecessors[0].visible_in_timeline
    assert graph.selected.dates == "Starts 2026-01-03; no end"
    assert graph.selected.assignment == "Legacy assignments: Alice, Bob"
    assert any("unevaluated" in warning.lower() for warning in graph.selected.warnings)
    assert graph.unevaluated_edges == 1
    assert graph.conflict_edges == 1


def test_container_cards_report_their_aggregate_team():
    alice, bob = Person(name="Alice"), Person(name="Bob")
    parent = WorkItem(title="Container", kind=WorkItemType.TASK)
    first = WorkItem(title="First", kind=WorkItemType.SUBTASK, parent_id=parent.id)
    second = WorkItem(title="Second", kind=WorkItemType.SUBTASK, parent_id=parent.id)
    selected = WorkItem(title="Selected", kind=WorkItemType.TASK)
    plan = ProgramPlan(
        name="Aggregate",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        people=(alice, bob),
        work_items=(parent, first, second, selected),
        allocations=(
            Allocation(work_item_id=first.id, person_id=alice.id, hours=Decimal(3)),
            Allocation(work_item_id=second.id, person_id=bob.id, hours=Decimal(5)),
        ),
        relationships=(
            Relationship(
                source_id=parent.id,
                target_id=selected.id,
                kind=RelationshipType.BLOCKS,
            ),
        ),
    )

    graph = project_dependency_neighborhood(plan, selected.id)

    assert graph.predecessors[0].assignment == "Aggregate team: Alice, Bob"


def test_cycles_are_explicit_and_large_neighbourhoods_keep_navigable_omissions():
    selected = WorkItem(title="Selected", kind=WorkItemType.TASK)
    predecessors = tuple(
        WorkItem(title=f"Predecessor {number:02d}", kind=WorkItemType.TASK) for number in range(20)
    )
    successors = tuple(
        WorkItem(title=f"Successor {number:02d}", kind=WorkItemType.TASK) for number in range(20)
    )
    relationships = tuple(
        Relationship(
            source_id=item.id,
            target_id=selected.id,
            kind=RelationshipType.BLOCKS,
        )
        for item in predecessors
    ) + tuple(
        Relationship(
            source_id=selected.id,
            target_id=item.id,
            kind=RelationshipType.BLOCKS,
        )
        for item in successors
    )
    relationships += (
        Relationship(
            source_id=successors[0].id,
            target_id=selected.id,
            kind=RelationshipType.BLOCKS,
        ),
    )
    plan = ProgramPlan(
        name="Bounded",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        work_items=(selected, *predecessors, *successors),
        relationships=relationships,
    )

    graph = project_dependency_neighborhood(plan, selected.id)

    assert graph.displayed_cards == 30
    # The first successor is also an immediate predecessor through the cycle.
    assert len(graph.omitted_predecessors) + len(graph.omitted_successors) == 12
    assert graph.cycle_edges == 2
    assert {card.item_id for card in graph.omitted_predecessors}.isdisjoint(
        card.item_id for card in graph.predecessors
    )
    assert {card.item_id for card in graph.omitted_successors}.isdisjoint(
        card.item_id for card in graph.successors
    )


def test_invalid_card_limit_is_rejected():
    selected = WorkItem(title="Selected", kind=WorkItemType.TASK)
    plan = ProgramPlan(
        name="Invalid limit",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 2)),
        work_items=(selected,),
    )

    try:
        project_dependency_neighborhood(plan, selected.id, max_cards=0)
    except ValueError as error:
        assert "at least one card" in str(error)
    else:
        raise AssertionError("Expected a ValueError for a zero-card neighbourhood.")
