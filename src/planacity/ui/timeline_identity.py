"""Pure visual identity rules for Timeline work bars and legends."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import blake2s
from uuid import UUID

from planacity.domain import WorkItemType
from planacity.planning.timeline import TimelineGroup, TimelineRow
from planacity.planning.work_context import TopicState
from planacity.ui.theme import Theme

GROUP_PALETTES: dict[Theme, tuple[str, ...]] = {
    Theme.LIGHT: (
        "#0e7490",
        "#2563eb",
        "#7c3aed",
        "#be123c",
        "#b45309",
        "#047857",
        "#c2410c",
        "#4f46e5",
    ),
    Theme.DARK: (
        "#67e8f9",
        "#93c5fd",
        "#c4b5fd",
        "#fda4af",
        "#fcd34d",
        "#6ee7b7",
        "#fdba74",
        "#a5b4fc",
    ),
}

NEUTRAL_COLORS: dict[Theme, dict[TopicState, str]] = {
    Theme.LIGHT: {
        TopicState.UNGROUPED: "#64748b",
        TopicState.AMBIGUOUS: "#475569",
    },
    Theme.DARK: {
        TopicState.UNGROUPED: "#94a3b8",
        TopicState.AMBIGUOUS: "#cbd5e1",
    },
}


class TimelineBarShape(StrEnum):
    EPIC = "epic_bracket"
    TASK = "task_rounded"
    SUBTASK = "subtask_slim"


@dataclass(frozen=True)
class TimelineBarIdentity:
    """Resolved group identity without persisted or row-order-dependent color state."""

    state: TopicState
    group_id: UUID | None
    label: str
    palette_slot: int | None

    def color(self, theme: Theme) -> str:
        if self.palette_slot is not None:
            return GROUP_PALETTES[theme][self.palette_slot]
        return NEUTRAL_COLORS[theme][self.state]

    @property
    def patterned(self) -> bool:
        return self.state == TopicState.AMBIGUOUS


def palette_slot(group_id: UUID) -> int:
    """Map a stable UUID to a palette slot without Python's randomized hash."""
    digest = blake2s(group_id.bytes, digest_size=4).digest()
    return int.from_bytes(digest, "big") % len(GROUP_PALETTES[Theme.LIGHT])


def work_shape(kind: WorkItemType) -> TimelineBarShape:
    return {
        WorkItemType.EPIC: TimelineBarShape.EPIC,
        WorkItemType.TASK: TimelineBarShape.TASK,
        WorkItemType.SUBTASK: TimelineBarShape.SUBTASK,
    }[kind]


def bar_identity(row: TimelineRow, groups: tuple[TimelineGroup, ...]) -> TimelineBarIdentity:
    names = {group.id: group.name for group in groups}
    if row.topic_state == TopicState.RESOLVED:
        if row.primary_group_id is None or row.primary_group_id not in names:
            raise ValueError("A resolved Timeline topic must reference a projected WorkGroup.")
        return TimelineBarIdentity(
            state=row.topic_state,
            group_id=row.primary_group_id,
            label=names[row.primary_group_id],
            palette_slot=palette_slot(row.primary_group_id),
        )
    return TimelineBarIdentity(
        state=row.topic_state,
        group_id=None,
        label=("Ambiguous group" if row.topic_state == TopicState.AMBIGUOUS else "Ungrouped"),
        palette_slot=None,
    )


def group_identity(group: TimelineGroup) -> TimelineBarIdentity:
    return TimelineBarIdentity(
        state=TopicState.RESOLVED,
        group_id=group.id,
        label=group.name,
        palette_slot=palette_slot(group.id),
    )
