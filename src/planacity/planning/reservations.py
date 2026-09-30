"""Deterministic reservation previews over explicit pre-reservation daily capacity."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from planacity.domain.horizon import PlanningHorizon
from planacity.domain.reservations import ReservationRule


@dataclass(frozen=True)
class CapacityDay:
    """Hours after unavailability/program events, before reservations or allocations."""

    day: date
    available_hours: Decimal

    def __post_init__(self) -> None:
        if type(self.day) is not date:
            raise ValueError("Capacity day must be a date without a time.")
        hours = self.available_hours
        if not isinstance(hours, Decimal) or not hours.is_finite() or not 0 <= hours <= 24:
            raise ValueError("Daily available hours must be a finite Decimal from 0 to 24.")


@dataclass(frozen=True)
class PersonCapacity:
    person_id: UUID
    days: tuple[CapacityDay, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.person_id, UUID):
            raise ValueError("Capacity person ID must be a UUID.")
        if not isinstance(self.days, tuple) or any(
            not isinstance(d, CapacityDay) for d in self.days
        ):
            raise ValueError("Supply daily capacity as a tuple of CapacityDay values.")
        if len({d.day for d in self.days}) != len(self.days):
            raise ValueError("Capacity dates must be unique for each person.")


@dataclass(frozen=True)
class ReservationOccurrence:
    rule_id: UUID
    person_id: UUID
    period: PlanningHorizon
    included_period: PlanningHorizon
    requested_hours: Decimal
    eligible_days: int
    included_days: int
    reserved_hours: Fraction | None


@dataclass(frozen=True)
class ReservedDay:
    day: date
    available_hours: Decimal
    reserved_hours: Fraction
    remaining_hours: Fraction
    rule_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class ReservationCapacity:
    person_id: UUID
    days: tuple[ReservedDay, ...]
    occurrences: tuple[ReservationOccurrence, ...]

    @property
    def reserved_hours(self) -> Fraction:
        return sum((day.reserved_hours for day in self.days), Fraction())

    @property
    def remaining_hours(self) -> Fraction | None:
        """Unknown if any positive duty has no eligible day in its complete period."""
        if any(occurrence.reserved_hours is None for occurrence in self.occurrences):
            return None
        return sum((day.remaining_hours for day in self.days), Fraction())

    @property
    def overlaps(self) -> tuple[ReservedDay, ...]:
        return tuple(day for day in self.days if len(day.rule_ids) > 1)

    @property
    def overloaded_days(self) -> tuple[ReservedDay, ...]:
        return tuple(day for day in self.days if day.remaining_hours < 0)


def reservation_periods(
    rule: ReservationRule, horizon: PlanningHorizon
) -> tuple[PlanningHorizon, ...]:
    """Complete anchored periods intersecting both effective dates and the query.

    Anchors align periods in either direction; they are not a recurrence start.
    Effective dates control when a rule applies. A complete period outside Python's
    supported dates is rejected rather than inventing its missing capacity.
    """
    first = max(rule.effective.start, horizon.start).toordinal()
    last = min(rule.effective.end, horizon.end).toordinal()
    if first > last:
        return ()
    width = 7 * rule.interval_weeks
    anchor = rule.anchor.toordinal()
    start = anchor + ((first - anchor) // width) * width
    periods = []
    while start <= last:
        end = start + width - 1
        if start < date.min.toordinal() or end > date.max.toordinal():
            raise ValueError(
                "A complete sprint period is outside supported dates. "
                "Adjust the anchor or interval."
            )
        periods.append(PlanningHorizon(date.fromordinal(start), date.fromordinal(end)))
        start += width
    return tuple(periods)


def _ordinals(period: PlanningHorizon) -> range:
    return range(period.start.toordinal(), period.end.toordinal() + 1)


def _require_days(days: dict[int, Decimal], period: PlanningHorizon, person_id: UUID) -> None:
    for ordinal in _ordinals(period):
        if ordinal not in days:
            raise ValueError(
                f"Missing capacity for person {person_id} on {date.fromordinal(ordinal)}. "
                "Supply every queried date and complete sprint period, "
                "including explicit zero days."
            )


def reserve_capacity(
    rules: tuple[ReservationRule, ...],
    horizon: PlanningHorizon,
    capacities: tuple[PersonCapacity, ...],
) -> tuple[ReservationCapacity, ...]:
    """Spread each period's fixed hours equally over its positive-capacity days.

    Supply capacity after availability and capacity-affecting program events.
    Every queried date and every complete relevant sprint must be present, even
    outside effective/query dates, so proration never uses a truncated denominator.
    Missing capacity is an error, not a zero-hour day. No calendar defaults apply.

    Fractions retain exact rational hours when division has a recurring decimal.
    Multiple duties add; negative remaining capacity and overlapping rule IDs are
    exposed, not clamped or silently merged. Inputs and source snapshots are never
    changed. This API does not persist generated occurrences or apply allocations.
    """
    if not isinstance(horizon, PlanningHorizon):
        raise ValueError("Supply a planning horizon.")
    if not isinstance(rules, tuple) or any(not isinstance(r, ReservationRule) for r in rules):
        raise ValueError("Supply a tuple of ReservationRule values.")
    if len({r.id for r in rules}) != len(rules):
        raise ValueError("Reservation IDs must be unique.")
    if not isinstance(capacities, tuple) or any(
        not isinstance(c, PersonCapacity) for c in capacities
    ):
        raise ValueError("Supply a tuple of PersonCapacity values.")
    if len({c.person_id for c in capacities}) != len(capacities):
        raise ValueError("Capacity person IDs must be unique.")
    people = {c.person_id for c in capacities}
    if any(person not in people for rule in rules for person in rule.person_ids):
        raise ValueError("Every reservation person needs explicit daily capacity.")
    periods = {rule.id: reservation_periods(rule, horizon) for rule in rules}
    results = []
    for capacity in sorted(capacities, key=lambda c: str(c.person_id)):
        hours = {day.day.toordinal(): day.available_hours for day in capacity.days}
        _require_days(hours, horizon, capacity.person_id)
        reserved: dict[int, Fraction] = {}
        applied: dict[int, list[UUID]] = {}
        occurrences = []
        for rule in sorted(rules, key=lambda r: str(r.id)):
            if capacity.person_id not in rule.person_ids:
                continue
            for period in periods[rule.id]:
                _require_days(hours, period, capacity.person_id)
                included = PlanningHorizon(
                    max(period.start, rule.effective.start, horizon.start),
                    min(period.end, rule.effective.end, horizon.end),
                )
                eligible = [ordinal for ordinal in _ordinals(period) if hours[ordinal] > 0]
                selected = [ordinal for ordinal in _ordinals(included) if hours[ordinal] > 0]
                share = Fraction(rule.hours_per_person) / len(eligible) if eligible else None
                occurrences.append(
                    ReservationOccurrence(
                        rule.id,
                        capacity.person_id,
                        period,
                        included,
                        rule.hours_per_person,
                        len(eligible),
                        len(selected),
                        share * len(selected) if share is not None else None,
                    )
                )
                if share is not None:
                    for ordinal in selected:
                        reserved[ordinal] = reserved.get(ordinal, Fraction()) + share
                        applied.setdefault(ordinal, []).append(rule.id)
        days = tuple(
            ReservedDay(
                date.fromordinal(ordinal),
                hours[ordinal],
                reserved.get(ordinal, Fraction()),
                Fraction(hours[ordinal]) - reserved.get(ordinal, Fraction()),
                tuple(applied.get(ordinal, ())),
            )
            for ordinal in _ordinals(horizon)
        )
        results.append(ReservationCapacity(capacity.person_id, days, tuple(occurrences)))
    return tuple(results)
