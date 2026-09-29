"""Date resizing preserves estimates, baselines and unrelated canonical work."""

from datetime import date
from decimal import Decimal

import pytest

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
)
from planacity.domain.models import ImportedWork, ImportSnapshot
from planacity.planning.timeline_axis import TimelineAxis, TimelineScale
from planacity.planning.timeline_resize import resize_work, snapped_day


def resize_plan():
    item = WorkItem(
        title="Calibration",
        kind=WorkItemType.TASK,
        start=date(2024, 2, 20),
        end=date(2024, 3, 2),
        estimate_hours=Decimal("7.5"),
    )
    baseline = ImportSnapshot(
        name="Jira",
        headers=("Summary",),
        rows=((item.title,),),
        records=(ImportedWork(item=item, external_reference="LAB-1"),),
    )
    return ProgramPlan(
        name="Leap year",
        horizon=PlanningHorizon(date(2024, 2, 1), date(2024, 3, 15)),
        work_items=(item,),
        imports=(baseline,),
    )


@pytest.mark.parametrize("scale", list(TimelineScale))
@pytest.mark.parametrize(
    "horizon",
    [
        PlanningHorizon(date(2024, 2, 20), date(2024, 3, 4)),
        PlanningHorizon(date.min, date(1, 1, 5)),
        PlanningHorizon(date(9999, 12, 28), date.max),
    ],
)
def test_day_boundary_snapping_at_every_scale_and_date_limits(scale, horizon):
    axis = TimelineAxis(horizon, scale)
    for day in range(axis.total_days):
        period = axis.period(axis.column_for_day(day))
        assert snapped_day(period, (day - period.start_day) / period.days, "start") == day
        assert snapped_day(period, (day - period.start_day + 1) / period.days, "end") == day


def test_resize_preserves_baseline_hours_and_accepts_outside_horizon_without_clamping():
    plan = resize_plan()
    item = plan.work_items[0]
    updated = resize_work(plan, item.id, "end", date(2024, 3, 20))
    assert updated.work_items[0].end == date(2024, 3, 20)
    assert updated.work_items[0].estimate_hours == Decimal("7.5")
    assert updated.imports is plan.imports
    assert updated.imports[0].records[0].item is item
    assert plan.work_items[0].end == date(2024, 3, 2)
    assert resize_work(plan, item.id, "end", item.start).work_items[0].end == item.start
    with pytest.raises(ValueError, match="on or after"):
        resize_work(plan, item.id, "end", date(2024, 2, 19))
