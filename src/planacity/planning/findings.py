"""Reusable planning findings calculated from one immutable plan snapshot."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.allocations import summarize_allocations
from planacity.planning.capacity import (
    CapacityGap,
    CapacityGapKind,
    DatedCapacity,
    DatedCapacityDay,
    calculate_dated_capacity,
)


class FindingSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class FindingRule(StrEnum):
    MISSING_CALENDAR = "capacity.missing_calendar"
    MISSING_WORK_DATES = "work.missing_dates"
    MISSING_ESTIMATE = "work.missing_estimate"
    UNALLOCATED_WORK = "work.unallocated"
    ALLOCATION_MISMATCH = "work.allocation_mismatch"
    HIERARCHY_EFFORT = "work.hierarchy_effort"
    UNRESOLVED_RESERVATION = "capacity.unresolved_reservation"
    NO_PLANNING_CAPACITY = "capacity.no_planning_capacity"
    OVERLOAD = "capacity.overload"
    CAPACITY_QUERY_LIMIT = "capacity.query_limit"


@dataclass(frozen=True)
class PlanningFinding:
    """One advisory problem; findings never modify or block saving a plan."""

    rule_key: FindingRule
    severity: FindingSeverity
    title: str
    explanation: str
    suggested_action: str
    work_item_ids: tuple[UUID, ...] = ()
    person_ids: tuple[UUID, ...] = ()
    source_ids: tuple[UUID, ...] = ()
    date_range: PlanningHorizon | None = None


def _hours(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _ids(values: set[UUID]) -> tuple[UUID, ...]:
    return tuple(sorted(values, key=str))


def _work_for_person(plan: ProgramPlan, person_id: UUID) -> tuple[UUID, ...]:
    return _ids(
        {
            allocation.work_item_id
            for allocation in plan.allocations
            if allocation.person_id == person_id and allocation.hours > 0
        }
    )


def _missing_calendar_findings(
    plan: ProgramPlan, gaps: tuple[CapacityGap, ...]
) -> tuple[PlanningFinding, ...]:
    findings = []
    for person in plan.people:
        relevant = tuple(
            gap
            for gap in gaps
            if gap.kind == CapacityGapKind.MISSING_CALENDAR and gap.person_id == person.id
        )
        if not relevant:
            continue
        findings.append(
            PlanningFinding(
                FindingRule.MISSING_CALENDAR,
                FindingSeverity.WARNING,
                "Missing work calendar",
                f"{person.name} has no work calendar, so their planning capacity is unknown.",
                "Assign a work calendar in People.",
                work_item_ids=_ids(
                    {gap.work_item_id for gap in relevant if gap.work_item_id is not None}
                ),
                person_ids=(person.id,),
                source_ids=_ids({gap.source_id for gap in relevant if gap.source_id is not None}),
                date_range=plan.horizon,
            )
        )
    return tuple(findings)


def _gap_finding(plan: ProgramPlan, gap: CapacityGap) -> PlanningFinding | None:
    work_ids = (gap.work_item_id,) if gap.work_item_id is not None else ()
    person_ids = (gap.person_id,) if gap.person_id is not None else ()
    source_ids = (gap.source_id,) if gap.source_id is not None else ()
    if gap.kind == CapacityGapKind.MISSING_WORK_DATES:
        if gap.work_item_id is None:
            return None
        item = plan.work_item(gap.work_item_id)
        return PlanningFinding(
            FindingRule.MISSING_WORK_DATES,
            FindingSeverity.WARNING,
            "Missing work dates",
            f"{item.title} needs both a start and end date before allocated hours can be placed.",
            "Set both dates in Plan.",
            work_item_ids=work_ids,
            person_ids=person_ids,
            source_ids=source_ids,
        )
    if gap.kind == CapacityGapKind.NO_PLANNING_CAPACITY:
        assert gap.work_item_id is not None and gap.person_id is not None
        item = plan.work_item(gap.work_item_id)
        person = plan.person(gap.person_id)
        demand = f" {_hours(gap.hours)} h" if gap.hours is not None else ""
        return PlanningFinding(
            FindingRule.NO_PLANNING_CAPACITY,
            FindingSeverity.ERROR,
            "No planning capacity",
            f"{item.title} has{demand} allocated to {person.name}, but its date window has no "
            "positive planning capacity.",
            "Change the dates, availability, reservations, calendar, or allocated hours.",
            work_item_ids=work_ids,
            person_ids=person_ids,
            source_ids=source_ids,
            date_range=gap.period,
        )
    if gap.kind == CapacityGapKind.UNRESOLVED_RESERVATION:
        assert gap.person_id is not None
        person = plan.person(gap.person_id)
        return PlanningFinding(
            FindingRule.UNRESOLVED_RESERVATION,
            FindingSeverity.WARNING,
            "Unplaced reserved capacity",
            f"A reservation for {person.name} cannot be placed in its complete period.",
            "Review the reservation, calendar, and availability in People.",
            work_item_ids=_work_for_person(plan, person.id),
            person_ids=person_ids,
            source_ids=source_ids,
            date_range=gap.period,
        )
    if gap.kind == CapacityGapKind.QUERY_LIMIT:
        return PlanningFinding(
            FindingRule.CAPACITY_QUERY_LIMIT,
            FindingSeverity.WARNING,
            "Capacity range too large",
            gap.message,
            "Shorten the planning horizon or the dated work and reservation ranges.",
            date_range=gap.period,
        )
    return None


def _overload_findings(plan: ProgramPlan, capacity: DatedCapacity) -> tuple[PlanningFinding, ...]:
    findings = []
    for person_result in capacity.people:
        overloaded = tuple(day for day in person_result.days if day.remaining_hours < 0)
        if not overloaded:
            continue
        groups: list[list[DatedCapacityDay]] = []
        for day in overloaded:
            if groups and day.day == groups[-1][-1].day + timedelta(days=1):
                groups[-1].append(day)
            else:
                groups.append([day])
        person = plan.person(person_result.person_id)
        for group in groups:
            first = group[0]
            last = group[-1]
            total = sum((-day.remaining_hours for day in group), Fraction())
            peak = max(-day.remaining_hours for day in group)
            allocations = {entry.allocation_id for day in group for entry in day.allocations}
            work = {entry.work_item_id for day in group for entry in day.allocations}
            reservations = {entry.rule_id for day in group for entry in day.reservations}
            period = PlanningHorizon(first.day, last.day)
            when = (
                first.day.isoformat()
                if first.day == last.day
                else f"{first.day.isoformat()} to {last.day.isoformat()}"
            )
            findings.append(
                PlanningFinding(
                    FindingRule.OVERLOAD,
                    FindingSeverity.ERROR,
                    "Capacity overload",
                    f"{person.name} is overloaded by {_hours(total)} h across {when}; "
                    f"the highest daily overload is {_hours(peak)} h. All concurrent work and "
                    "reservations are included.",
                    "Reduce or move allocated work, restore availability, or change reservations.",
                    work_item_ids=_ids(work),
                    person_ids=(person.id,),
                    source_ids=_ids(allocations | reservations),
                    date_range=period,
                )
            )
    return tuple(findings)


def planning_findings(plan: ProgramPlan) -> tuple[PlanningFinding, ...]:
    """Calculate deterministic advisory findings from the complete current plan."""
    summaries = summarize_allocations(plan, plan.allocations).work
    findings: list[PlanningFinding] = []
    for item, summary in zip(plan.work_items, summaries, strict=True):
        if not summary.is_container:
            if item.start is None or item.end is None:
                findings.append(
                    PlanningFinding(
                        FindingRule.MISSING_WORK_DATES,
                        FindingSeverity.WARNING,
                        "Missing work dates",
                        f"{item.title} needs both a start and end date before work can be "
                        "scheduled.",
                        "Set both dates in Plan.",
                        work_item_ids=(item.id,),
                    )
                )
            if summary.missing_estimate:
                findings.append(
                    PlanningFinding(
                        FindingRule.MISSING_ESTIMATE,
                        FindingSeverity.WARNING,
                        "Missing estimate",
                        f"{item.title} has no effort estimate.",
                        "Enter an estimate on the leaf work item.",
                        work_item_ids=(item.id,),
                    )
                )
            elif summary.estimate_hours and summary.unassigned:
                findings.append(
                    PlanningFinding(
                        FindingRule.UNALLOCATED_WORK,
                        FindingSeverity.WARNING,
                        "Unallocated work",
                        f"{item.title} has {summary.estimate_hours} h estimated but no positive "
                        "allocation.",
                        "Open Work allocations and assign its planned hours.",
                        work_item_ids=(item.id,),
                    )
                )
            elif summary.remaining_hours is not None and summary.remaining_hours != 0:
                findings.append(
                    PlanningFinding(
                        FindingRule.ALLOCATION_MISMATCH,
                        FindingSeverity.WARNING,
                        "Estimate and allocation differ",
                        f"{item.title} has {summary.estimate_hours} h estimated and "
                        f"{summary.allocated_hours} h allocated.",
                        "Review the estimate or explicit allocation split.",
                        work_item_ids=(item.id,),
                        source_ids=_ids(
                            {
                                allocation.id
                                for allocation in plan.allocations
                                if allocation.work_item_id == item.id
                            }
                        ),
                    )
                )
        if summary.has_direct_container_allocations:
            mixed = summary.mixed_level_effort
            findings.append(
                PlanningFinding(
                    FindingRule.HIERARCHY_EFFORT,
                    FindingSeverity.WARNING,
                    "Mixed hierarchy effort" if mixed else "Direct container effort",
                    (
                        f"{item.title} has direct and descendant allocations, so its effort is "
                        "mixed across hierarchy levels."
                        if mixed
                        else f"{item.title} has allocations stored directly on a container."
                    ),
                    "Move direct effort to a named leaf from Work allocations.",
                    work_item_ids=(item.id,),
                    source_ids=_ids(
                        {
                            allocation.id
                            for allocation in plan.allocations
                            if allocation.work_item_id == item.id
                        }
                    ),
                )
            )

    capacity = calculate_dated_capacity(plan, plan.horizon)
    findings.extend(_missing_calendar_findings(plan, capacity.all_gaps))
    existing_missing_dates = {
        finding.work_item_ids[0]
        for finding in findings
        if finding.rule_key == FindingRule.MISSING_WORK_DATES and finding.work_item_ids
    }
    for gap in capacity.all_gaps:
        if gap.kind == CapacityGapKind.MISSING_CALENDAR:
            continue
        if (
            gap.kind == CapacityGapKind.MISSING_WORK_DATES
            and gap.work_item_id in existing_missing_dates
        ):
            continue
        finding = _gap_finding(plan, gap)
        if finding is not None:
            findings.append(finding)
    findings.extend(_overload_findings(plan, capacity))
    return tuple(findings)


def findings_for_work(
    plan: ProgramPlan,
    findings: tuple[PlanningFinding, ...],
    work_item_id: UUID,
    *,
    include_descendants: bool = True,
) -> tuple[PlanningFinding, ...]:
    """Select findings relevant to one row while retaining global calculation gaps."""
    scope = {work_item_id}
    if include_descendants:
        pending = [work_item_id]
        while pending:
            children = plan.children(pending.pop())
            scope.update(child.id for child in children)
            pending.extend(child.id for child in children)
    return tuple(
        finding
        for finding in findings
        if scope.intersection(finding.work_item_ids)
        or finding.rule_key == FindingRule.CAPACITY_QUERY_LIMIT
    )
