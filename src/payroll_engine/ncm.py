"""Calculate NCM from an explicitly supplied, recognized daily benefit base.

Inputs describe one period with constant contracted hours and rest percentage.
Recognized benefit days are independent of the salary's standard 30-day month.
This module does not determine entitlement, payroll deductions or contributions.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .base_salary import (
    CENT,
    MAX_INPUT_AMOUNT,
    InvalidBaseSalaryInput,
    _calculation_context,
)


class InvalidNcmInput(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NcmBenefit:
    contracted_percentage: Decimal
    rest_percentage: Decimal
    effective_working_percentage: Decimal
    recognized_daily_base: Decimal
    benefit_days: int
    equivalent_rest_days: Decimal
    gross_benefit: Decimal
    rounding: str


def _validate_positive_decimal(
    field: str, value: Decimal, maximum: Decimal, unit: Decimal
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InvalidNcmInput(field, f"{field}: indica un Decimal finito.")
    if not Decimal(0) < value <= maximum:
        raise InvalidNcmInput(
            field, f"{field}: debe ser mayor que 0 y no superar {maximum}."
        )
    if value != value.quantize(unit):
        raise InvalidNcmInput(
            field, f"{field}: la precisión admitida es {unit}."
        )


def calculate_ncm_benefit(
    contracted_percentage: Decimal,
    rest_percentage: Decimal,
    recognized_daily_base: Decimal,
    benefit_days: int,
    rounding: str,
) -> NcmBenefit:
    """Apply rest once to the habitual job's daily base; round the total once.

    The supplied INSS base must precede the NCM rest adjustment and already
    correspond to the contracted job, including a part-time contract if any.
    Days are those recognized for this period within one month, not inferred
    from salary days. Eligibility and authorized rest percentages are external.
    """
    try:
        context = _calculation_context(rounding)
    except InvalidBaseSalaryInput as error:
        raise InvalidNcmInput(error.field, str(error)) from error
    with localcontext(context):
        for field, value in (
            ("contracted_percentage", contracted_percentage),
            ("rest_percentage", rest_percentage),
        ):
            _validate_positive_decimal(field, value, Decimal(100), CENT)
        _validate_positive_decimal(
            "recognized_daily_base",
            recognized_daily_base,
            MAX_INPUT_AMOUNT,
            Decimal("0.0001"),
        )
        if type(benefit_days) is not int or not 1 <= benefit_days <= 31:
            raise InvalidNcmInput(
                "benefit_days", "Indica entre 1 y 31 días enteros reconocidos."
            )
        rest_fraction = rest_percentage / 100
        return NcmBenefit(
            contracted_percentage=contracted_percentage,
            rest_percentage=rest_percentage,
            effective_working_percentage=(
                contracted_percentage * (1 - rest_fraction)
            ),
            recognized_daily_base=recognized_daily_base,
            benefit_days=benefit_days,
            equivalent_rest_days=benefit_days * rest_fraction,
            gross_benefit=(
                recognized_daily_base * rest_fraction * benefit_days
            ).quantize(CENT),
            rounding=rounding,
        )
