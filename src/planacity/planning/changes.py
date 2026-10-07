"""Computed differences from imported work, without changing the baseline."""

from dataclasses import dataclass
from uuid import UUID

from planacity.domain import ProgramPlan


@dataclass(frozen=True)
class WorkChange:
    item_id: UUID
    reference: str
    title: str
    kind: str
    fields: tuple[str, ...] = ()


def work_changes(plan: ProgramPlan) -> tuple[WorkChange, ...]:
    if not plan.imports:
        return ()
    baseline = {r.item.id: r for source in plan.imports for r in source.records}
    current = {item.id: item for item in plan.work_items}
    changes = []
    for identifier, record in baseline.items():
        item = current.get(identifier)
        if item is None:
            changes.append(
                WorkChange(identifier, record.external_reference, record.item.title, "Removed")
            )
            continue
        fields = tuple(
            field
            for field in (
                "title",
                "kind",
                "parent_id",
                "estimate_hours",
                "start",
                "end",
                "priority",
            )
            if getattr(item, field) != getattr(record.item, field)
        )
        if fields:
            changes.append(
                WorkChange(identifier, record.external_reference, item.title, "Modified", fields)
            )
    changes.extend(
        WorkChange(item.id, "", item.title, "Added")
        for item in plan.work_items
        if item.id not in baseline
    )
    return tuple(changes)
