"""Distribute contractual base salary without reapplying contracted hours.

The amount already belongs to the employee's agreed working time. Temporary
reductions and absences are separate inputs for later calculation stages.
"""

from dataclasses import dataclass
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
