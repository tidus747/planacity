"""Calendar-day snapping and validated Timeline resize proposals."""

from datetime import date
from math import floor
from typing import Literal
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.planning.timeline_axis import TimelinePeriod
from planacity.planning.work_items import set_work_dates

ResizeEdge = Literal["start", "end"]


def snapped_day(period: TimelinePeriod, fraction: float, edge: ResizeEdge) -> int:
    """Convert a fractional period boundary to an inclusive day offset."""
    return period.start_day + floor(fraction * period.days + 0.5) - int(edge == "end")


def resize_work(plan: ProgramPlan, item_id: UUID, edge: ResizeEdge, day: date) -> ProgramPlan:
    """Resize one scheduled item without clamping dates or propagating dependencies."""
    item = plan.work_item(item_id)
    if item.start is None or item.end is None:
        raise ValueError("Set both dates with Edit dates before resizing this work.")
    return set_work_dates(
        plan,
        item_id,
        start=day if edge == "start" else item.start,
        end=day if edge == "end" else item.end,
    )
