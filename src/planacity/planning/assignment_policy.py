"""Single-person leaf policy without rejecting or rewriting legacy plans."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan


@dataclass(frozen=True)
class AssignmentPolicyConflict:
    """One executable leaf that retains several explicit assignments."""

    work_item_id: UUID
    allocation_ids: tuple[UUID, ...]
    person_ids: tuple[UUID, ...]


def assignment_policy_conflicts(plan: ProgramPlan) -> tuple[AssignmentPolicyConflict, ...]:
    """Return legacy multi-person leaves in canonical work-item order.

    Zero-hour entries remain assignments. Containers are handled by the existing
    hierarchy-effort policy and are deliberately excluded here.
    """
    allocations_by_work: dict[UUID, list[tuple[UUID, UUID]]] = {
        item.id: [] for item in plan.work_items
    }
    for allocation in plan.allocations:
        allocations_by_work[allocation.work_item_id].append((allocation.id, allocation.person_id))

    conflicts = []
    for item in plan.work_items:
        if plan.children(item.id):
            continue
        entries = allocations_by_work[item.id]
        if len(entries) <= 1:
            continue
        conflicts.append(
            AssignmentPolicyConflict(
                work_item_id=item.id,
                allocation_ids=tuple(sorted((entry[0] for entry in entries), key=str)),
                person_ids=tuple(sorted((entry[1] for entry in entries), key=str)),
            )
        )
    return tuple(conflicts)


def validate_assignment_transition(before: ProgramPlan, after: ProgramPlan) -> None:
    """Reject new or worsened multi-person leaves while permitting legacy repair.

    A legacy conflict may be edited without changing its allocation identities and
    may be reduced by removing or moving entries. Adding another allocation to it,
    or moving an allocation onto an already assigned leaf, is rejected.
    """
    previous = {
        conflict.work_item_id: frozenset(conflict.allocation_ids)
        for conflict in assignment_policy_conflicts(before)
    }
    for conflict in assignment_policy_conflicts(after):
        earlier = previous.get(conflict.work_item_id)
        if earlier is not None and frozenset(conflict.allocation_ids).issubset(earlier):
            continue
        item = after.work_item(conflict.work_item_id)
        raise ValueError(
            f"'{item.title}' can have at most one allocation. Reassign or remove the existing "
            "allocation, or split collaborative work into separately assigned leaves."
        )
