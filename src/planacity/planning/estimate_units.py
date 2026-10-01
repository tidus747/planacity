"""Exact estimate conversions; only non-terminating display values are rounded."""

from dataclasses import replace
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.domain.estimate_units import EstimatePreferences, EstimateUnit
from planacity.planning.work_calendar import nominal_week_hours


def set_estimate_preferences(
    plan: ProgramPlan, unit: EstimateUnit, calendar_id: UUID | None = None
) -> ProgramPlan:
    return replace(
        plan,
        estimate_preferences=EstimatePreferences(
            unit=unit, calendar_id=None if unit == EstimateUnit.HOURS else calendar_id
        ),
    )


def hours_per_unit(plan: ProgramPlan) -> Fraction:
    """One week is the explicit weekly total; one day is its positive-day mean.

    These are effort equivalents, never elapsed dates or a person's availability.
    Fractions preserve varying-day calendars without rounding the conversion rate.
    """
    preferences = plan.estimate_preferences
    if preferences.unit == EstimateUnit.HOURS:
        return Fraction(1)
    if preferences.calendar_id is None:
        raise ValueError("Choose a reference work calendar first.")
    calendar = plan.work_calendar(preferences.calendar_id)
    total = Fraction(nominal_week_hours(calendar))
    days = sum(hours > 0 for hours in calendar.weekday_hours)
    if not days:
        raise ValueError("The reference calendar has no working hours.")
    return total if preferences.unit == EstimateUnit.WEEKS else total / days


def _exact_decimal(value: Fraction) -> Decimal | None:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return None
    places = max(twos, fives)
    scaled = value.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    # Tuple construction is exact even under a caller's low Decimal precision.
    digits = tuple(int(digit) for digit in str(abs(scaled)))
    return Decimal((int(scaled < 0), digits, -places))


def format_fraction(value: Fraction) -> str:
    exact = _exact_decimal(value)
    if exact is not None:
        return str(exact)
    with localcontext() as context:
        context.prec = 16
        return "~" + str(Decimal(value.numerator) / Decimal(value.denominator))


def estimate_text(plan: ProgramPlan, hours: Decimal | None, *, editing: bool = False) -> str:
    if hours is None:
        return ""
    if plan.estimate_preferences.unit == EstimateUnit.HOURS:
        return str(hours)
    value = format_fraction(Fraction(hours) / hours_per_unit(plan))
    # A rounded display must never be written back by opening/closing an editor.
    return f"{hours} h" if editing and value.startswith("~") else value


def parse_estimate(plan: ProgramPlan, text: str) -> Decimal | None:
    text = text.strip()
    if not text:
        return None
    explicit_hours = text.lower().endswith("h")
    number = text[:-1].strip() if explicit_hours else text
    try:
        value = Decimal(number)
    except InvalidOperation as error:
        raise ValueError(
            f"Enter a number in {plan.estimate_preferences.unit.value}, "
            "or exact hours with h (for example, 1.5 h)."
        ) from error
    if not value.is_finite() or value < 0:
        raise ValueError("Estimates must be finite, non-negative numbers.")
    if explicit_hours or plan.estimate_preferences.unit == EstimateUnit.HOURS:
        return value
    hours = _exact_decimal(Fraction(value) * hours_per_unit(plan))
    if hours is None:
        raise ValueError(
            "This value converts to repeating hour decimals. Enter exact hours with h "
            "(for example, 1.5 h); the estimate has not been rounded or saved."
        )
    return hours


def conversion_description(plan: ProgramPlan) -> str:
    preferences = plan.estimate_preferences
    if preferences.unit == EstimateUnit.HOURS:
        return "Estimates are entered and displayed in hours. No calendar conversion is used."
    if preferences.calendar_id is None:
        raise ValueError("Choose a reference work calendar first.")
    calendar = plan.work_calendar(preferences.calendar_id)
    return (
        f"Calendar: {calendar.name}. 1 {preferences.unit.value[:-1]} = "
        f"{format_fraction(hours_per_unit(plan))} h. "
        "A week uses all seven weekdays; a day is the mean of positive-hour weekdays. "
        "Leave and reservations do not change effort units. "
        "~ marks a rounded display; its editor shows exact hours with h. "
        "Stored estimates and Jira units stay unchanged."
    )
