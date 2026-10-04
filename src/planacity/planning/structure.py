"""Explicit group membership and relationship operations, separate from hierarchy."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import ProgramPlan, Relationship, WorkGroup
from planacity.planning.dependency_validation import validate_dependency_change


def add_work_group(plan: ProgramPlan, group: WorkGroup) -> ProgramPlan:
    return replace(plan, work_groups=(*plan.work_groups, group))


def rename_work_group(plan: ProgramPlan, group_id: UUID, name: str) -> ProgramPlan:
    updated = replace(plan.work_group(group_id), name=name)
    return replace(
        plan,
        work_groups=tuple(updated if group.id == group_id else group for group in plan.work_groups),
    )


def set_group_epics(plan: ProgramPlan, group_id: UUID, epic_ids: tuple[UUID, ...]) -> ProgramPlan:
    updated = replace(plan.work_group(group_id), epic_ids=epic_ids)
    return replace(
        plan,
        work_groups=tuple(updated if group.id == group_id else group for group in plan.work_groups),
    )


def remove_work_group(plan: ProgramPlan, group_id: UUID) -> ProgramPlan:
    """Remove the group and its memberships; preserve every work item and link."""
    plan.work_group(group_id)
    return replace(
        plan, work_groups=tuple(group for group in plan.work_groups if group.id != group_id)
    )


def add_relationship(plan: ProgramPlan, relationship: Relationship) -> ProgramPlan:
    candidate = replace(plan, relationships=(*plan.relationships, relationship))
    validate_dependency_change(plan, candidate, added_relationship_ids=(relationship.id,))
    return candidate


def remove_relationship(plan: ProgramPlan, relationship_id: UUID) -> ProgramPlan:
    if not any(link.id == relationship_id for link in plan.relationships):
        raise ValueError(f"Relationship {relationship_id} does not exist in this plan.")
    return replace(
        plan, relationships=tuple(link for link in plan.relationships if link.id != relationship_id)
    )
