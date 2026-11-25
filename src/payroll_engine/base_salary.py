"""Distribute contractual base salary without reapplying contracted hours.

The amount already belongs to the employee's agreed working time. Temporary
reductions and absences are separate inputs for later calculation stages.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext

CENT = Decimal("0.01")
MAX_INPUT_AMOUNT = Decimal("9999999999.99")


class InvalidBaseSalaryInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BaseSalaryBreakdown:
    annual_amount: Decimal
    ordinary_payment_amount: Decimal
    extra_payments_per_year: int
    extra_payment_amount: Decimal
    annual_rounding_difference: Decimal
    rounding: str


def _calculation_context(rounding: str) -> Context:
    if not isinstance(rounding, str):
        raise InvalidBaseSalaryInput(
            "rounding", "El modo de redondeo debe indicarse explícitamente."
        )
    try:
        return Context(prec=28, rounding=rounding)
    except (TypeError, ValueError) as error:
        raise InvalidBaseSalaryInput(
            "rounding", "Indica un modo de redondeo válido de decimal."
        ) from error


def _validate_input(amount: Decimal, payments_per_year: int) -> None:
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise InvalidBaseSalaryInput(
            "amount", "El sueldo base debe ser un Decimal finito."
        )
    if not Decimal(0) <= amount <= MAX_INPUT_AMOUNT:
        raise InvalidBaseSalaryInput(
            "amount", "El importe debe estar entre 0 y 9999999999.99 euros."
        )
    if amount != amount.quantize(CENT):
        raise InvalidBaseSalaryInput(
            "amount", "El importe no puede contener fracciones de céntimo."
        )
    if type(payments_per_year) is not int or payments_per_year not in (12, 14):
        raise InvalidBaseSalaryInput(
            "payments_per_year", "El número de pagas debe ser 12 o 14."
        )


def _breakdown(
    annual_amount: Decimal,
    payment_amount: Decimal,
    payments_per_year: int,
    rounding: str,
) -> BaseSalaryBreakdown:
    extra_count = payments_per_year - 12
    extra_amount = payment_amount if extra_count else Decimal("0.00")
    distributed_amount = payment_amount * 12 + extra_amount * extra_count
    return BaseSalaryBreakdown(
        annual_amount=annual_amount,
        ordinary_payment_amount=payment_amount,
        extra_payments_per_year=extra_count,
        extra_payment_amount=extra_amount,
        annual_rounding_difference=annual_amount - distributed_amount,
        rounding=rounding,
    )


def base_salary_from_annual(
    amount: Decimal, payments_per_year: int, rounding: str
) -> BaseSalaryBreakdown:
    """Distribute contractual annual base salary and expose rounding differences."""
    with localcontext(_calculation_context(rounding)):
        _validate_input(amount, payments_per_year)
        annual_amount = amount.quantize(CENT)
        payment_amount = (annual_amount / payments_per_year).quantize(CENT)
        return _breakdown(
            annual_amount, payment_amount, payments_per_year, rounding
        )


def base_salary_from_monthly(
    amount: Decimal, payments_per_year: int, rounding: str
) -> BaseSalaryBreakdown:
    """Annualize contractual base salary per payment, with equal base extras."""
    with localcontext(_calculation_context(rounding)):
        _validate_input(amount, payments_per_year)
        payment_amount = amount.quantize(CENT)
        annual_amount = payment_amount * payments_per_year
        return _breakdown(
            annual_amount, payment_amount, payments_per_year, rounding
        )


def prorate_monthly_salary(
    amount: Decimal, salary_days: int, rounding: str
) -> Decimal:
    """Prorate a monthly amount using the explicitly agreed divisor of 30.

    Days must already have been counted according to the applicable payroll
    calendar. Round the final amount, never the daily rate before multiplying.
    """
    with localcontext(_calculation_context(rounding)):
        _validate_input(amount, 12)
        if type(salary_days) is not int or not 0 <= salary_days <= 30:
            raise InvalidBaseSalaryInput(
                "salary_days", "Indica un número entero de días entre 0 y 30."
            )
        return (amount / 30 * salary_days).quantize(CENT)


def standard_month_salary_days(
    employment_start: date, employment_end: date | None, month_start: date
) -> int:
    """Count a salary month as 30 days, including February.

    The end date is exclusive, as in the employment model. The last calendar
    day closes day 30; day 31 occupies day 30 rather than adding a 31st day.
    This salary convention does not define Social Security contribution days.
    """
    for field, value in (
        ("employment_start", employment_start),
        ("month_start", month_start),
    ):
        if type(value) is not date:
            raise InvalidBaseSalaryInput(field, "Indica una fecha sin hora.")
    if employment_end is not None:
        if (
            type(employment_end) is not date
            or employment_end <= employment_start
        ):
            raise InvalidBaseSalaryInput(
                "employment_end",
                "El fin exclusivo debe ser posterior al inicio.",
            )
    if month_start.day != 1:
        raise InvalidBaseSalaryInput(
            "month_start", "El mes debe comenzar el día 1."
        )
    month_end = date(
        month_start.year + (month_start.month == 12),
        month_start.month % 12 + 1,
        1,
    )
    start = max(employment_start, month_start)
    end = min(employment_end or month_end, month_end)
    if start >= end:
        return 0
    last_day = end - timedelta(days=1)
    end_day = 30 if end == month_end else min(last_day.day, 30)
    return max(0, end_day - min(start.day, 30) + 1)


def monthly_contribution_days(
    employment_start: date, employment_end: date | None, month_start: date
) -> int:
    """Use 30 for a full monthly contribution period, actual days otherwise.

    TGSS monthly base adjustment rules (December 2024), sections 1 and 6.
    Only the ordinary full-time monthly profile without incidents is covered.
    """
    salary_days = standard_month_salary_days(
        employment_start, employment_end, month_start
    )
    if salary_days == 0:
        return 0
    month_end = date(
        month_start.year + (month_start.month == 12),
        month_start.month % 12 + 1,
        1,
    )
    if employment_start <= month_start and (
        employment_end is None or employment_end >= month_end
    ):
        return 30
    return (
        min(employment_end or month_end, month_end)
        - max(employment_start, month_start)
    ).days
