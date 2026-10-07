"""Validate canonical plan metadata without loading the desktop UI."""

import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from uuid import uuid4

import pytest

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType, WorkPriority
from planacity.planning.work_items import add_work_item


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 1, 1), date(2026, 1, 1)),
        (date(2026, 12, 23), date(2027, 2, 4)),
        (date(2024, 2, 28), date(2024, 2, 29)),
        (date(2026, 5, 13), date(2026, 6, 24)),
    ],
)
def test_horizon_accepts_arbitrary_inclusive_date_ranges(start: date, end: date) -> None:
    horizon = PlanningHorizon(start, end)
    assert (horizon.start, horizon.end) == (start, end)


def test_horizon_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError, match="on or after"):
        PlanningHorizon(date(2026, 6, 1), date(2026, 5, 1))


@pytest.mark.parametrize("invalid", [None, "2026-01-01", datetime(2026, 1, 1)])
@pytest.mark.parametrize("field", ["start", "end"])
def test_horizon_requires_dates_without_implicit_conversion(invalid: object, field: str) -> None:
    values = {"start": date(2026, 1, 1), "end": date(2026, 1, 2)}
    values[field] = invalid
    with pytest.raises(ValueError, match="dates without a time"):
        PlanningHorizon(**values)


@pytest.fixture
def plan() -> ProgramPlan:
    return ProgramPlan(name="Aurora", horizon=PlanningHorizon(date(2026, 5, 13), date(2026, 6, 24)))


@pytest.mark.parametrize("name", ["", "   ", "\t\n", None, 12])
def test_plan_rejects_blank_or_non_text_names(plan: ProgramPlan, name: object) -> None:
    with pytest.raises(ValueError, match="non-blank name"):
        replace(plan, name=name)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("id", "not-a-uuid", "UUID"),
        ("description", None, "description must be text"),
        ("horizon", None, "PlanningHorizon"),
        ("work_items", [], "tuple"),
        ("work_items", ("not an item",), "WorkItem"),
    ],
)
def test_plan_rejects_invalid_runtime_values(
    plan: ProgramPlan, field: str, value: object, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        replace(plan, **{field: value})


def test_metadata_preserves_identity_unicode_and_user_whitespace(plan: ProgramPlan) -> None:
    name = "  Validaci\u00f3n de Iv\u00e1n  "
    description = "First line\nSecond line: \u2192 original user text."
    changed = replace(plan, name=name, description=description)
    assert changed.name == name
    assert changed.description == description
    assert changed.id == plan.id
    assert plan.name == "Aurora"


def test_plans_have_independent_work_and_generated_ids(plan: ProgramPlan) -> None:
    other = ProgramPlan(name="Other", horizon=plan.horizon)
    item = WorkItem(title="Build test bench", kind=WorkItemType.TASK)
    changed = add_work_item(plan, item)
    assert changed.work_items == (item,)
    assert plan.work_items == other.work_items == ()
    assert plan.id != other.id
    assert changed.id == plan.id
    with pytest.raises(FrozenInstanceError):
        changed.name = "Unexpected mutation"


def test_explicit_ids_survive_reconstruction(plan: ProgramPlan) -> None:
    item = WorkItem(id=uuid4(), title="Build test bench", kind=WorkItemType.TASK)
    reconstructed = ProgramPlan(
        id=plan.id, name=plan.name, horizon=plan.horizon, work_items=(item,)
    )
    assert reconstructed.id == plan.id
    assert reconstructed.work_item(item.id).id == item.id


@pytest.mark.parametrize("priority", [None, *WorkPriority])
def test_work_priority_accepts_only_canonical_optional_levels(
    priority: WorkPriority | None,
) -> None:
    item = WorkItem(title="Build test bench", kind=WorkItemType.TASK, priority=priority)
    assert item.priority == priority


def test_work_priority_rejects_free_form_values() -> None:
    with pytest.raises(ValueError, match="Highest, High, Medium, Low, Lowest, or unset"):
        WorkItem(title="Build test bench", kind=WorkItemType.TASK, priority="urgent")


def test_domain_and_planning_import_without_qt() -> None:
    script = """
import importlib.abc
import sys

class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('PySide6'):
            raise AssertionError('Domain code must not import Qt')

sys.meta_path.insert(0, NoQt())
from datetime import date
from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.work_items import add_work_item
plan = ProgramPlan(name='Aurora', horizon=PlanningHorizon(date.today(), date.today()))
assert len(add_work_item(plan, WorkItem(title='Work', kind=WorkItemType.TASK)).work_items) == 1
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 0, result.stderr
