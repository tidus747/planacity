"""Reservation lifecycle returns validated candidates without committing UI drafts."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import ProgramPlan, ReservationRule
from planacity.planning.reservations import PersonCapacity, ReservationCapacity, reserve_capacity


def reservation_rule(plan: ProgramPlan, rule_id: UUID) -> ReservationRule:
    for rule in plan.reservation_rules:
        if rule.id == rule_id:
            return rule
    raise ValueError("Reservation rule does not exist in this plan.")


def add_reservation(plan: ProgramPlan, rule: ReservationRule) -> ProgramPlan:
    return replace(plan, reservation_rules=(*plan.reservation_rules, rule))


def update_reservation(plan: ProgramPlan, rule: ReservationRule) -> ProgramPlan:
    reservation_rule(plan, rule.id)
    return replace(
        plan,
        reservation_rules=tuple(
            rule if existing.id == rule.id else existing for existing in plan.reservation_rules
        ),
    )


def remove_reservation(plan: ProgramPlan, rule_id: UUID) -> ProgramPlan:
    reservation_rule(plan, rule_id)
    return replace(
        plan, reservation_rules=tuple(rule for rule in plan.reservation_rules if rule.id != rule_id)
    )


def preview_reservations(
    plan: ProgramPlan, capacities: tuple[PersonCapacity, ...]
) -> tuple[ReservationCapacity, ...]:
    """Preview the plan's candidate rules over explicit, fully adjusted daily inputs.

    Editing code previews a candidate and only applies it after confirmation.
    Discarding the candidate or a failed preview leaves the original plan intact.
    No generated occurrence is stored or cached on the plan.
    """
    for capacity in capacities:
        plan.person(capacity.person_id)
    return reserve_capacity(plan.reservation_rules, plan.horizon, capacities)
