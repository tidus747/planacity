"""Calendar boundaries and bar geometry do not require Qt or editable plan copies."""

from datetime import date

import pytest

from planacity.domain import PlanningHorizon
from planacity.planning.timeline_axis import TimelineAxis, TimelineScale, bar_span


@pytest.mark.parametrize("scale", list(TimelineScale))
@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 1, 1), date(2026, 1, 1)),
        (date(2024, 2, 27), date(2024, 3, 3)),
        (date(2025, 12, 30), date(2026, 2, 2)),
        (date.min, date(1, 1, 12)),
        (date(9999, 12, 20), date.max),
    ],
)
def test_periods_cover_horizon_once_and_days_roundtrip(scale, start, end):
    axis = TimelineAxis(PlanningHorizon(start, end), scale)
    covered = []
    for column in range(axis.columns):
        period = axis.period(column)
        assert period.days <= period.full_days
        for day in range(period.start_day, period.end_day + 1):
            covered.append(day)
            assert axis.column_for_day(day) == column
    assert covered == list(range((end - start).days + 1))
    assert axis.column_for_day(-100) == 0
    assert axis.column_for_day(axis.total_days + 100) == axis.columns - 1
    with pytest.raises(IndexError):
        axis.period(-1)
    with pytest.raises(IndexError):
        axis.period(axis.columns)


def test_weeks_align_to_monday_and_use_iso_week_year():
    axis = TimelineAxis(PlanningHorizon(date(2025, 12, 31), date(2026, 1, 13)), TimelineScale.WEEK)
    assert axis.columns == 3
    assert axis.period(0).label == "2026-W01"
    assert (axis.period(0).start_day, axis.period(0).end_day) == (0, 4)
    assert (axis.period(1).start_day, axis.period(1).end_day) == (5, 11)
    assert axis.period(2).days == 2


def test_months_use_calendar_lengths_including_leap_day():
    axis = TimelineAxis(PlanningHorizon(date(2024, 1, 30), date(2024, 3, 2)), TimelineScale.MONTH)
    assert [(axis.period(i).days, axis.period(i).full_days) for i in range(3)] == [
        (2, 31),
        (29, 29),
        (2, 31),
    ]
    assert axis.period(1).label == "Feb 2024"
    period = axis.period(1)
    assert bar_span(2, 2, period) == (0, 1 / 29)
    assert bar_span(30, 30, period) == (28 / 29, 1)
    assert bar_span(-100, 100, period) == (0, 1)
    assert bar_span(31, 35, period) is None
    assert bar_span(-5, -1, period) is None


def test_maximum_horizon_axis_does_not_allocate_day_collections():
    axis = TimelineAxis(PlanningHorizon(date.min, date.max), TimelineScale.DAY)
    assert axis.columns == date.max.toordinal()
    assert axis.period(axis.columns - 1).end_day == date.max.toordinal() - 1
