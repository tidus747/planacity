"""Pure grouping and filtering of canonical Timeline rows."""

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from planacity.domain import WorkItemType
from planacity.planning.timeline import TimelineDateState, TimelineProjection, TimelineRow


class TimelineGrouping(StrEnum):
    HIERARCHY = "hierarchy"
    EPIC = "epic"
    WORKGROUP = "workgroup"


@dataclass(frozen=True)
class TimelineFilters:
    text: str = ""
    kind: WorkItemType | None = None
    group_id: UUID | None = None
    state: TimelineDateState | None = None

    def matches(self, row: TimelineRow) -> bool:
        return (
            self.text.strip().casefold() in row.title.casefold()
            and (self.kind is None or row.kind == self.kind)
            and (self.group_id is None or self.group_id in row.group_ids)
            and (self.state is None or row.date_state == self.state)
        )


def arrange_timeline(
    projection: TimelineProjection,
    grouping: TimelineGrouping = TimelineGrouping.HIERARCHY,
    filters: TimelineFilters | None = None,
) -> TimelineProjection:
    """Keep canonical sibling order and UUIDs, including repeated group membership.

    Filters match individual rows. A matching child does not imply that its parent
    matches. WorkGroup membership is inherited from the containing Epic.
    """
    filters = filters or TimelineFilters()
    rows = tuple(row for row in projection.rows if filters.matches(row))
    if grouping == TimelineGrouping.HIERARCHY:
        return replace(projection, rows=rows)
    sections: list[tuple[UUID | None, str, tuple[TimelineRow, ...]]] = []
    if grouping == TimelineGrouping.WORKGROUP:
        sections.extend(
            (group.id, group.name, tuple(row for row in rows if group.id in row.group_ids))
            for group in projection.groups
            if filters.group_id is None or group.id == filters.group_id
        )
        sections.append((None, "Ungrouped work", tuple(row for row in rows if not row.group_ids)))
    else:
        epic_for: dict[UUID, UUID | None] = {}
        for row in projection.rows:
            epic_for[row.item_id] = (
                row.item_id
                if row.kind == WorkItemType.EPIC
                else epic_for.get(row.parent_id)
                if row.parent_id is not None
                else None
            )
        sections.extend(
            (
                epic.item_id,
                epic.title,
                tuple(row for row in rows if epic_for[row.item_id] == epic.item_id),
            )
            for epic in projection.rows
            if epic.kind == WorkItemType.EPIC
        )
        sections.append(
            (None, "Standalone work", tuple(row for row in rows if epic_for[row.item_id] is None))
        )
    return replace(
        projection,
        rows=tuple(
            replace(row, section=name, section_id=section_id)
            for section_id, name, members in sections
            for row in members
        ),
    )
